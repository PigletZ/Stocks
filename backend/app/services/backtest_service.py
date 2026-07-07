import json
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from ..database import engine
from ..models import BacktestRun, BacktestTrade
from ..backtest.piglet_backtest import PigletBacktestEngine, PigletBacktestParams
from ..backtest.metrics import compute_backtest_metrics, equity_curve_to_dicts


class BacktestService:
    """回测服务：运行回测、持久化结果与查询。"""

    # 实时拉 Tushare 做回测时，为避免请求超时，限制最大回测区间（日历日）
    MAX_REALTIME_RANGE_DAYS = 15

    def create_run(
        self,
        strategy_id: str,
        start_date: date,
        end_date: date,
        params: PigletBacktestParams,
        session: Session,
    ) -> BacktestRun:
        """创建回测记录（状态 pending），返回 BacktestRun 实例。"""
        params_dict = {
            "window_days": params.window_days,
            "hold_days": params.hold_days,
            "max_positions": params.max_positions,
            "max_per_day": params.max_per_day,
            "require_dragon": params.require_dragon,
            "initial_capital": params.initial_capital,
            "commission_rate": params.commission_rate,
        }

        run = BacktestRun(
            strategy_id=strategy_id,
            start_date=start_date,
            end_date=end_date,
            initial_capital=params.initial_capital,
            params_json=json.dumps(params_dict, ensure_ascii=False),
            status="pending",
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        return run

    def execute_backtest(self, run_id: int, params: PigletBacktestParams) -> None:
        """在独立会话中执行回测并更新记录。用于后台任务。"""
        with Session(engine) as session:
            run = session.get(BacktestRun, run_id)
            if not run:
                return

            run.status = "running"
            session.add(run)
            session.commit()

            try:
                backtest_engine = PigletBacktestEngine(session, params)
                equity_curve, trades = backtest_engine.run(
                    run.start_date, run.end_date
                )

                metrics = compute_backtest_metrics(equity_curve, trades)

                # 保存交易明细
                for t in trades:
                    session.add(
                        BacktestTrade(
                            backtest_run_id=run.id,
                            stock_code=t["stock_code"],
                            direction=t["direction"],
                            quantity=t["quantity"],
                            price=t["price"],
                            amount=t["amount"],
                            commission=t["commission"],
                            trade_date=t["trade_date"],
                            signal_date=t.get("signal_date"),
                            hold_days=t.get("hold_days"),
                            pnl=t.get("pnl"),
                            raw_json=json.dumps(
                                t.get("raw") or {}, ensure_ascii=False, default=str
                            ),
                        )
                    )

                run.status = "completed"
                run.metrics_json = json.dumps(metrics, ensure_ascii=False)
                run.equity_curve_json = json.dumps(
                    equity_curve_to_dicts(equity_curve), ensure_ascii=False
                )
                run.completed_at = date.today()
                session.commit()
            except Exception as e:
                run.status = "failed"
                run.error_message = str(e)
                run.completed_at = date.today()
                session.commit()

    def validate_date_range(self, start_date: date, end_date: date) -> Optional[str]:
        """校验日期范围是否合法。返回错误信息或 None。"""
        if start_date > end_date:
            return "start_date 不能晚于 end_date"
        days = (end_date - start_date).days
        if days > self.MAX_REALTIME_RANGE_DAYS:
            return f"实时 Tushare 回测暂限制最大 {self.MAX_REALTIME_RANGE_DAYS} 天，当前 {days} 天"
        return None

    def get_backtest(self, run_id: int, session: Session) -> Optional[BacktestRun]:
        return session.get(BacktestRun, run_id)

    def list_backtests(
        self,
        session: Session,
        strategy_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[BacktestRun]:
        query = select(BacktestRun).order_by(BacktestRun.created_at.desc())
        if strategy_id:
            query = query.where(BacktestRun.strategy_id == strategy_id)
        return session.exec(query.limit(limit)).all()

    @staticmethod
    def parse_params(req_params: Dict[str, Any]) -> PigletBacktestParams:
        """从请求参数解析回测参数。"""
        return PigletBacktestParams(
            window_days=int(req_params.get("window_days", 5)),
            hold_days=int(req_params.get("hold_days", 5)),
            max_positions=int(req_params.get("max_positions", 5)),
            max_per_day=int(req_params.get("max_per_day", 2)),
            require_dragon=bool(req_params.get("require_dragon", False)),
            initial_capital=float(req_params.get("initial_capital", 100000)),
            commission_rate=float(req_params.get("commission_rate", 0.0003)),
        )
