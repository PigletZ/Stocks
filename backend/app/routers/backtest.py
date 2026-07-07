from datetime import date, datetime
from typing import Any, Dict, List, Optional

import json
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..database import get_session
from ..models import BacktestTrade, Stock
from ..services.backtest_service import BacktestService

router = APIRouter()


class BacktestRequest(BaseModel):
    strategy_id: str = Field(default="piglet", description="策略 ID")
    start_date: str = Field(..., description="开始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD")
    window_days: int = Field(default=5, ge=2, le=60, description="选股回看窗口天数")
    hold_days: int = Field(default=5, ge=1, le=60, description="买入后持有天数")
    max_positions: int = Field(default=5, ge=1, le=50, description="最大同时持仓数")
    max_per_day: int = Field(default=2, ge=1, le=20, description="每个信号日最多新增仓位")
    require_dragon: bool = Field(default=False, description="是否只交易有龙虎榜游资介入的股票")
    initial_capital: float = Field(default=100000.0, gt=0, description="初始资金")
    commission_rate: float = Field(default=0.0003, ge=0, le=0.1, description="佣金率（双边）")


def _parse_date(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()


@router.post("/run")
def run_backtest(
    req: BacktestRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """创建回测任务并在后台运行，立即返回 run_id 用于轮询。"""
    service = BacktestService()
    params = service.parse_params(req.model_dump())
    start_date = _parse_date(req.start_date)
    end_date = _parse_date(req.end_date)

    error = service.validate_date_range(start_date, end_date)
    if error:
        raise HTTPException(status_code=400, detail=error)

    try:
        run = service.create_run(
            strategy_id=req.strategy_id,
            start_date=start_date,
            end_date=end_date,
            params=params,
            session=session,
        )
        background_tasks.add_task(service.execute_backtest, run.id, params)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建回测任务失败: {e}")

    return {"run_id": run.id, "status": "pending"}


@router.get("/{run_id}")
def get_backtest_result(
    run_id: int,
    session: Session = Depends(get_session),
):
    """查询回测结果，包含指标、权益曲线、交易明细。"""
    service = BacktestService()
    run = service.get_backtest(run_id, session)
    if not run:
        raise HTTPException(status_code=404, detail="回测记录不存在")

    trades = session.exec(
        select(BacktestTrade).where(BacktestTrade.backtest_run_id == run_id)
    ).all()

    # 批量查询股票名称
    stock_codes = list({t.stock_code for t in trades})
    name_map = {}
    if stock_codes:
        stocks = session.exec(select(Stock).where(Stock.code.in_(stock_codes))).all()
        name_map = {s.code: s.name for s in stocks}

    return {
        "id": run.id,
        "strategy_id": run.strategy_id,
        "start_date": run.start_date.isoformat(),
        "end_date": run.end_date.isoformat(),
        "initial_capital": run.initial_capital,
        "params": json.loads(run.params_json) if run.params_json else {},
        "status": run.status,
        "error_message": run.error_message,
        "metrics": json.loads(run.metrics_json) if run.metrics_json else {},
        "equity_curve": json.loads(run.equity_curve_json) if run.equity_curve_json else [],
        "trades": [
            {
                "id": t.id,
                "stock_code": t.stock_code,
                "stock_name": name_map.get(t.stock_code, t.stock_code),
                "direction": t.direction,
                "quantity": t.quantity,
                "price": t.price,
                "amount": t.amount,
                "commission": t.commission,
                "trade_date": t.trade_date.isoformat(),
                "signal_date": t.signal_date.isoformat() if t.signal_date else None,
                "hold_days": t.hold_days,
                "pnl": t.pnl,
                "raw": json.loads(t.raw_json) if t.raw_json else {},
            }
            for t in trades
        ],
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@router.get("")
def list_backtests(
    strategy_id: Optional[str] = Query(None, description="按策略 ID 过滤"),
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
    session: Session = Depends(get_session),
):
    """列出历史回测记录。"""
    service = BacktestService()
    runs = service.list_backtests(session, strategy_id=strategy_id, limit=limit)
    return [
        {
            "id": r.id,
            "strategy_id": r.strategy_id,
            "start_date": r.start_date.isoformat(),
            "end_date": r.end_date.isoformat(),
            "initial_capital": r.initial_capital,
            "params": json.loads(r.params_json) if r.params_json else {},
            "status": r.status,
            "error_message": r.error_message,
            "metrics": json.loads(r.metrics_json) if r.metrics_json else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in runs
    ]
