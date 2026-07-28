"""基于本地 SQLite 缓存的首板策略数据提供层（回测用）。

数据来自每日 cron 与回填脚本落库的 bar / limit_up_daily / dragon_tiger_daily /
marketdailystat，不回源 Tushare，因此长区间回测不受实时拉取的 15 天限制。
"""

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd
from sqlmodel import Session, select

from ..models import Bar, DragonTigerDaily, LimitUpDaily, MarketDailyStat
from ..strategies.piglet_provider import PigletDataProvider


class LocalPigletProvider(PigletDataProvider):
    """读本地缓存表的 PigletDataProvider 实现。"""

    def __init__(self, session: Session):
        self.session = session
        self._trade_dates_cache: Optional[List[date]] = None
        self._bars_cache: Dict[Tuple[frozenset, frozenset], list] = {}

    # ==================== 交易日历 ====================

    def _all_trade_dates(self) -> List[date]:
        if self._trade_dates_cache is None:
            self._trade_dates_cache = list(
                self.session.exec(
                    select(MarketDailyStat.stat_date).order_by(MarketDailyStat.stat_date)
                ).all()
            )
        return self._trade_dates_cache

    def get_trade_dates(self, end_date: date, n: int) -> List[date]:
        dates = [d for d in self._all_trade_dates() if d <= end_date]
        return dates[-n:]

    def get_trade_dates_in_range(self, start_date: date, end_date: date) -> List[date]:
        return [d for d in self._all_trade_dates() if start_date <= d <= end_date]

    # ==================== 涨跌停 ====================

    def get_limit_list(self, d: date) -> pd.DataFrame:
        rows = self.session.exec(
            select(LimitUpDaily).where(LimitUpDaily.trade_date == d)
        ).all()
        # 策略只使用 ts_code / limit / close 三列；
        # stock_code 为纯数字、无 "." 后缀，_ts_code_to_code 原样返回，行为一致
        return pd.DataFrame(
            [{"ts_code": r.stock_code, "limit": r.limit_type, "close": r.close} for r in rows]
        )

    # ==================== 日线行情 ====================

    def _query_bars(self, trade_dates: List[date], codes: Set[str]) -> List[Bar]:
        key = (frozenset(trade_dates), frozenset(codes))
        if key in self._bars_cache:
            return self._bars_cache[key]
        ts_list = [datetime(d.year, d.month, d.day) for d in trade_dates]
        rows = self.session.exec(
            select(Bar).where(
                Bar.interval == "1d",
                Bar.stock_code.in_(codes),
                Bar.timestamp.in_(ts_list),
            )
        ).all()
        self._bars_cache[key] = rows
        return rows

    def get_lows_and_close(
        self, trade_dates: List[date], codes: Set[str]
    ) -> Tuple[Dict[Tuple[str, date], float], Dict[str, float]]:
        low_map: Dict[Tuple[str, date], float] = {}
        latest_close_map: Dict[str, float] = {}
        if not trade_dates or not codes:
            return low_map, latest_close_map
        last_ts = datetime(*trade_dates[-1].timetuple()[:3])
        for bar in self._query_bars(trade_dates, codes):
            d = bar.timestamp.date()
            low_map[(bar.stock_code, d)] = bar.low
            if bar.timestamp == last_ts:
                latest_close_map[bar.stock_code] = bar.close
        return low_map, latest_close_map

    def get_daily_ohlc(self, code: str, d: date) -> Optional[Dict[str, float]]:
        ts = datetime(d.year, d.month, d.day)
        bar = self.session.exec(
            select(Bar).where(
                Bar.interval == "1d",
                Bar.stock_code == code,
                Bar.timestamp == ts,
            ).limit(1)
        ).first()
        if bar is None:
            return None
        return {
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "vol": bar.volume,
            # Bar 表不存成交额；回测引擎只使用 open/close，这里补 0 占位
            "amount": 0.0,
        }

    # ==================== 龙虎榜 ====================

    def get_top_list_net(self, trade_dates: List[date], codes: Set[str]) -> Dict[str, float]:
        if not trade_dates or not codes:
            return {}
        rows = self.session.exec(
            select(DragonTigerDaily).where(
                DragonTigerDaily.trade_date.in_(trade_dates),
                DragonTigerDaily.stock_code.in_(codes),
            )
        ).all()
        net: Dict[str, float] = {}
        for r in rows:
            if r.net_amount is not None:
                net[r.stock_code] = net.get(r.stock_code, 0.0) + r.net_amount
        return net


def local_coverage(session: Session, start_date: date, end_date: date) -> bool:
    """本地缓存是否覆盖 [start_date, end_date] 的回测数据（K线 + 涨停明细 + 交易日历）。"""
    from sqlalchemy import func

    bar_min, bar_max = session.exec(
        select(func.min(Bar.timestamp), func.max(Bar.timestamp)).where(Bar.interval == "1d")
    ).first() or (None, None)
    if bar_min is None or bar_max is None:
        return False
    limit_min = session.exec(select(func.min(LimitUpDaily.trade_date))).first()
    cal_min = session.exec(select(func.min(MarketDailyStat.stat_date))).first()
    cal_max = session.exec(select(func.max(MarketDailyStat.stat_date))).first()
    if limit_min is None or cal_min is None or cal_max is None:
        return False
    return (
        bar_min.date() <= start_date
        and bar_max.date() >= end_date
        and limit_min <= start_date
        and cal_min <= start_date
        and cal_max >= end_date
    )
