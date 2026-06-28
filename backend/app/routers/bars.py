from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List, Optional
from datetime import date

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
    service.ensure_stock_exists(code, session)

    bars = service.fetch_daily_bars(code, start=start, end=end)
    if not bars:
        return []

    # 删除同范围旧数据，写入新数据（简单覆盖策略）
    min_ts = min(b.timestamp for b in bars)
    max_ts = max(b.timestamp for b in bars)
    old_bars = session.exec(
        select(Bar)
        .where(Bar.stock_code == code)
        .where(Bar.interval == "1d")
        .where(Bar.timestamp >= min_ts)
        .where(Bar.timestamp <= max_ts)
    ).all()
    for old in old_bars:
        session.delete(old)

    for bar in bars:
        session.add(bar)
    session.commit()

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

    query = select(Bar).where(Bar.stock_code == code, Bar.interval == "1d")
    if start:
        query = query.where(Bar.timestamp >= start)
    if end:
        query = query.where(Bar.timestamp <= end)
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

    bars = _ensure_stock_and_sync(code, start, end, session)
    return {"count": len(bars)}
