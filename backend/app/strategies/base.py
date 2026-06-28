from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from sqlmodel import Session


@dataclass
class StockPick:
    """选股结果条目。"""

    code: str
    name: str
    score: float
    buy_price: float
    reason: str
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "score": self.score,
            "buy_price": self.buy_price,
            "reason": self.reason,
            "extra": self.raw_data,
        }


class StrategyBase(ABC):
    """选股策略基类。所有策略需继承此类并通过 @register_strategy 注册。"""

    strategy_id: str = ""
    strategy_name: str = ""
    description: str = ""

    @abstractmethod
    def select(self, trade_date: date, session: Session) -> List[StockPick]:
        """执行选股，返回候选列表（策略内部完成过滤和评分归一化）。"""
        pass

    def supports_date(self, trade_date: date) -> bool:
        """策略是否支持指定日期。默认支持非未来日期。"""
        from datetime import date as dt_date

        return trade_date <= dt_date.today()


_STRATEGY_REGISTRY: Dict[str, type[StrategyBase]] = {}


def register_strategy(cls: type[StrategyBase]) -> type[StrategyBase]:
    """策略注册装饰器。"""
    if not cls.strategy_id:
        raise ValueError(f"策略 {cls.__name__} 未设置 strategy_id")
    _STRATEGY_REGISTRY[cls.strategy_id] = cls
    return cls


def get_strategy(strategy_id: str) -> Optional[type[StrategyBase]]:
    return _STRATEGY_REGISTRY.get(strategy_id)


def list_strategies() -> List[Dict[str, str]]:
    return [
        {"id": cls.strategy_id, "name": cls.strategy_name, "description": cls.description}
        for cls in _STRATEGY_REGISTRY.values()
    ]
