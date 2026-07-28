from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from ..database import get_session
from ..services.screener_service import ScreenerService
from ..services.strategy_service import StrategyService

router = APIRouter()


def _parse_date(d: Optional[str]) -> date:
    if d:
        return datetime.strptime(d, "%Y-%m-%d").date()
    return date.today()


@router.get("")
def list_strategies(session: Session = Depends(get_session)):
    """列出所有可用策略（含选股器保存的自定义预设，strategy_id 为 screen:{id}）。"""
    service = StrategyService()
    strategies = service.get_strategies()
    for preset in ScreenerService().list_presets(session):
        cond_text = "、".join(
            f"{c['field']}{c['op']}{c['value']}" for c in preset["conditions"]
        )
        strategies.append({
            "id": f"screen:{preset['id']}",
            "name": f"自定义：{preset['name']}",
            "description": f"选股器预设（{cond_text}）",
        })
    return strategies


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

    if strategy_id.startswith("screen:"):
        # 选股器预设：按保存的条件执行
        screener = ScreenerService()
        try:
            preset_id = int(strategy_id.split(":", 1)[1])
        except (IndexError, ValueError):
            raise HTTPException(status_code=404, detail=f"策略 {strategy_id} 不存在")
        preset = screener.get_preset(preset_id, session)
        if not preset:
            raise HTTPException(status_code=404, detail="选股器预设不存在或已删除")
        import json
        picks = screener.run_as_picks(json.loads(preset.conditions_json), target_date, session)
    else:
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
