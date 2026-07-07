from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd
import tushare as ts

from ..config import settings
from ..services.tushare_stock_service import TushareStockService


class PigletDataProvider(ABC):
    """首板不破策略的数据提供层抽象。

    将策略与数据源解耦，便于线上实时选股与离线回测使用不同的数据源。
    """

    @abstractmethod
    def get_trade_dates(self, end_date: date, n: int) -> List[date]:
        """返回截至 end_date（含）的最近 n 个交易日，升序。"""
        ...

    @abstractmethod
    def get_trade_dates_in_range(self, start_date: date, end_date: date) -> List[date]:
        """返回 [start_date, end_date] 区间内的交易日，升序。"""
        ...

    @abstractmethod
    def get_limit_list(self, d: date) -> pd.DataFrame:
        """获取指定日期的涨跌停名单。"""
        ...

    @abstractmethod
    def get_lows_and_close(
        self, trade_dates: List[date], codes: Set[str]
    ) -> Tuple[Dict[Tuple[str, date], float], Dict[str, float]]:
        """获取指定交易日、指定股票的最低价，以及最近交易日的收盘价。"""
        ...

    @abstractmethod
    def get_top_list_net(self, trade_dates: List[date], codes: Set[str]) -> Dict[str, float]:
        """获取指定交易日窗口内，指定股票的龙虎榜净买额合计。"""
        ...

    @abstractmethod
    def get_daily_ohlc(self, code: str, d: date) -> Optional[Dict[str, float]]:
        """获取单只股票指定交易日的 OHLCV。

        返回字典：open/high/low/close/amount，未找到返回 None。
        """
        ...


class TusharePigletProvider(PigletDataProvider):
    """基于 Tushare Pro 的数据提供层，内部带运行级缓存减少重复请求。"""

    def __init__(self):
        self._tushare_pro = None
        self._trade_dates_cache: Dict[Tuple[date, date], List[date]] = {}
        self._limit_list_cache: Dict[date, pd.DataFrame] = {}
        self._daily_cache: Dict[date, pd.DataFrame] = {}
        self._top_list_cache: Dict[date, pd.DataFrame] = {}

    def _get_tushare_pro(self):
        if self._tushare_pro is None:
            token = settings.tushare_token
            if not token:
                raise RuntimeError("Tushare token 未配置")
            self._tushare_pro = ts.pro_api(token)
        return self._tushare_pro

    @staticmethod
    def _safe_float(value, default: Optional[float] = None) -> Optional[float]:
        if value is None or pd.isna(value):
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def _ts_code_to_code(self, ts_code: str) -> str:
        return TushareStockService._ts_code_to_code(ts_code)

    def get_trade_dates(self, end_date: date, n: int) -> List[date]:
        key = (end_date, n)
        if key in self._trade_dates_cache:
            return self._trade_dates_cache[key]

        start = end_date - timedelta(days=n * 3 + 10)
        dates = self._fetch_trade_dates_range(start, end_date)
        result = dates[-n:] if len(dates) >= n else dates
        self._trade_dates_cache[key] = result
        return result

    def get_trade_dates_in_range(self, start_date: date, end_date: date) -> List[date]:
        key = (start_date, end_date)
        if key in self._trade_dates_cache:
            return self._trade_dates_cache[key]

        result = self._fetch_trade_dates_range(start_date, end_date)
        self._trade_dates_cache[key] = result
        return result

    def _fetch_trade_dates_range(self, start: date, end: date) -> List[date]:
        pro = self._get_tushare_pro()
        try:
            df = pro.trade_cal(
                exchange="SSE",
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                is_open="1",
            )
        except Exception:
            return []
        if df is None or df.empty:
            return []
        dates = sorted(
            datetime.strptime(str(c), "%Y%m%d").date() for c in df["cal_date"].tolist()
        )
        return dates

    def get_limit_list(self, d: date) -> pd.DataFrame:
        if d in self._limit_list_cache:
            return self._limit_list_cache[d]

        pro = self._get_tushare_pro()
        try:
            df = pro.limit_list_d(trade_date=d.strftime("%Y%m%d"))
        except Exception:
            df = pd.DataFrame()
        if df is None:
            df = pd.DataFrame()
        self._limit_list_cache[d] = df
        return df

    def get_lows_and_close(
        self, trade_dates: List[date], codes: Set[str]
    ) -> Tuple[Dict[Tuple[str, date], float], Dict[str, float]]:
        low_map: Dict[Tuple[str, date], float] = {}
        latest_close_map: Dict[str, float] = {}
        if not trade_dates:
            return low_map, latest_close_map

        last_date = trade_dates[-1]
        for d in trade_dates:
            df = self._get_daily_for_date(d)
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                code = self._ts_code_to_code(row["ts_code"])
                if code not in codes:
                    continue
                low = self._safe_float(row.get("low"))
                if low is not None:
                    low_map[(code, d)] = low
                if d == last_date:
                    close = self._safe_float(row.get("close"))
                    if close is not None:
                        latest_close_map[code] = close
        return low_map, latest_close_map

    def get_top_list_net(self, trade_dates: List[date], codes: Set[str]) -> Dict[str, float]:
        net: Dict[str, float] = {}
        for d in trade_dates:
            df = self._get_top_list_for_date(d)
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                code = self._ts_code_to_code(row["ts_code"])
                if code not in codes:
                    continue
                amt = self._safe_float(row.get("net_amount"))
                if amt is not None:
                    net[code] = net.get(code, 0.0) + amt
        return net

    def get_daily_ohlc(self, code: str, d: date) -> Optional[Dict[str, float]]:
        df = self._get_daily_for_date(d)
        if df is None or df.empty:
            return None

        # 复用 ts_code 转换逻辑
        ts_codes = set()
        for _, row in df.iterrows():
            c = self._ts_code_to_code(row["ts_code"])
            if c == code:
                ts_codes.add(row["ts_code"])

        if not ts_codes:
            return None

        # 同一代码理论上只有一行
        rows = df[df["ts_code"].isin(ts_codes)]
        if rows.empty:
            return None

        row = rows.iloc[0]
        result = {}
        for field in ("open", "high", "low", "close", "amount", "vol"):
            value = self._safe_float(row.get(field))
            if value is None:
                return None
            result[field] = value
        return result

    def _get_daily_for_date(self, d: date) -> Optional[pd.DataFrame]:
        if d in self._daily_cache:
            return self._daily_cache[d]

        pro = self._get_tushare_pro()
        try:
            df = pro.daily(trade_date=d.strftime("%Y%m%d"))
        except Exception:
            df = pd.DataFrame()
        if df is None:
            df = pd.DataFrame()
        self._daily_cache[d] = df
        return df

    def _get_top_list_for_date(self, d: date) -> Optional[pd.DataFrame]:
        if d in self._top_list_cache:
            return self._top_list_cache[d]

        pro = self._get_tushare_pro()
        try:
            df = pro.top_list(trade_date=d.strftime("%Y%m%d"))
        except Exception:
            df = pd.DataFrame()
        if df is None:
            df = pd.DataFrame()
        self._top_list_cache[d] = df
        return df
