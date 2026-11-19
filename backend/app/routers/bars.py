from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List, Optional
from datetime import date, datetime, time, timedelta
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..database import get_session
from ..models import Bar
from ..services.tushare_stock_service import TushareStockService

router = APIRouter()


def _ensure_stock_and_sync(
    code: str,
    start: Optional[date],
    end: Optional[date],
    session: Session,
) -> List[Bar]:
    service = TushareStockService()
    try:
        service.ensure_stock_exists(code, session)
        bars = service.fetch_daily_bars(code, start=start, end=end)
    except RuntimeError:
        raise HTTPException(503, "行情数据暂时不可用，已保留已有 K 线，请稍后重试")
    if not bars:
        return []

    values = [bar.model_dump(exclude={"id"}) for bar in bars]
    try:
        for offset in range(0, len(values), 100):
            statement = sqlite_insert(Bar).values(values[offset:offset+100])
            statement = statement.on_conflict_do_update(
                index_elements=["stock_code", "timestamp", "interval"],
                set_={field: getattr(statement.excluded, field) for field in
                      ("open", "high", "low", "close", "volume", "adjusted")},
            )
            session.execute(statement)
        session.commit()
    except Exception:
        session.rollback()
        raise

    return bars


@router.get("/{code}", response_model=List[Bar])
def get_bars(
    code: str,
    interval: str = "1d",
    start: Optional[date] = None,
    end: Optional[date] = None,
    auto_sync: bool = True,
    session: Session = Depends(get_session),
):
    if interval != "1d":
        raise HTTPException(status_code=400, detail="仅支持日线 K 线（interval=1d）")
    if start and end and start > end:
        raise HTTPException(400, "开始日期不能晚于结束日期")

    query = select(Bar).where(Bar.stock_code == code, Bar.interval == "1d")
    if start:
        query = query.where(Bar.timestamp >= datetime.combine(start, time.min))
    if end:
        query = query.where(Bar.timestamp < datetime.combine(end, time.min)+timedelta(days=1))
    bars = session.exec(query.order_by(Bar.timestamp)).all()

    # 本地没有数据时自动从 Tushare 同步
    if not bars and auto_sync:
        bars = _ensure_stock_and_sync(code, start, end, session)

    return bars


@router.post("/{code}/sync")
def sync_bars(
    code: str,
    interval: str = "1d",
    start: Optional[date] = None,
    end: Optional[date] = None,
    session: Session = Depends(get_session),
):
    """从 Tushare 拉取指定股票的日线 K 线并缓存到本地"""
    if interval != "1d":
        raise HTTPException(status_code=400, detail="仅支持日线 K 线（interval=1d）")
    if start and end and start > end:
        raise HTTPException(400, "开始日期不能晚于结束日期")

    bars = _ensure_stock_and_sync(code, start, end, session)
    return {"count": len(bars)}
