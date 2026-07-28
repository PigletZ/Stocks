"""涨停复盘服务：涨跌停/龙虎榜明细落库 + 连板梯队/昨日涨停表现/情绪周期查询。"""

import logging
from datetime import date, datetime
from typing import Dict, List, Optional

import pandas as pd
import tushare as ts
from sqlmodel import Session, select, delete

from ..config import settings
from ..models import DragonTigerDaily, LimitUpDaily, MarketDailyStat, StockDailyQuote


logger = logging.getLogger(__name__)


class ReviewService:
    """涨停复盘数据服务"""

    def __init__(self):
        self._tushare_pro = None

    def _get_tushare_pro(self):
        """使用配置中的 Tushare token 初始化 Pro 接口（懒加载）"""
        if self._tushare_pro is None:
            token = settings.tushare_token
            if not token:
                raise RuntimeError("Tushare token 未配置")
            self._tushare_pro = ts.pro_api(token)
        return self._tushare_pro

    # ==================== 数据落库 ====================

    def sync_limit_daily(self, target_date: date, session: Session) -> int:
        """同步指定交易日的涨跌停/炸板明细（limit_list_d），当天整体覆盖。

        数据未就绪（空表/异常）时返回 0 且不触碰已有数据。
        """
        date_str = target_date.strftime("%Y%m%d")
        try:
            df = self._get_tushare_pro().limit_list_d(trade_date=date_str)
        except Exception as e:
            logger.warning("limit_list_d %s 拉取失败: %s", date_str, e)
            return 0
        if df is None or df.empty:
            return 0

        session.exec(delete(LimitUpDaily).where(LimitUpDaily.trade_date == target_date))
        rows = []
        for r in df.to_dict("records"):
            rows.append(LimitUpDaily(
                stock_code=str(r.get("ts_code") or "").split(".")[0],
                trade_date=target_date,
                name=str(r.get("name") or ""),
                limit_type=str(r.get("limit") or ""),
                close=self._num(r.get("close")),
                pct_chg=self._num(r.get("pct_chg")),
                amount=self._num(r.get("amount")),
                fd_amount=self._num(r.get("fd_amount")),
                turnover_ratio=self._num(r.get("turnover_ratio")),
                float_mv=self._num(r.get("float_mv")),
                total_mv=self._num(r.get("total_mv")),
                first_time=self._str(r.get("first_time")),
                last_time=self._str(r.get("last_time")),
                open_times=self._int(r.get("open_times")),
                up_stat=self._str(r.get("up_stat")),
                limit_times=self._int(r.get("limit_times")),
            ))
        session.add_all(rows)
        session.commit()
        logger.info("limit_up_daily %s 落库 %d 条", date_str, len(rows))
        return len(rows)

    def sync_dragon_tiger_daily(self, target_date: date, session: Session) -> int:
        """同步指定交易日的龙虎榜（top_list），当天整体覆盖。"""
        date_str = target_date.strftime("%Y%m%d")
        try:
            df = self._get_tushare_pro().top_list(trade_date=date_str)
        except Exception as e:
            logger.warning("top_list %s 拉取失败: %s", date_str, e)
            return 0
        if df is None or df.empty:
            return 0

        # 同一只票当天可能多条（不同上榜原因），按 code 聚合
        df["code"] = df["ts_code"].astype(str).str.split(".").str[0]
        agg = df.groupby("code", as_index=False).agg({
            "name": "first",
            "close": "first",
            "pct_change": "first",
            "turnover_rate": "first",
            "amount": "sum",
            "l_buy": "sum",
            "l_sell": "sum",
            "net_amount": "sum",
            "net_rate": "first",
            "reason": lambda s: "；".join(sorted(set(str(x) for x in s if pd.notna(x)))),
        })

        session.exec(delete(DragonTigerDaily).where(DragonTigerDaily.trade_date == target_date))
        rows = []
        for r in agg.to_dict("records"):
            rows.append(DragonTigerDaily(
                stock_code=r["code"],
                trade_date=target_date,
                name=str(r.get("name") or ""),
                close=self._num(r.get("close")),
                pct_change=self._num(r.get("pct_change")),
                turnover_rate=self._num(r.get("turnover_rate")),
                amount=self._num(r.get("amount")),
                l_buy=self._num(r.get("l_buy")),
                l_sell=self._num(r.get("l_sell")),
                net_amount=self._num(r.get("net_amount")),
                net_rate=self._num(r.get("net_rate")),
                reason=self._str(r.get("reason")),
            ))
        session.add_all(rows)
        session.commit()
        logger.info("dragon_tiger_daily %s 落库 %d 条", date_str, len(rows))
        return len(rows)

    def get_latest_limit_date(self, session: Session) -> Optional[date]:
        """本地涨停缓存中最新的交易日"""
        row = session.exec(
            select(LimitUpDaily.trade_date).order_by(LimitUpDaily.trade_date.desc()).limit(1)
        ).first()
        return row

    # ==================== 连板梯队 ====================

    def get_limit_ladder(self, target_date: Optional[date], session: Session) -> dict:
        """连板梯队：指定日期涨停股按连板数分组（从高到低）。"""
        d = target_date or self.get_latest_limit_date(session)
        if d is None:
            return {"trade_date": None, "ladder": [], "total": 0}

        rows = session.exec(
            select(LimitUpDaily).where(
                LimitUpDaily.trade_date == d,
                LimitUpDaily.limit_type == "U",
            )
        ).all()

        groups: Dict[int, list] = {}
        for r in rows:
            boards = r.limit_times if r.limit_times and r.limit_times > 0 else 1
            groups.setdefault(boards, []).append(self._limit_item(r))

        ladder = [
            {"boards": b, "count": len(items), "stocks": sorted(items, key=lambda x: x["first_time"] or "999999")}
            for b, items in sorted(groups.items(), key=lambda kv: kv[0], reverse=True)
        ]
        return {"trade_date": d.isoformat(), "ladder": ladder, "total": len(rows)}

    # ==================== 昨日涨停今日表现 ====================

    def get_limit_performance(self, target_date: Optional[date], session: Session) -> dict:
        """昨日涨停股在指定日期的表现：晋级率、平均涨幅、明细。

        指定日期缺本地涨幅数据时（早于 StockDailyQuote 覆盖范围），
        实时从 Tushare daily 补齐（单日一次请求）。
        """
        d = target_date or self.get_latest_limit_date(session)
        if d is None:
            return {"trade_date": None, "prev_date": None, "stats": {}, "items": []}

        prev_date = session.exec(
            select(LimitUpDaily.trade_date)
            .where(LimitUpDaily.trade_date < d)
            .order_by(LimitUpDaily.trade_date.desc())
            .limit(1)
        ).first()
        if prev_date is None:
            return {"trade_date": d.isoformat(), "prev_date": None, "stats": {}, "items": []}

        prev_rows = session.exec(
            select(LimitUpDaily).where(
                LimitUpDaily.trade_date == prev_date,
                LimitUpDaily.limit_type == "U",
            )
        ).all()

        # 今日涨跌停状态
        today_rows = session.exec(
            select(LimitUpDaily).where(LimitUpDaily.trade_date == d)
        ).all()
        today_map = {r.stock_code: r for r in today_rows}

        # 今日涨幅：优先 StockDailyQuote，缺失的实时补拉
        codes = [r.stock_code for r in prev_rows]
        quotes = session.exec(
            select(StockDailyQuote).where(
                StockDailyQuote.trade_date == d,
                StockDailyQuote.stock_code.in_(codes),
            )
        ).all()
        pct_map = {q.stock_code: q.change_pct for q in quotes if q.change_pct is not None}
        missing = [c for c in codes if c not in pct_map and c not in today_map]
        if missing:
            pct_map.update(self._fetch_pct_live(d, missing))

        items = []
        for r in prev_rows:
            t = today_map.get(r.stock_code)
            if t is not None and t.limit_type == "U":
                status = "晋级"
            elif t is not None and t.limit_type == "Z":
                status = "炸板"
            elif t is not None and t.limit_type == "D":
                status = "跌停"
            else:
                pct = pct_map.get(r.stock_code)
                status = "红盘" if (pct is not None and pct >= 0) else "绿盘"
            items.append({
                "code": r.stock_code,
                "name": r.name,
                "prev_boards": r.limit_times if r.limit_times and r.limit_times > 0 else 1,
                "today_pct": round(pct_map.get(r.stock_code), 2) if pct_map.get(r.stock_code) is not None else (t.pct_chg if t else None),
                "today_boards": t.limit_times if t and t.limit_type == "U" else None,
                "status": status,
            })

        pcts = [i["today_pct"] for i in items if i["today_pct"] is not None]
        promoted = sum(1 for i in items if i["status"] == "晋级")
        stats = {
            "total": len(items),
            "promoted": promoted,
            "promote_rate": round(promoted / len(items) * 100, 1) if items else 0,
            "opened": sum(1 for i in items if i["status"] == "炸板"),
            "limit_down": sum(1 for i in items if i["status"] == "跌停"),
            "avg_pct": round(sum(pcts) / len(pcts), 2) if pcts else None,
        }
        # 晋级优先，其余按涨幅排序
        order = {"晋级": 0, "炸板": 1, "红盘": 2, "绿盘": 3, "跌停": 4}
        items.sort(key=lambda i: (order.get(i["status"], 5), -(i["today_pct"] or -999)))
        return {
            "trade_date": d.isoformat(),
            "prev_date": prev_date.isoformat(),
            "stats": stats,
            "items": items,
        }

    # ==================== 情绪周期 ====================

    def get_emotion_series(self, start: date, end: date, session: Session) -> List[dict]:
        """情绪指标时间序列：涨停/跌停/炸板数、炸板率、晋级率、最高板、成交额。"""
        stats = session.exec(
            select(MarketDailyStat).where(
                MarketDailyStat.stat_date >= start,
                MarketDailyStat.stat_date <= end,
            ).order_by(MarketDailyStat.stat_date)
        ).all()

        # 涨停明细用于晋级率与最高板（多取一天用于首日晋级计算）
        limit_rows = session.exec(
            select(LimitUpDaily).where(
                LimitUpDaily.trade_date >= start,
                LimitUpDaily.trade_date <= end,
                LimitUpDaily.limit_type == "U",
            )
        ).all()
        by_date: Dict[date, List[LimitUpDaily]] = {}
        for r in limit_rows:
            by_date.setdefault(r.trade_date, []).append(r)

        result = []
        prev_codes: set = set()
        for s in stats:
            day_rows = by_date.get(s.stat_date, [])
            codes = {r.stock_code for r in day_rows}
            promoted = len(codes & prev_codes)
            promote_rate = round(promoted / len(prev_codes) * 100, 1) if prev_codes else None
            max_board = max(
                (r.limit_times for r in day_rows if r.limit_times and r.limit_times > 0),
                default=(1 if day_rows else 0),
            )
            break_rate = (
                round(s.opened_limit / (s.limit_up + s.opened_limit) * 100, 1)
                if (s.limit_up + s.opened_limit) > 0 else None
            )
            result.append({
                "date": s.stat_date.isoformat(),
                "limit_up": s.limit_up,
                "limit_down": s.limit_down,
                "opened_limit": s.opened_limit,
                "break_rate": break_rate,
                "promote_rate": promote_rate,
                "max_board": max_board,
                "up": s.up,
                "down": s.down,
                "total_turnover": s.total_turnover,
            })
            prev_codes = codes
        return result

    # ==================== 内部工具 ====================

    def _fetch_pct_live(self, target_date: date, codes: List[str]) -> Dict[str, float]:
        """实时从 Tushare daily 补拉指定日期的涨跌幅（用于早于本地缓存的历史日期）。"""
        try:
            df = self._get_tushare_pro().daily(trade_date=target_date.strftime("%Y%m%d"))
            if df is None or df.empty:
                return {}
            df["code"] = df["ts_code"].astype(str).str.split(".").str[0]
            sub = df[df["code"].isin(codes)]
            return {r["code"]: float(r["pct_chg"]) for r in sub.to_dict("records")}
        except Exception as e:
            logger.warning("daily %s 实时补拉失败: %s", target_date, e)
            return {}

    @staticmethod
    def _limit_item(r: LimitUpDaily) -> dict:
        return {
            "code": r.stock_code,
            "name": r.name,
            "boards": r.limit_times if r.limit_times and r.limit_times > 0 else 1,
            "up_stat": r.up_stat,
            "pct_chg": r.pct_chg,
            "amount": r.amount,
            "fd_amount": r.fd_amount,
            "first_time": r.first_time,
            "open_times": r.open_times,
            "float_mv": r.float_mv,
        }

    @staticmethod
    def _num(v) -> Optional[float]:
        if v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v):
            return None
        return float(v)

    @staticmethod
    def _int(v) -> Optional[int]:
        n = ReviewService._num(v)
        return int(n) if n is not None else None

    @staticmethod
    def _str(v) -> Optional[str]:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        s = str(v).strip()
        return s if s and s.lower() != "nan" else None
