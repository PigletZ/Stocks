from datetime import date
from typing import List, Optional

import numpy as np
import pandas as pd
import tushare as ts
from sqlmodel import Session

from ..config import settings
from ..services.tushare_stock_service import TushareStockService
from ..strategies.base import StockPick, StrategyBase, register_strategy
from ..strategies.filters import apply_base_filters, normalize_scores, sort_and_top


@register_strategy
class DragonTigerStrategy(StrategyBase):
    """龙虎榜游资追踪选股策略。

    基于当日龙虎榜数据，跟随游资净买入，聚焦主板小市值标的。
    """

    strategy_id = "dragon-tiger"
    strategy_name = "龙虎榜游资追踪"
    description = "基于当日龙虎榜数据，跟随游资净买入，聚焦主板小市值标的。"

    def __init__(self):
        self._tushare_pro = None

    def _get_tushare_pro(self):
        """懒加载 Tushare Pro 接口。"""
        if self._tushare_pro is None:
            token = settings.tushare_token
            if not token:
                raise RuntimeError("Tushare token 未配置")
            self._tushare_pro = ts.pro_api(token)
        return self._tushare_pro

    def select(self, trade_date: date, session: Session) -> List[StockPick]:
        df = self._fetch_top_list(trade_date)
        if df is None or df.empty:
            return []

        # 净买入为正
        df = df[pd.to_numeric(df.get("net_amount"), errors="coerce").fillna(0) > 0].copy()
        if df.empty:
            return []

        df["code"] = df["ts_code"].apply(TushareStockService._ts_code_to_code)

        # 基础过滤：ST、科创板、创业板、北交所、次新股
        codes = df["code"].dropna().unique().tolist()
        filtered_codes = apply_base_filters(codes, trade_date, session)
        df = df[df["code"].isin(filtered_codes)].copy()
        if df.empty:
            return []

        # 流通市值过滤：float_values 单位为元
        df["float_mv"] = pd.to_numeric(df.get("float_values"), errors="coerce")
        df = df[(df["float_mv"].isna()) | (df["float_mv"] <= 200e8)].copy()
        if df.empty:
            return []

        # 计算评分
        df["net_rate"] = pd.to_numeric(df.get("net_rate"), errors="coerce").fillna(0)
        df["pct_change"] = pd.to_numeric(df.get("pct_change"), errors="coerce").fillna(0)
        df["amount"] = pd.to_numeric(df.get("amount"), errors="coerce").fillna(0)

        # 成交额因子：对数处理，降低极端值影响
        df["amount_factor"] = np.log(df["amount"] + 1)

        df["score"] = (
            df["net_rate"] * 0.4 +
            df["pct_change"] * 0.3 +
            df["amount_factor"] * 0.3
        )

        # 同一只股票可能因多次上榜出现多条记录，保留评分最高的一条
        df = df.sort_values("score", ascending=False).drop_duplicates(subset=["code"], keep="first")

        picks: List[StockPick] = []
        for _, row in df.iterrows():
            code = str(row["code"])
            name = str(row.get("name", ""))
            price = self._safe_float(row.get("close"), 0.0) or 0.0
            score = self._safe_float(row.get("score"), 0.0) or 0.0
            net_rate = self._safe_float(row.get("net_rate"), 0.0) or 0.0
            float_mv = self._safe_float(row.get("float_mv"), None)

            float_mv_text = f"{float_mv / 1e8:.1f}亿" if float_mv else "未知"
            reason = f"龙虎榜净买占比 {net_rate:.2f}%，主板小市值（流通市值 {float_mv_text}）"

            picks.append(
                StockPick(
                    code=code,
                    name=name,
                    score=score,
                    buy_price=price,
                    reason=reason,
                    raw_data={"net_rate": net_rate, "float_mv": float_mv},
                )
            )

        normalize_scores(picks)
        return sort_and_top(picks, 10)

    def _fetch_top_list(self, trade_date: date) -> pd.DataFrame:
        """获取指定交易日的龙虎榜数据。"""
        try:
            date_str = trade_date.strftime("%Y%m%d")
            df = self._get_tushare_pro().top_list(trade_date=date_str)
            if df is None or df.empty:
                return pd.DataFrame()
            return df
        except Exception:
            return pd.DataFrame()

    @staticmethod
    def _safe_float(value, default: Optional[float] = None) -> Optional[float]:
        if value is None or pd.isna(value):
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
