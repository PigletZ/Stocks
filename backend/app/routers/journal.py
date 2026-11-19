from datetime import datetime, date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session

from ..database import get_session
from ..validation import parse_iso_date
from ..services.journal_service import JournalService

router = APIRouter()


class NoteIn(BaseModel):
    content: str = ""
    codes: List[str] = []


class TradeIn(BaseModel):
    stock_code: str
    direction: str  # buy / sell
    price: float
    quantity: int
    fee: float = 0.0
    traded_at: datetime
    note: Optional[str] = None


class TradeUpdate(BaseModel):
    stock_code: Optional[str] = None
    direction: Optional[str] = None
    price: Optional[float] = None
    quantity: Optional[int] = None
    fee: Optional[float] = None
    traded_at: Optional[datetime] = None
    note: Optional[str] = None


def _parse_date(d: str) -> date:
    return parse_iso_date(d)


# ==================== 复盘笔记 ====================

@router.get("/note")
def get_note(date: str = Query(..., description="日期 YYYY-MM-DD"), session: Session = Depends(get_session)):
    service = JournalService()
    return service.get_note(_parse_date(date), session)


@router.put("/note")
def upsert_note(
    body: NoteIn,
    date: str = Query(..., description="日期 YYYY-MM-DD"),
    session: Session = Depends(get_session),
):
    service = JournalService()
    return service.upsert_note(_parse_date(date), body.content, body.codes, session)


@router.delete("/note")
def delete_note(date: str = Query(..., description="日期 YYYY-MM-DD"), session: Session = Depends(get_session)):
    service = JournalService()
    if not service.delete_note(_parse_date(date), session):
        raise HTTPException(status_code=404, detail="笔记不存在")
    return {"message": "已删除"}


@router.get("/note-dates")
def list_note_dates(
    year: int = Query(..., ge=1, le=9998),
    month: int = Query(..., ge=1, le=12),
    session: Session = Depends(get_session),
):
    """指定月份有笔记/有交易的日期（日历标记）"""
    service = JournalService()
    return {
        "note_dates": service.list_note_dates(year, month, session),
        "trade_dates": service.list_trade_dates(year, month, session),
    }


# ==================== 交易台账 ====================

@router.get("/trades")
def list_trades(
    code: Optional[str] = Query(None),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    session: Session = Depends(get_session),
):
    service = JournalService()
    return service.list_trades(
        session,
        code=code,
        start=_parse_date(start) if start else None,
        end=_parse_date(end) if end else None,
    )


@router.post("/trades")
def create_trade(body: TradeIn, session: Session = Depends(get_session)):
    service = JournalService()
    try:
        return service.create_trade(
            stock_code=body.stock_code,
            direction=body.direction,
            price=body.price,
            quantity=body.quantity,
            fee=body.fee,
            traded_at=body.traded_at,
            note=body.note,
            session=session,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/trades/{trade_id}")
def update_trade(trade_id: int, body: TradeUpdate, session: Session = Depends(get_session)):
    service = JournalService()
    try:
        result = service.update_trade(trade_id, session, **body.model_dump(exclude_unset=True))
    except ValueError as error:
        raise HTTPException(400, str(error))
    if result is None:
        raise HTTPException(status_code=404, detail="交易记录不存在")
    return result


@router.delete("/trades/{trade_id}")
def delete_trade(trade_id: int, session: Session = Depends(get_session)):
    service = JournalService()
    try:
        deleted = service.delete_trade(trade_id, session)
    except ValueError as error:
        raise HTTPException(400, str(error))
    if not deleted:
        raise HTTPException(status_code=404, detail="交易记录不存在")
    return {"message": "已删除"}


# ==================== 持仓与统计 ====================

@router.get("/positions")
def get_positions(session: Session = Depends(get_session)):
    """当前持仓（FIFO 成本）与浮动盈亏"""
    service = JournalService()
    return service.get_positions(session)


@router.get("/stats")
def get_stats(session: Session = Depends(get_session)):
    """整体盈亏统计：已实现盈亏、胜率、交易次数"""
    service = JournalService()
    return service.get_stats(session)
