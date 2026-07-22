from datetime import date, datetime
from typing import List, Optional
import pandas as pd
import tushare as ts

from ..config import settings
from ..models import Stock, Bar, StockDailyQuote
from sqlmodel import Session, select


class TushareStockService:
    """基于 Tushare 的股票数据服务"""

    def _get_tushare_pro(self):
        """懒加载 Tushare Pro 接口"""
        if not hasattr(self, "_tushare_pro") or self._tushare_pro is None:
            token = settings.tushare_token
            if not token:
                raise RuntimeError("Tushare token 未配置，请检查 /etc/kimi/stocks/base.conf 或 TUSHARE_TOKEN 环境变量")
            self._tushare_pro = ts.pro_api(token)
        return self._tushare_pro

    @staticmethod
    def _code_to_ts_code(code: str) -> Optional[str]:
        """将纯数字代码转换为 Tushare ts_code"""
        # 沪市：60/68/69/90 开头
        if code.startswith(("6", "90")):
            return f"{code}.SH"
        # 深市：00/00/20/30 开头
        if code.startswith(("0", "2", "3")):
            return f"{code}.SZ"
        # 北交所：4/8/920 开头
        if code.startswith(("4", "8", "920")):
            return f"{code}.BJ"
        return None

    @staticmethod
    def _ts_code_to_code(ts_code: str) -> str:
        """将 Tushare ts_code 转换为纯数字代码"""
        return ts_code.split(".")[0] if ts_code else ""

    @staticmethod
    def _safe_parse_date(value) -> Optional[date]:
        """安全解析 YYYYMMDD 日期字符串"""
        if value is None or pd.isna(value):
            return None
        s = str(value).strip()
        if not s or s == "None":
            return None
        try:
            return datetime.strptime(s, "%Y%m%d").date()
        except Exception:
            return None

    @staticmethod
    def _fetch_all_pages(pro, api_name: str, **kwargs) -> pd.DataFrame:
        """分页获取 Tushare 数据（每次最多 5000 条）"""
        frames = []
        offset = 0
        limit = 5000
        while True:
            try:
                df = getattr(pro, api_name)(offset=offset, limit=limit, **kwargs)
            except Exception:
                break
            if df is None or df.empty:
                break
            frames.append(df)
            offset += len(df)
            if len(df) < limit:
                break
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def fetch_stock_list(self) -> List[Stock]:
        """从 Tushare stock_basic 获取 A 股基础信息"""
        pro = self._get_tushare_pro()
        df = pro.stock_basic(
            exchange="",
            list_status="",
            fields="ts_code,name,industry,list_date,exchange",
        )
        if df is None or df.empty:
            return []

        stocks = []
        for _, row in df.iterrows():
            ts_code = str(row.get("ts_code", "")).strip()
            code = self._ts_code_to_code(ts_code)
            if not code:
                continue
            name = str(row.get("name", "")).strip().replace(" ", "")
            if not name:
                continue
            exchange = str(row.get("exchange", "")).strip().upper()
            if not exchange:
                exchange = self._infer_exchange(code)
            else:
                exchange = self._normalize_exchange(exchange)
            industry = str(row.get("industry", "")).strip() or None
            list_date = self._safe_parse_date(row.get("list_date"))

            stocks.append(
                Stock(
                    code=code,
                    name=name,
                    market="A股",
                    exchange=exchange,
                    industry=industry,
                    list_date=list_date,
                    updated_at=datetime.utcnow(),
                )
            )
        return stocks

    def ensure_stock_exists(self, code: str, session: Session) -> Stock:
        """如果股票不存在，从 Tushare 拉取基础信息并创建"""
        stock = session.exec(select(Stock).where(Stock.code == code)).first()
        if stock:
            return stock

        pro = self._get_tushare_pro()
        ts_code = self._code_to_ts_code(code)
        if not ts_code:
            raise ValueError(f"无法识别股票代码 {code}")

        df = pro.stock_basic(ts_code=ts_code, fields="ts_code,name,industry,list_date,exchange")
        if df is None or df.empty:
            raise ValueError(f"无法从 Tushare 找到股票 {code}")

        row = df.iloc[0]
        name = str(row.get("name", "")).strip().replace(" ", "")
        exchange = str(row.get("exchange", "")).strip().upper()
        if not exchange:
            exchange = self._infer_exchange(code)
        else:
            exchange = self._normalize_exchange(exchange)
        industry = str(row.get("industry", "")).strip() or None
        list_date = self._safe_parse_date(row.get("list_date"))

        stock = Stock(
            code=code,
            name=name,
            market="A股",
            exchange=exchange,
            industry=industry,
            list_date=list_date,
            updated_at=datetime.utcnow(),
        )
        session.add(stock)
        session.commit()
        session.refresh(stock)
        return stock

    @staticmethod
    def _to_float(value, multiplier: float = 1.0) -> Optional[float]:
        """将 pandas 数值安全转换为 float，处理 NaN/None"""
        if value is None or pd.isna(value):
            return None
        try:
            result = float(value) * multiplier
            if pd.isna(result):
                return None
            return result
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _infer_exchange(code: str) -> str:
        if code.startswith(("6", "68", "88", "89", "90")):
            return "SH"
        if code.startswith(("0", "3", "2")):
            return "SZ"
        if code.startswith(("4", "8", "43", "83", "87", "920")):
            return "BJ"
        return "SZ"

    @staticmethod
    def _normalize_exchange(exchange: str) -> str:
        """将 Tushare 交易所标识转换为本系统使用的 SH / SZ / BJ"""
        mapping = {"SSE": "SH", "SZSE": "SZ", "BSE": "BJ"}
        return mapping.get(exchange.upper(), exchange.upper())

    def fetch_daily_quotes(self, trade_date: date) -> List[StockDailyQuote]:
        """获取指定交易日的全市场行情（daily + daily_basic）"""
        pro = self._get_tushare_pro()
        date_str = trade_date.strftime("%Y%m%d")

        df_daily = self._fetch_all_pages(pro, "daily", trade_date=date_str)
        df_basic = self._fetch_all_pages(pro, "daily_basic", trade_date=date_str)

        if df_daily.empty and df_basic.empty:
            return []

        if df_daily.empty:
            df = df_basic.copy()
        elif df_basic.empty:
            df = df_daily.copy()
        else:
            df = df_daily.merge(df_basic, on="ts_code", how="outer", suffixes=("", "_basic"))

        quotes = []
        for _, row in df.iterrows():
            ts_code = str(row.get("ts_code", "")).strip()
            code = self._ts_code_to_code(ts_code)
            if not code:
                continue

            quotes.append(
                StockDailyQuote(
                    stock_code=code,
                    trade_date=trade_date,
                    close=self._to_float(row.get("close")),
                    change_pct=self._to_float(row.get("pct_chg")),
                    amount=self._to_float(row.get("amount"), 1000),
                    turnover_rate=self._to_float(row.get("turnover_rate")),
                    turnover_rate_f=self._to_float(row.get("turnover_rate_f")),
                    float_mv=self._to_float(row.get("circ_mv"), 10000),
                    total_mv=self._to_float(row.get("total_mv"), 10000),
                    pe=self._to_float(row.get("pe")),
                    pe_ttm=self._to_float(row.get("pe_ttm")),
                    pb=self._to_float(row.get("pb")),
                    ps=self._to_float(row.get("ps")),
                    ps_ttm=self._to_float(row.get("ps_ttm")),
                    dv_ratio=self._to_float(row.get("dv_ratio")),
                    dv_ttm=self._to_float(row.get("dv_ttm")),
                    updated_at=datetime.utcnow(),
                )
            )
        return quotes

    def fetch_daily_bars(
        self,
        code: str,
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> List[Bar]:
        """获取指定股票的日线 K 线"""
        pro = self._get_tushare_pro()
        ts_code = self._code_to_ts_code(code)
        if not ts_code:
            return []

        start_str = start.strftime("%Y%m%d") if start else "19700101"
        end_str = end.strftime("%Y%m%d") if end else date.today().strftime("%Y%m%d")

        df = self._fetch_all_pages(
            pro,
            "daily",
            ts_code=ts_code,
            start_date=start_str,
            end_date=end_str,
        )
        if df.empty:
            return []

        bars = []
        for _, row in df.iterrows():
            bars.append(
                Bar(
                    stock_code=code,
                    timestamp=datetime.strptime(str(row["trade_date"]), "%Y%m%d"),
                    interval="1d",
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["vol"]) * 100,
                    adjusted=False,
                )
            )
        return bars

    def fetch_daily_quotes_for_stock(
        self,
        code: str,
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> List[StockDailyQuote]:
        """获取指定股票区间内的 daily + daily_basic 行情（包含成交额与换手率等）。"""
        pro = self._get_tushare_pro()
        ts_code = self._code_to_ts_code(code)
        if not ts_code:
            return []

        start_str = start.strftime("%Y%m%d") if start else "19700101"
        end_str = end.strftime("%Y%m%d") if end else date.today().strftime("%Y%m%d")

        df_daily = self._fetch_all_pages(
            pro,
            "daily",
            ts_code=ts_code,
            start_date=start_str,
            end_date=end_str,
        )
        df_basic = self._fetch_all_pages(
            pro,
            "daily_basic",
            ts_code=ts_code,
            start_date=start_str,
            end_date=end_str,
        )

        if df_daily.empty and df_basic.empty:
            return []

        if df_daily.empty:
            df = df_basic.copy()
        elif df_basic.empty:
            df = df_daily.copy()
        else:
            df = df_daily.merge(df_basic, on="ts_code", how="outer", suffixes=("", "_basic"))

        quotes = []
        for _, row in df.iterrows():
            trade_date = self._safe_parse_date(row.get("trade_date"))
            if not trade_date:
                continue
            quotes.append(
                StockDailyQuote(
                    stock_code=code,
                    trade_date=trade_date,
                    close=self._to_float(row.get("close")),
                    change_pct=self._to_float(row.get("pct_chg")),
                    amount=self._to_float(row.get("amount"), 1000),
                    turnover_rate=self._to_float(row.get("turnover_rate")),
                    turnover_rate_f=self._to_float(row.get("turnover_rate_f")),
                    float_mv=self._to_float(row.get("circ_mv"), 10000),
                    total_mv=self._to_float(row.get("total_mv"), 10000),
                    pe=self._to_float(row.get("pe")),
                    pe_ttm=self._to_float(row.get("pe_ttm")),
                    pb=self._to_float(row.get("pb")),
                    ps=self._to_float(row.get("ps")),
                    ps_ttm=self._to_float(row.get("ps_ttm")),
                    dv_ratio=self._to_float(row.get("dv_ratio")),
                    dv_ttm=self._to_float(row.get("dv_ttm")),
                    updated_at=datetime.utcnow(),
                )
            )
        return quotes
