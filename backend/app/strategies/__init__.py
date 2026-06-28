"""策略包：自动发现并注册所有策略模块。"""

import importlib
import pkgutil

from .base import StrategyBase, get_strategy, list_strategies, register_strategy  # noqa: F401


def _auto_discover() -> None:
    """自动发现 backend/app/strategies/ 目录下的策略模块。"""
    for _, name, _ in pkgutil.iter_modules(__path__):
        if name in ("base", "filters"):
            continue
        importlib.import_module(f".{name}", __package__)


_auto_discover()
