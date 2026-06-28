from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from ..database import get_session
from ..services.strategy_service import StrategyService

router = APIRouter()


def _parse_date(d: Optional[str]) -> date:
    if d:
        return datetime.strptime(d, "%Y-%m-%d").date()
    return date.today()


@router.get("")
def list_strategies():
    """列出所有可用策略。"""
    service = StrategyService()
    return service.get_strategies()


@router.get("/{strategy_id}/picks")
def get_strategy_picks(
    strategy_id: str,
    trade_date: Optional[str] = Query(None, description="日期 YYYY-MM-DD，默认今天"),
    force_refresh: bool = Query(False, description="强制刷新，忽略缓存"),
    session: Session = Depends(get_session),
):
    """执行指定策略选股，返回 Top10 结果。"""
    service = StrategyService()
    target_date = _parse_date(trade_date)

    # 若目标日期无行情数据（非交易日 / 当日数据未同步），回退到最近交易日
    latest = service.get_latest_trade_date(session)
    if latest and target_date > latest:
        target_date = latest

    try:
        picks = service.run_strategy(strategy_id, target_date, session, force_refresh)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # 默认返回 Top10；piglet 为"列出全部命中"的复盘型策略，不截断
    items = picks if strategy_id == "piglet" else picks[:10]

    return {
        "strategy_id": strategy_id,
        "trade_date": target_date.isoformat(),
        "count": len(items),
        "items": [p.to_dict() for p in items],
    }
