from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select
from typing import List, Optional
from datetime import date, datetime

from ..database import get_session
from ..models import Holding, WatchlistGroup, WatchlistItem, Stock, StockDailyQuote
from ..services.journal_service import JournalService

router = APIRouter()


def _get_or_create_default_group(session: Session) -> WatchlistGroup:
    group = session.exec(
        select(WatchlistGroup).where(WatchlistGroup.name == "默认分组")
    ).first()
    if group:
        return group
    group = WatchlistGroup(name="默认分组", sort_order=0)
    session.add(group)
    session.commit()
    session.refresh(group)
    return group


def _get_latest_trade_date(session: Session) -> Optional[date]:
    quote = session.exec(
        select(StockDailyQuote).order_by(StockDailyQuote.trade_date.desc())
    ).first()
    return quote.trade_date if quote else None


def _quote_to_dict(quote: Optional[StockDailyQuote]) -> dict:
    if not quote:
        return {
            "quote_date": None,
            "close": None,
            "change_pct": None,
            "amount": None,
            "turnover_rate": None,
            "float_mv": None,
            "total_mv": None,
            "pe": None,
            "pb": None,
        }
    return {
        "quote_date": quote.trade_date.isoformat(),
        "close": quote.close,
        "change_pct": quote.change_pct,
        "amount": quote.amount,
        "turnover_rate": quote.turnover_rate,
        "float_mv": quote.float_mv,
        "total_mv": quote.total_mv,
        "pe": quote.pe,
        "pb": quote.pb,
    }


@router.get("/groups")
def list_watchlist_groups(session: Session = Depends(get_session)) -> List[dict]:
    """按分组返回自选股列表（含最新行情与持仓盈亏）

    持仓来源：交易台账 FIFO 计算优先；无台账记录时用手动录入的 holding。
    """
    latest_date = _get_latest_trade_date(session)
    pos_map = JournalService().get_position_map(session)
    manual_holdings = {h.stock_code: h for h in session.exec(select(Holding)).all()}

    groups = session.exec(
        select(WatchlistGroup).order_by(WatchlistGroup.sort_order, WatchlistGroup.created_at)
    ).all()

    def _position_dict(code: str, close: Optional[float]) -> Optional[dict]:
        if code in pos_map:
            p = pos_map[code]
            source = "journal"
        elif code in manual_holdings:
            h = manual_holdings[code]
            p = {"quantity": h.quantity, "cost_price": h.cost_price, "realized_pnl": None}
            source = "manual"
        else:
            return None
        cost = p["cost_price"]
        return {
            "quantity": p["quantity"],
            "cost_price": cost,
            "source": source,
            "unrealized_pnl": round((close - cost) * p["quantity"], 2) if close is not None else None,
            "unrealized_pct": round((close / cost - 1) * 100, 2) if close is not None and cost > 0 else None,
            "realized_pnl": p.get("realized_pnl"),
        }

    result = []
    for group in groups:
        if latest_date:
            query = (
                select(WatchlistItem, Stock, StockDailyQuote)
                .join(Stock, WatchlistItem.stock_code == Stock.code)
                .outerjoin(
                    StockDailyQuote,
                    (WatchlistItem.stock_code == StockDailyQuote.stock_code)
                    & (StockDailyQuote.trade_date == latest_date),
                )
                .where(WatchlistItem.group_id == group.id)
                .order_by(WatchlistItem.sort_order, WatchlistItem.created_at)
            )
        else:
            query = (
                select(WatchlistItem, Stock)
                .join(Stock, WatchlistItem.stock_code == Stock.code)
                .where(WatchlistItem.group_id == group.id)
                .order_by(WatchlistItem.sort_order, WatchlistItem.created_at)
            )

        rows = session.exec(query).all()

        stocks = []
        for row in rows:
            item = row[0]
            stock = row[1]
            quote = row[2] if len(row) > 2 else None
            stocks.append(
                {
                    "code": stock.code,
                    "name": stock.name,
                    "exchange": stock.exchange,
                    "industry": stock.industry,
                    "sort_order": item.sort_order,
                    "position": _position_dict(stock.code, quote.close if quote else None),
                    **_quote_to_dict(quote),
                }
            )

        result.append(
            {
                "id": group.id,
                "name": group.name,
                "sort_order": group.sort_order,
                "stocks": stocks,
            }
        )
    return result


class HoldingIn(BaseModel):
    cost_price: float
    quantity: int
    note: Optional[str] = None


@router.put("/holdings/{code}")
def upsert_holding(code: str, body: HoldingIn, session: Session = Depends(get_session)):
    """手动录入/更新持仓成本（无台账记录的股票用）"""
    if body.cost_price <= 0 or body.quantity <= 0:
        raise HTTPException(status_code=400, detail="成本价和数量必须大于 0")
    stock = session.exec(select(Stock).where(Stock.code == code)).first()
    if not stock:
        raise HTTPException(status_code=404, detail="股票不存在")

    holding = session.exec(select(Holding).where(Holding.stock_code == code)).first()
    if holding:
        holding.cost_price = body.cost_price
        holding.quantity = body.quantity
        holding.note = body.note
        holding.updated_at = datetime.utcnow()
    else:
        holding = Holding(
            stock_code=code,
            cost_price=body.cost_price,
            quantity=body.quantity,
            note=body.note,
        )
    session.add(holding)
    session.commit()
    return {"code": code, "cost_price": holding.cost_price, "quantity": holding.quantity}


@router.delete("/holdings/{code}")
def delete_holding(code: str, session: Session = Depends(get_session)):
    """删除手动持仓"""
    holding = session.exec(select(Holding).where(Holding.stock_code == code)).first()
    if not holding:
        raise HTTPException(status_code=404, detail="手动持仓不存在")
    session.delete(holding)
    session.commit()
    return {"message": "已删除"}


@router.post("/groups")
def create_group(
    name: str,
    sort_order: int = 0,
    session: Session = Depends(get_session),
):
    """创建自选分组"""
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="分组名称不能为空")

    existing = session.exec(
        select(WatchlistGroup).where(WatchlistGroup.name == name)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="分组名称已存在")

    group = WatchlistGroup(name=name, sort_order=sort_order)
    session.add(group)
    session.commit()
    session.refresh(group)
    return {"id": group.id, "name": group.name, "sort_order": group.sort_order}


@router.put("/groups/{group_id}")
def rename_group(
    group_id: int,
    name: str,
    session: Session = Depends(get_session),
):
    """重命名自选分组"""
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="分组名称不能为空")

    group = session.get(WatchlistGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="分组不存在")

    if group.name == name:
        return {"id": group.id, "name": group.name, "sort_order": group.sort_order}

    existing = session.exec(
        select(WatchlistGroup).where(WatchlistGroup.name == name)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="分组名称已存在")

    group.name = name
    session.add(group)
    session.commit()
    session.refresh(group)
    return {"id": group.id, "name": group.name, "sort_order": group.sort_order}


@router.delete("/groups/{group_id}")
def delete_group(group_id: int, session: Session = Depends(get_session)):
    """删除自选分组，组内股票移动到默认分组"""
    group = session.get(WatchlistGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="分组不存在")

    default_group = _get_or_create_default_group(session)
    items = session.exec(
        select(WatchlistItem).where(WatchlistItem.group_id == group_id)
    ).all()
    for item in items:
        item.group_id = default_group.id
        session.add(item)

    session.delete(group)
    session.commit()
    return {"message": "已删除分组，股票已移至默认分组"}


@router.get("")
def list_all_watchlist(session: Session = Depends(get_session)) -> List[dict]:
    """返回所有自选股（不分组）"""
    items = session.exec(
        select(WatchlistItem, Stock)
        .join(Stock, WatchlistItem.stock_code == Stock.code)
        .order_by(WatchlistItem.sort_order, WatchlistItem.created_at)
    ).all()
    return [
        {
            "code": stock.code,
            "name": stock.name,
            "exchange": stock.exchange,
            "group_id": item.group_id,
            "sort_order": item.sort_order,
        }
        for item, stock in items
    ]


@router.post("/{code}")
def add_to_watchlist(
    code: str,
    group_id: Optional[int] = Query(None, description="分组 ID，默认使用默认分组"),
    sort_order: int = 0,
    session: Session = Depends(get_session),
):
    """添加股票到自选股"""
    stock = session.exec(select(Stock).where(Stock.code == code)).first()
    if not stock:
        raise HTTPException(status_code=404, detail="股票不存在，请先同步股票列表")

    existing = session.exec(
        select(WatchlistItem).where(WatchlistItem.stock_code == code)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="该股票已在自选列表中")

    if group_id:
        group = session.get(WatchlistGroup, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="分组不存在")
    else:
        group = _get_or_create_default_group(session)

    item = WatchlistItem(
        stock_code=code,
        group_id=group.id,
        sort_order=sort_order,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return {"code": item.stock_code, "group_id": item.group_id}


@router.delete("/{code}")
def remove_from_watchlist(code: str, session: Session = Depends(get_session)):
    """从自选股中移除"""
    item = session.exec(
        select(WatchlistItem).where(WatchlistItem.stock_code == code)
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="自选股不存在")
    session.delete(item)
    session.commit()
    return {"message": "已移除"}


@router.put("/{code}/group")
def move_group(
    code: str,
    group_id: int,
    session: Session = Depends(get_session),
):
    """移动自选股到指定分组"""
    item = session.exec(
        select(WatchlistItem).where(WatchlistItem.stock_code == code)
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="自选股不存在")

    group = session.get(WatchlistGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="分组不存在")

    item.group_id = group.id
    session.add(item)
    session.commit()
    session.refresh(item)
    return {"code": item.stock_code, "group_id": item.group_id}
