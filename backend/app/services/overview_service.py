from datetime import date, datetime, timedelta
from typing import List, Dict, Optional
import logging

from sqlalchemy import func
from sqlmodel import Session, select
import pandas as pd
import tushare as ts

from ..config import settings


logger = logging.getLogger(__name__)


class OverviewService:
    """概览页数据服务"""

    # 主要指数代码映射（纯数字代码）
    INDEX_CODES = {
        "000001": "上证指数",
        "399001": "深证成指",
        "399006": "创业板指",
        "000688": "科创50",
        "899050": "北证50",
    }

    def _get_tushare_pro(self):
        """使用配置中的 Tushare token 初始化 Pro 接口（懒加载）"""
        if not hasattr(self, "_tushare_pro") or self._tushare_pro is None:
            token = settings.tushare_token
            if not token:
                raise RuntimeError("Tushare token 未配置，请检查 /etc/kimi/stocks/base.conf 或 TUSHARE_TOKEN 环境变量")
            self._tushare_pro = ts.pro_api(token)
        return self._tushare_pro

    @staticmethod
    def _index_exchange_prefix(code: str) -> str:
        """根据指数代码返回交易所前缀（sh/sz/bj）"""
        if code.startswith("6") or code.startswith("000"):
            return "sh"
        if code.startswith("399"):
            return "sz"
        if code.startswith("8") or code.startswith("4"):
            return "bj"
        return "sh"

    @staticmethod
    def _code_to_ts_code(code: str) -> Optional[str]:
        """将纯数字股票/指数代码转换为 Tushare ts_code"""
        if code.startswith("6") or code.startswith("000") or code.startswith("899"):
            return f"{code}.SH"
        if code.startswith("399") or code.startswith("3") or code.startswith("0") or code.startswith("2"):
            return f"{code}.SZ"
        if code.startswith("8") or code.startswith("4"):
            return f"{code}.BJ"
        return None

    @staticmethod
    def _ts_code_to_code(ts_code: str) -> str:
        """将 Tushare ts_code 转换为纯数字代码"""
        return ts_code.split(".")[0] if ts_code else ""

    def __init__(self):
        self._tushare_pro = None

    def _get_previous_trade_date(self, target_date: date) -> Optional[date]:
        """获取 target_date 之前最近的一个交易日"""
        try:
            start = target_date - timedelta(days=14)
            dates = self.fetch_trade_dates(start, target_date)
            for d in reversed(dates):
                if d < target_date:
                    return d
        except Exception:
            pass
        return None

    def _fetch_daily_for_date(self, target_date: date) -> Optional[pd.DataFrame]:
        """获取指定日期的 Tushare daily 数据"""
        try:
            date_str = target_date.strftime("%Y%m%d")
            df = self._get_tushare_pro().daily(trade_date=date_str)
            if not df.empty:
                return df
        except Exception:
            pass
        return None

    def _fetch_limit_list_for_date(self, target_date: date) -> Optional[pd.DataFrame]:
        """获取指定日期的 Tushare limit_list_d 数据"""
        try:
            date_str = target_date.strftime("%Y%m%d")
            df = self._get_tushare_pro().limit_list_d(trade_date=date_str)
            if not df.empty:
                return df
        except Exception:
            pass
        return None

    def _fetch_top_list_for_date(self, target_date: date) -> Optional[pd.DataFrame]:
        """获取指定日期的 Tushare top_list 数据"""
        try:
            date_str = target_date.strftime("%Y%m%d")
            df = self._get_tushare_pro().top_list(trade_date=date_str)
            if not df.empty:
                return df
        except Exception:
            pass
        return None

    def fetch_index_spot(self) -> List[dict]:
        """获取主要指数最新可用日线行情（Tushare index_daily）。

        若当天数据尚未更新，自动回退到最近一个有数据的交易日。
        """
        target_date = date.today()
        result = []
        for code, name in self.INDEX_CODES.items():
            data = self.fetch_index_for_date(code, name, target_date)
            if data:
                result.append(data)
        if result:
            return result

        prev_date = self._get_previous_trade_date(target_date)
        if not prev_date:
            return []

        result = []
        for code, name in self.INDEX_CODES.items():
            data = self.fetch_index_for_date(code, name, prev_date)
            if data:
                result.append(data)
        return result

    def fetch_today_market_stats(self) -> dict:
        """获取最新可用交易日的市场统计（Tushare daily + limit_list_d）。

        若当天数据尚未更新，自动回退到最近一个有数据的交易日。
        """
        target_date = date.today()
        stats = self.fetch_market_stats_for_date(target_date)
        if stats.get("total", 0) > 0:
            return stats

        prev_date = self._get_previous_trade_date(target_date)
        if prev_date:
            return self.fetch_market_stats_for_date(prev_date)
        return stats

    def fetch_limit_stats_for_date(self, target_date: date) -> dict:
        """获取指定日期的涨停、跌停、炸板数量（使用 Tushare limit_list_d）"""
        date_str = target_date.strftime("%Y%m%d")
        try:
            df = self._get_tushare_pro().limit_list_d(trade_date=date_str)
            return {
                "limit_up": int((df["limit"] == "U").sum()),
                "limit_down": int((df["limit"] == "D").sum()),
                "opened_limit": int((df["limit"] == "Z").sum()),
            }
        except Exception:
            return {
                "limit_up": 0,
                "limit_down": 0,
                "opened_limit": 0,
            }

    def fetch_trade_dates(self, start: date, end: date) -> List[date]:
        """获取指定日期范围内的 A 股交易日（使用 Tushare 交易日历），结果按升序返回"""
        try:
            df = self._get_tushare_pro().trade_cal(
                exchange="SSE",
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
            )
            df = df[df["is_open"] == 1]
            dates = sorted(df["cal_date"].astype(str).tolist())
            return [datetime.strptime(d, "%Y%m%d").date() for d in dates]
        except Exception:
            # fallback：仅剔除周末
            dates = []
            current = start
            while current <= end:
                if current.weekday() < 5:
                    dates.append(current)
                current += timedelta(days=1)
            return dates

    def fetch_market_history(
        self,
        start: date,
        end: date,
        session,
    ) -> List[dict]:
        """获取指定日期范围的市场统计折线图数据，仅包含交易日，按日期升序返回"""
        from ..models import MarketDailyStat

        trade_dates = self.fetch_trade_dates(start, end)
        result = []
        for current in trade_dates:
            # 先查缓存
            cached = session.exec(
                select(MarketDailyStat).where(MarketDailyStat.stat_date == current)
            ).first()

            if cached:
                result.append({
                    "date": current.isoformat(),
                    "up": cached.up,
                    "down": cached.down,
                    "flat": cached.flat,
                    "limit_up": cached.limit_up,
                    "limit_down": cached.limit_down,
                    "opened_limit": cached.opened_limit,
                    "total": cached.total,
                    "total_turnover": cached.total_turnover,
                })
            else:
                market_stats = self.fetch_market_stats_for_date(current)
                stat = MarketDailyStat(
                    stat_date=current,
                    **market_stats,
                )
                session.add(stat)
                session.commit()

                result.append({
                    "date": current.isoformat(),
                    **market_stats,
                })

        return result

    def fetch_limit_up_stocks(
        self,
        target_date: Optional[date] = None,
        sort_by: str = "pct_chg",
        order: str = "desc",
        offset: int = 0,
        limit: int = 20,
    ) -> dict:
        """获取涨停股票列表（Tushare limit_list_d），支持日期、排序与分页。"""
        return self._fetch_limit_stocks("U", target_date, sort_by, order, offset, limit)

    def fetch_limit_down_stocks(
        self,
        target_date: Optional[date] = None,
        sort_by: str = "pct_chg",
        order: str = "asc",
        offset: int = 0,
        limit: int = 20,
    ) -> dict:
        """获取跌停股票列表（Tushare limit_list_d），支持日期、排序与分页。"""
        return self._fetch_limit_stocks("D", target_date, sort_by, order, offset, limit)

    def fetch_opened_limit_stocks(
        self,
        target_date: Optional[date] = None,
        sort_by: str = "pct_chg",
        order: str = "desc",
        offset: int = 0,
        limit: int = 20,
    ) -> dict:
        """获取炸板股票列表（Tushare limit_list_d 中 limit=Z），支持日期、排序与分页。"""
        return self._fetch_limit_stocks("Z", target_date, sort_by, order, offset, limit)

    @staticmethod
    def _time_str_to_seconds(time_value) -> int:
        """将 Tushare 时间字符串（如 93000 / 134817）转换为从 0 点开始的秒数，用于排序。"""
        if time_value is None or pd.isna(time_value) or str(time_value).strip() in ("", "None"):
            return 0
        s = str(time_value).strip()
        if len(s) == 6:
            return int(s[:2]) * 3600 + int(s[2:4]) * 60 + int(s[4:6])
        if len(s) == 5:
            return int(s[:1]) * 3600 + int(s[1:3]) * 60 + int(s[3:5])
        return 0

    def _fetch_limit_stocks(
        self,
        limit_type: str,
        target_date: Optional[date],
        sort_by: str,
        order: str,
        offset: int,
        limit: int,
    ) -> dict:
        """统一获取涨跌停/炸板股票列表，支持日期、排序与分页。"""
        d = target_date or date.today()
        df = self._fetch_limit_list_for_date(d)
        if df is None or df.empty:
            should_fallback = target_date is None or d == date.today()
            if should_fallback:
                prev_date = self._get_previous_trade_date(d)
                if prev_date:
                    df = self._fetch_limit_list_for_date(prev_date)
        if df is None or df.empty:
            return {"total": 0, "items": []}

        df = df[df["limit"] == limit_type].copy()
        if df.empty:
            return {"total": 0, "items": []}

        df["code"] = df["ts_code"].astype(str).apply(self._ts_code_to_code)
        # Tushare limit_list_d 的 amount 与 fd_amount 单位为"元"，直接保留
        # 封单比 = 封单金额 / 成交额
        df["fd_ratio"] = df.apply(
            lambda r: float(r["fd_amount"]) / float(r["amount"]) if pd.notna(r["fd_amount"]) and float(r["amount"]) > 0 else 0.0,
            axis=1,
        )
        # 首封/封住时间转成秒数用于正确排序
        df["first_time_sec"] = df["first_time"].apply(self._time_str_to_seconds)
        df["last_time_sec"] = df["last_time"].apply(self._time_str_to_seconds)

        # 排序
        valid_sort = {
            "pct_chg": "pct_chg",
            "amount": "amount",
            "turnover_ratio": "turnover_ratio",
            "fd_ratio": "fd_ratio",
            "first_time": "first_time_sec",
            "last_time": "last_time_sec",
            "open_times": "open_times",
            "limit_times": "limit_times",
        }
        sort_col = valid_sort.get(sort_by, "pct_chg")
        ascending = order.lower() == "asc"
        df = df.sort_values(sort_col, ascending=ascending)

        total = len(df)
        df = df.iloc[offset : offset + limit]

        items = df[
            [
                "code",
                "name",
                "close",
                "pct_chg",
                "amount",
                "fd_ratio",
                "turnover_ratio",
                "float_mv",
                "total_mv",
                "first_time",
                "last_time",
                "open_times",
                "up_stat",
                "limit_times",
            ]
        ].rename(
            columns={
                "code": "代码",
                "name": "名称",
                "close": "最新价",
                "pct_chg": "涨跌幅",
                "amount": "成交额",
                "fd_ratio": "封单比",
                "turnover_ratio": "换手率",
                "float_mv": "流通值",
                "total_mv": "总市值",
                "first_time": "首封时间",
                "last_time": "封住时间",
                "open_times": "开板次数",
                "up_stat": "涨停分析" if limit_type in ("U", "Z") else "跌停分析",
                "limit_times": "几天几板",
            }
        ).to_dict("records")

        return {"total": total, "items": items}

    def fetch_dragon_tiger(
        self,
        target_date: Optional[date] = None,
        sort_by: str = "net_amount",
        order: str = "desc",
        offset: int = 0,
        limit: int = 20,
        session: Optional[Session] = None,
    ) -> dict:
        """获取龙虎榜数据（Tushare top_list），支持排序与分页。

        未指定日期或指定为今天但数据尚未更新时，自动回退到最近有数据的交易日。
        默认排除 ST、退市、科创板、创业板、北交所及次新股。
        """
        d = target_date or date.today()
        effective_date = d
        df = self._fetch_top_list_for_date(d)
        if df is None or df.empty:
            should_fallback = target_date is None or d == date.today()
            if should_fallback:
                prev_date = self._get_previous_trade_date(d)
                if prev_date:
                    df = self._fetch_top_list_for_date(prev_date)
                    effective_date = prev_date
        if df is None or df.empty:
            return {"total": 0, "items": []}

        # 标准化字段
        # Tushare top_list 的 net_amount 单位为"元"，直接保留
        df = df.copy()
        df["code"] = df["ts_code"].astype(str).apply(self._ts_code_to_code)

        # 基础过滤：ST、退市、科创、创业、北交、次新股
        if session is not None:
            from ..models import Stock
            from ..strategies.filters import apply_base_filters

            codes = df["code"].dropna().unique().tolist()
            # 识别本地 Stock 表缺失的代码
            stocks = session.exec(select(Stock).where(Stock.code.in_(codes))).all()
            stock_map = {s.code: s for s in stocks}
            missing_codes = set(codes) - set(stock_map.keys())
            if missing_codes:
                logger.warning(
                    "龙虎榜过滤发现本地 Stock 表缺失代码: %s",
                    sorted(missing_codes),
                )

            filtered_codes = apply_base_filters(codes, effective_date, session)
            before_count = len(df)
            df = df[df["code"].isin(filtered_codes)].copy()
            after_count = len(df)
            if before_count != after_count:
                logger.info(
                    "龙虎榜基础过滤: %d 条 -> %d 条 (过滤 %d 条)",
                    before_count,
                    after_count,
                    before_count - after_count,
                )

        # 排序
        valid_sort = {
            "change_pct": "pct_change",
            "net_amount": "net_amount",
            "trade_date": "trade_date",
        }
        sort_col = valid_sort.get(sort_by, "net_amount")
        ascending = order.lower() == "asc"
        df = df.sort_values(sort_col, ascending=ascending)

        total = len(df)

        # 分页
        df = df.iloc[offset : offset + limit]

        items = df[["code", "name", "trade_date", "close", "pct_change", "net_amount", "reason"]].rename(
            columns={
                "code": "代码",
                "name": "名称",
                "trade_date": "上榜日",
                "close": "收盘价",
                "pct_change": "涨跌幅",
                "net_amount": "龙虎榜净买额",
                "reason": "上榜原因",
            }
        ).to_dict("records")

        return {"total": total, "items": items}

    def fetch_top_gainers(
        self,
        target_date: date,
        session: Session,
    ) -> dict:
        """获取5日/10日/20日涨幅榜（基于 StockDailyQuote 本地缓存，缺失时从 Tushare 补齐）。

        返回结构：
        {
            "target_date": "YYYY-MM-DD",
            "effective_date": "YYYY-MM-DD",
            "five_day": [...],
            "ten_day": [...],
            "twenty_day": [...],
        }
        """
        from ..models import Stock, StockDailyQuote
        from ..services.tushare_stock_service import TushareStockService
        from ..strategies.filters import apply_base_filters

        effective_date = self._resolve_effective_quote_date(target_date, session)
        if effective_date is None:
            return {
                "target_date": target_date.isoformat(),
                "effective_date": None,
                "five_day": [],
                "ten_day": [],
                "twenty_day": [],
            }

        lookbacks = self._get_lookback_trade_dates(effective_date, [5, 10, 20])
        five_base = lookbacks.get(5)
        ten_base = lookbacks.get(10)
        twenty_base = lookbacks.get(20)

        needed_dates = {d for d in (effective_date, five_base, ten_base, twenty_base) if d is not None}
        self._ensure_daily_quotes(needed_dates, session)

        rows = session.exec(
            select(StockDailyQuote, Stock)
            .join(Stock, StockDailyQuote.stock_code == Stock.code)
            .where(StockDailyQuote.trade_date.in_(needed_dates))
        ).all()

        quote_map = {(q.stock_code, q.trade_date): q for q, _ in rows}
        stock_map = {q.stock_code: s for q, s in rows}

        return {
            "target_date": target_date.isoformat(),
            "effective_date": effective_date.isoformat(),
            "five_day": self._build_gainer_ranking(
                effective_date, five_base, quote_map, stock_map, session
            ),
            "ten_day": self._build_gainer_ranking(
                effective_date, ten_base, quote_map, stock_map, session
            ),
            "twenty_day": self._build_gainer_ranking(
                effective_date, twenty_base, quote_map, stock_map, session
            ),
        }

    def _resolve_effective_quote_date(
        self,
        target_date: date,
        session: Session,
    ) -> Optional[date]:
        """确定有效行情日期：优先本地最新交易日，若落后交易日历则尝试从 Tushare 补齐。"""
        from ..models import StockDailyQuote
        from ..services.tushare_stock_service import TushareStockService

        db_latest = session.exec(
            select(StockDailyQuote.trade_date)
            .where(StockDailyQuote.trade_date <= target_date)
            .order_by(StockDailyQuote.trade_date.desc())
            .limit(1)
        ).first()

        calendar_dates = self.fetch_trade_dates(
            target_date - timedelta(days=90), target_date
        )
        calendar_latest = calendar_dates[-1] if calendar_dates else None

        if calendar_latest is None:
            return db_latest

        if db_latest == calendar_latest:
            return db_latest

        try:
            quotes = TushareStockService().fetch_daily_quotes(calendar_latest)
            if quotes:
                self._upsert_daily_quotes(quotes, session)
                return calendar_latest
        except Exception as e:
            logger.warning("从 Tushare 拉取 %s 行情失败: %s", calendar_latest, e)

        return db_latest

    def _get_lookback_trade_dates(
        self,
        effective_date: date,
        windows: List[int],
    ) -> Dict[int, Optional[date]]:
        """根据交易日历，计算 effective_date 前推 N 个交易日的日期。"""
        dates = self.fetch_trade_dates(
            effective_date - timedelta(days=90), effective_date
        )
        if effective_date not in dates:
            return {w: None for w in windows}

        idx = dates.index(effective_date)
        return {w: dates[idx - w] if idx >= w else None for w in windows}

    def _ensure_daily_quotes(
        self,
        dates,
        session: Session,
    ) -> None:
        """确保指定日期在 StockDailyQuote 中有数据，缺失时从 Tushare 拉取。"""
        from ..models import StockDailyQuote
        from ..services.tushare_stock_service import TushareStockService

        for d in dates:
            exists = session.exec(
                select(func.count(StockDailyQuote.id))
                .where(StockDailyQuote.trade_date == d)
            ).one()
            if exists:
                continue

            try:
                quotes = TushareStockService().fetch_daily_quotes(d)
                if quotes:
                    self._upsert_daily_quotes(quotes, session)
            except Exception as e:
                logger.warning("补齐 %s 行情失败: %s", d, e)

    def _upsert_daily_quotes(
        self,
        quotes: List["StockDailyQuote"],
        session: Session,
    ) -> None:
        """批量 upsert StockDailyQuote 记录。"""
        from ..models import StockDailyQuote

        fields = [
            "close",
            "change_pct",
            "amount",
            "turnover_rate",
            "turnover_rate_f",
            "float_mv",
            "total_mv",
            "pe",
            "pe_ttm",
            "pb",
            "ps",
            "ps_ttm",
            "dv_ratio",
            "dv_ttm",
        ]
        for q in quotes:
            existing = session.exec(
                select(StockDailyQuote)
                .where(StockDailyQuote.stock_code == q.stock_code)
                .where(StockDailyQuote.trade_date == q.trade_date)
            ).first()
            if existing:
                for f in fields:
                    setattr(existing, f, getattr(q, f))
                existing.updated_at = datetime.utcnow()
                session.add(existing)
            else:
                session.add(q)
        session.commit()

    def _build_gainer_ranking(
        self,
        end_date: date,
        start_date: Optional[date],
        quote_map: Dict,
        stock_map: Dict[str, "Stock"],
        session: Session,
    ) -> List[dict]:
        """构建单期涨幅榜前 10。"""
        from ..models import Stock
        from ..strategies.filters import apply_base_filters

        if start_date is None:
            return []

        candidates = []
        codes = []
        for code, stock in stock_map.items():
            q_now = quote_map.get((code, end_date))
            q_then = quote_map.get((code, start_date))
            if not q_now or not q_then:
                continue
            if q_now.close is None or q_then.close is None or q_then.close <= 0:
                continue

            gain = (q_now.close / q_then.close - 1) * 100
            candidates.append({
                "code": code,
                "close": q_now.close,
                "gain": gain,
                "amount": q_now.amount or 0,
                "turnover_rate": q_now.turnover_rate or 0,
            })
            codes.append(code)

        if not candidates:
            return []

        filtered_codes = set(apply_base_filters(codes, end_date, session))

        result = []
        for c in sorted(candidates, key=lambda x: x["gain"], reverse=True):
            if c["code"] not in filtered_codes:
                continue
            stock = stock_map[c["code"]]
            result.append({
                "rank": len(result) + 1,
                "code": c["code"],
                "name": stock.name,
                "close": round(c["close"], 2),
                "gain": round(c["gain"], 2),
                "amount": c["amount"],
                "turnover_rate": c["turnover_rate"],
                "industry": stock.industry or "",
            })
            if len(result) >= 10:
                break

        return result

    def fetch_index_for_date(self, code: str, name: str, target_date: date) -> Optional[dict]:
        """获取单个指数在指定日期的行情（使用 Tushare index_daily）"""
        date_str = target_date.strftime("%Y%m%d")
        ts_code_map = {
            "000001": "000001.SH",
            "399001": "399001.SZ",
            "399006": "399006.SZ",
            "000688": "000688.SH",
            "899050": "899050.BJ",
        }
        ts_code = ts_code_map.get(code)
        if not ts_code:
            return None
        try:
            df = self._get_tushare_pro().index_daily(ts_code=ts_code, start_date=date_str, end_date=date_str)
            if not df.empty:
                row = df.iloc[0]
                return {
                    "code": code,
                    "name": name,
                    "price": float(row["close"]),
                    "change": float(row["change"]),
                    "change_pct": float(row["pct_chg"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "volume": float(row["vol"]),
                    "amount": float(row["amount"]),
                }
        except Exception:
            pass
        return None

    def fetch_market_stats_for_date(self, target_date: date) -> dict:
        """获取指定日期的市场统计（涨跌家数、成交额、涨跌停，全部来自 Tushare）

        使用 Tushare daily 计算涨跌家数与总成交额；limit_list_d 计算涨跌停/炸板。
        若当日 daily 无数据（未收盘或节假日），则全部返回 0，避免显示 stale 数据。
        """
        date_str = target_date.strftime("%Y%m%d")
        empty_result = {
            "up": 0,
            "down": 0,
            "flat": 0,
            "limit_up": 0,
            "limit_down": 0,
            "opened_limit": 0,
            "total": 0,
            "total_turnover": 0.0,
        }
        try:
            df = self._get_tushare_pro().daily(trade_date=date_str)
            if df.empty:
                return empty_result
            up = int((df["pct_chg"] > 0).sum())
            down = int((df["pct_chg"] < 0).sum())
            flat = int((df["pct_chg"] == 0).sum())
            # amount 单位为千元，转成元
            total_turnover = float(df["amount"].sum()) * 1000
            limit_stats = self.fetch_limit_stats_for_date(target_date)
            return {
                "up": up,
                "down": down,
                "flat": flat,
                "total": up + down + flat,
                "total_turnover": total_turnover,
                **limit_stats,
            }
        except Exception:
            return empty_result

    def fetch_daily_overview(self, target_date: date, session) -> dict:
        """获取指定日期的日概览数据（指数 + 市场统计）"""
        from concurrent.futures import ThreadPoolExecutor
        from ..models import IndexDaily, MarketDailyStat

        # 1. 指数数据：先查缓存，缺失再并行请求
        cached_indices: Dict[str, dict] = {}
        missing_codes: List[tuple] = []
        for code, name in self.INDEX_CODES.items():
            cached = session.exec(
                select(IndexDaily).where(
                    IndexDaily.code == code,
                    IndexDaily.trade_date == target_date,
                )
            ).first()
            if cached:
                cached_indices[code] = {
                    "code": cached.code,
                    "name": cached.name,
                    "price": cached.close,
                    "change": cached.change,
                    "change_pct": cached.change_pct,
                }
            else:
                missing_codes.append((code, name))

        def _fetch_one(args):
            code, name = args
            return code, self.fetch_index_for_date(code, name, target_date)

        fetched_indices: Dict[str, dict] = {}
        if missing_codes:
            with ThreadPoolExecutor(max_workers=5) as executor:
                for code, data in executor.map(_fetch_one, missing_codes):
                    if data:
                        fetched_indices[code] = data
                        session.add(IndexDaily(
                            code=code,
                            name=self.INDEX_CODES[code],
                            trade_date=target_date,
                            open=data["open"],
                            high=data["high"],
                            low=data["low"],
                            close=data["price"],
                            volume=data["volume"],
                            amount=data["amount"],
                            change=data["change"],
                            change_pct=data["change_pct"],
                        ))

        if fetched_indices:
            session.commit()

        indices = []
        for code in self.INDEX_CODES:
            item = cached_indices.get(code) or fetched_indices.get(code)
            if item:
                indices.append(item)

        # 2. 市场统计（统一走 Tushare；节假日/未收盘时返回 0）
        cached_stat = session.exec(
            select(MarketDailyStat).where(MarketDailyStat.stat_date == target_date)
        ).first()
        if cached_stat:
            market_stats = {
                "up": cached_stat.up,
                "down": cached_stat.down,
                "flat": cached_stat.flat,
                "limit_up": cached_stat.limit_up,
                "limit_down": cached_stat.limit_down,
                "opened_limit": cached_stat.opened_limit,
                "total": cached_stat.total,
                "total_turnover": cached_stat.total_turnover,
            }
        else:
            market_stats = self.fetch_market_stats_for_date(target_date)
            session.add(MarketDailyStat(
                stat_date=target_date,
                **market_stats,
            ))
            session.commit()

        return {
            "date": target_date.isoformat(),
            "indices": indices,
            "market_stats": market_stats,
        }

    def fetch_realtime_overview(self) -> dict:
        """实时概览数据（基础信息）；板块、涨速等榜单通过独立接口按需加载"""
        return {
            "indices": self.fetch_index_spot(),
            "market_stats": self.fetch_today_market_stats(),
            "top_gainers": self.fetch_top_movers("up", 10),
            "top_losers": self.fetch_top_movers("down", 10),
            "industry_sectors": [],
            "concept_sectors": [],
            "speed_5min_up": [],
            "speed_5min_down": [],
            "speed_15min_up": [],
            "speed_15min_down": [],
        }

    def _get_stock_names(self, codes: List[str]) -> Dict[str, str]:
        """从本地 Stock 表批量查询股票名称"""
        from ..models import Stock
        from ..database import engine
        try:
            with Session(engine) as session:
                rows = session.exec(select(Stock).where(Stock.code.in_(codes))).all()
                return {row.code: row.name for row in rows}
        except Exception:
            return {}

    def fetch_top_movers(self, direction: str = "up", limit: int = 10) -> List[dict]:
        """获取领涨/领跌股票（Tushare daily），当天无数据时回退到最近交易日。"""
        target_date = date.today()
        df = self._fetch_daily_for_date(target_date)
        if df is None or df.empty:
            prev_date = self._get_previous_trade_date(target_date)
            if prev_date:
                df = self._fetch_daily_for_date(prev_date)
        if df is None or df.empty:
            return []

        df = df.copy()
        df["code"] = df["ts_code"].astype(str).apply(self._ts_code_to_code)
        names = self._get_stock_names(df["code"].astype(str).tolist())
        df["name"] = df["code"].map(names).fillna("")
        df = df.sort_values("pct_chg", ascending=(direction == "down"))
        df = df.head(limit)
        return df[["code", "name", "close", "pct_chg"]].rename(
            columns={
                "code": "代码",
                "name": "名称",
                "close": "最新价",
                "pct_chg": "涨跌幅",
            }
        ).to_dict("records")

    def _get_sector_index_info(self) -> Dict[str, dict]:
        """获取同花顺指数代码到类型/名称的映射（I=行业，N=概念）。

        结果缓存在实例内存中，避免每次同步都重复请求 Tushare。
        """
        if hasattr(self, "_sector_index_info") and self._sector_index_info:
            return self._sector_index_info

        info: Dict[str, dict] = {}
        try:
            for st, label in (("I", "industry"), ("N", "concept")):
                df = self._get_tushare_pro().ths_index(type=st, src="exp")
                for _, row in df.iterrows():
                    code = str(row.get("ts_code", "")).strip()
                    name = str(row.get("name", "")).strip()
                    if code:
                        info[code] = {"type": label, "name": name}
        except Exception:
            # 失败时返回空，由调用方处理
            pass

        self._sector_index_info = info
        return info

    def _fetch_sector_daily_from_tushare(self, target_date: date) -> Dict[str, List[dict]]:
        """从 Tushare 拉取指定日期的同花顺行业/概念指数日线数据。

        Tushare ths_daily 未提供板块成交额，因此用成交量（vol，单位：手）作为替代字段。
        """
        date_str = target_date.strftime("%Y%m%d")
        result: Dict[str, List[dict]] = {"industry": [], "concept": []}
        try:
            info = self._get_sector_index_info()
            if not info:
                return result

            df = self._get_tushare_pro().ths_daily(trade_date=date_str)
            if df.empty:
                return result

            for _, row in df.iterrows():
                code = str(row.get("ts_code", "")).strip()
                meta = info.get(code)
                if not meta:
                    continue
                result[meta["type"]].append({
                    "sector_code": code,
                    "sector_name": meta["name"],
                    "change_pct": float(row.get("pct_change", 0) or 0),
                    "volume": float(row.get("vol", 0) or 0),
                })
        except Exception:
            pass
        return result

    def fetch_sector_ranking(self, sector_type: str = "industry", limit: int = 20) -> List[dict]:
        """获取最新可用日期的板块排行（收盘后日线数据）。

        优先返回数据库中已有数据的最近一个交易日；数据库为空时尝试从 Tushare 拉取今天数据。
        """
        from ..models import SectorDaily
        from ..database import engine

        try:
            with Session(engine) as session:
                latest_row = session.exec(
                    select(SectorDaily)
                    .where(SectorDaily.sector_type == sector_type)
                    .order_by(SectorDaily.trade_date.desc())
                    .limit(1)
                ).first()
                target_date = latest_row.trade_date if latest_row else date.today()
                return self.fetch_sector_ranking_for_date(
                    target_date, sector_type, sort_by="change_pct", limit=limit, session=session
                )
        except Exception:
            return []

    def fetch_sector_ranking_for_date(
        self,
        target_date: date,
        sector_type: str = "industry",
        sort_by: str = "change_pct",
        limit: int = 50,
        session=None,
    ) -> List[dict]:
        """获取指定日期的板块排行，优先查本地缓存，无缓存时从 Tushare 拉取并入库。"""
        from ..models import SectorDaily

        valid_sort = {"change_pct", "volume"}
        if sort_by not in valid_sort:
            sort_by = "change_pct"

        if session is not None:
            cached = session.exec(
                select(SectorDaily).where(
                    SectorDaily.sector_type == sector_type,
                    SectorDaily.trade_date == target_date,
                )
            ).all()
            if cached:
                rows = [
                    {
                        "sector_code": row.sector_code,
                        "sector_name": row.sector_name,
                        "change_pct": row.change_pct,
                        "volume": row.volume,
                    }
                    for row in cached
                ]
                rows.sort(key=lambda x: x[sort_by], reverse=True)
                return rows[:limit]

        # 缓存缺失：从 Tushare 拉取
        data = self._fetch_sector_daily_from_tushare(target_date)
        rows = data.get(sector_type, [])
        if session is not None and rows:
            try:
                self._upsert_sector_daily(session, sector_type, target_date, rows)
            except Exception:
                # 缓存写入失败（如并发写库）不影响本次数据返回
                session.rollback()
                logger.exception(
                    "板块日线缓存写入失败: %s %s", sector_type, target_date
                )

        rows.sort(key=lambda x: x[sort_by], reverse=True)
        return rows[:limit]

    @staticmethod
    def _upsert_sector_daily(session, sector_type: str, target_date: date, rows: List[dict]) -> int:
        """原子 upsert 板块日线，返回写入条数。

        概览页会对同一交易日并发发起多个 sectors-daily 请求，缓存为空时多个
        线程同时走"拉取 → 写入"；逐行 SELECT+add 会在 autoflush 时撞
        (sector_type, sector_code, trade_date) 唯一约束（历史 500 报错），
        改用 SQLite 原生 ON CONFLICT DO UPDATE 后写入是原子的，并发安全。
        """
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        from ..models import SectorDaily

        # 防御：Tushare 若返回重复 sector_code，只保留最后一条
        deduped = {item["sector_code"]: item for item in rows}
        now = datetime.utcnow()
        values = [
            {
                "sector_type": sector_type,
                "sector_code": item["sector_code"],
                "sector_name": item["sector_name"],
                "trade_date": target_date,
                "change_pct": item["change_pct"],
                "volume": item["volume"],
                "updated_at": now,
            }
            for item in deduped.values()
        ]
        stmt = sqlite_insert(SectorDaily).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["sector_type", "sector_code", "trade_date"],
            set_={
                "sector_name": stmt.excluded.sector_name,
                "change_pct": stmt.excluded.change_pct,
                "volume": stmt.excluded.volume,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        session.execute(stmt)
        session.commit()
        return len(values)

    def sync_sector_ranking_for_date(
        self,
        target_date: date,
        sector_type: str = "industry",
        session=None,
    ) -> int:
        """强制同步指定日期的板块排行数据，返回同步条数。"""
        from ..models import SectorDaily

        if session is None:
            return 0

        # 删除旧缓存与重新写入放在同一事务，避免与并发请求交错产生竞态
        old_rows = session.exec(
            select(SectorDaily).where(
                SectorDaily.sector_type == sector_type,
                SectorDaily.trade_date == target_date,
            )
        ).all()
        for row in old_rows:
            session.delete(row)

        data = self._fetch_sector_daily_from_tushare(target_date)
        rows = data.get(sector_type, [])
        if not rows:
            session.commit()
            return 0
        # _upsert_sector_daily 内部会 commit；删除在同一会话中随之一起提交
        return self._upsert_sector_daily(session, sector_type, target_date, rows)

    def fetch_speed_ranking(self, interval: str = "5min", direction: str = "up", limit: int = 20) -> List[dict]:
        """获取涨速榜（5分钟/15分钟最快拉升/下跌）。

        当前数据源策略为仅使用 Tushare，而 Tushare 的分钟级数据接口频次限制为 1 次/小时，
        无法支撑全市场涨速排行计算，因此暂时返回空列表。
        """
        return []
