import json
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlmodel import Session, delete, select

from ..models import StrategyPickCache
from ..strategies.base import StockPick, get_strategy, list_strategies


class StrategyService:
    """策略选股服务：执行选股、缓存与持久化。"""

    CACHE_TTL_HOURS = 4

    def get_strategies(self) -> List[Dict[str, str]]:
        return list_strategies()

    def run_strategy(
        self,
        strategy_id: str,
        trade_date: date,
        session: Session,
        force_refresh: bool = False,
    ) -> List[StockPick]:
        """执行选股。缓存已禁用，每次都实时计算。"""
        strategy_cls = get_strategy(strategy_id)
        if strategy_cls is None:
            raise ValueError(f"策略 {strategy_id} 不存在")

        strategy = strategy_cls()
        if not strategy.supports_date(trade_date):
            return []

        return strategy.select(trade_date, session)

    def _get_cached(
        self,
        session: Session,
        strategy_id: str,
        trade_date: date,
    ) -> Optional[List[StockPick]]:
        """读取缓存，若过期则返回 None。"""
        cache = session.exec(
            select(StrategyPickCache)
            .where(StrategyPickCache.strategy_id == strategy_id)
            .where(StrategyPickCache.trade_date == trade_date)
            .order_by(StrategyPickCache.created_at.desc())
        ).first()

        if cache is None:
            return None

        age_hours = (datetime.utcnow() - cache.created_at).total_seconds() / 3600
        if age_hours > self.CACHE_TTL_HOURS:
            return None

        try:
            data = json.loads(cache.data_json)
            return [StockPick(**item) for item in data]
        except Exception:
            return None

    def _save_cache(
        self,
        session: Session,
        strategy_id: str,
        trade_date: date,
        picks: List[StockPick],
    ) -> None:
        """写入或更新缓存。先删除旧记录，避免唯一约束冲突。"""
        session.exec(
            delete(StrategyPickCache)
            .where(StrategyPickCache.strategy_id == strategy_id)
            .where(StrategyPickCache.trade_date == trade_date)
        )
        session.flush()

        cache = StrategyPickCache(
            strategy_id=strategy_id,
            trade_date=trade_date,
            data_json=json.dumps([p.to_dict() for p in picks], ensure_ascii=False, default=str),
        )
        session.add(cache)
        session.commit()

    def get_latest_trade_date(self, session: Session) -> Optional[date]:
        """从已同步的日线行情中获取最近交易日。"""
        from ..models import StockDailyQuote

        quote = session.exec(
            select(StockDailyQuote).order_by(StockDailyQuote.trade_date.desc())
        ).first()
        return quote.trade_date if quote else None
