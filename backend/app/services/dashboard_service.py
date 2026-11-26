"""概览分析：只读本地收盘数据，缺失数据保持空值，不回源或伪造零值。"""

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Session, select

from ..models import IndexDaily, LimitUpDaily, MarketDailyStat, SectorDaily, StockDailyQuote
from .overview_service import OverviewService


class DashboardService:
    @staticmethod
    def sync_daily(d: date, session: Session) -> dict:
        """先取得完整新数据，再覆盖缓存；失败时保留已入库结果。"""
        from concurrent.futures import ThreadPoolExecutor
        service = OverviewService()
        stats, authoritative = service.fetch_market_stats_for_date(d,strict=True)
        if not authoritative:
            raise ValueError("收盘统计尚未发布或拉取失败，已保留原有数据")
        with ThreadPoolExecutor(max_workers=5) as executor:
            data = list(executor.map(
                lambda item: service.fetch_index_for_date(item[0], item[1], d,strict=True),
                OverviewService.INDEX_CODES.items(),
            ))
        if not all(data):
            raise ValueError("指数数据尚未齐备或拉取失败，已保留原有数据")
        now = datetime.utcnow()
        for item in data:
            row = session.exec(select(IndexDaily).where(
                IndexDaily.code == item["code"], IndexDaily.trade_date == d
            )).first()
            if row is None:
                row = IndexDaily(code=item["code"], name=item["name"], trade_date=d,
                                 open=item["open"], high=item["high"], low=item["low"],
                                 close=item["price"], volume=item["volume"], amount=item["amount"],
                                 change=item["change"], change_pct=item["change_pct"])
            else:
                for key in ("open", "high", "low", "volume", "amount", "change", "change_pct"):
                    setattr(row, key, item[key])
                row.close = item["price"]
            row.updated_at = now
            session.add(row)
        row = session.exec(select(MarketDailyStat).where(MarketDailyStat.stat_date == d)).first()
        if row is None:
            row = MarketDailyStat(stat_date=d, **stats)
        else:
            for key, value in stats.items():
                setattr(row, key, value)
        row.updated_at = now
        session.add(row)
        session.commit()
        return {"date": d.isoformat(), "indices_count": len(data), "market_stats": stats}

    @staticmethod
    def _snapshot(row):
        if row is None:
            return None
        total = row.up + row.down + row.flat
        breadth_ready = row.total > 0 and total == row.total
        return {
            "date": row.stat_date.isoformat(),
            "up": row.up if breadth_ready else None,
            "down": row.down if breadth_ready else None,
            "flat": row.flat if breadth_ready else None,
            "total": row.total if breadth_ready else None,
            "up_ratio": round(row.up / total * 100, 2) if breadth_ready else None,
            "total_turnover": row.total_turnover if row.total_turnover > 0 else None,
            "limit_up": row.limit_up,
            "limit_down": row.limit_down,
            "opened_limit": row.opened_limit,
            "break_rate": round(row.opened_limit / (row.limit_up + row.opened_limit) * 100, 2)
            if row.limit_up + row.opened_limit > 0 else None,
        }

    def get_dashboard(self, target_date: Optional[date], session: Session) -> dict:
        today = datetime.now(timezone(timedelta(hours=8))).date()
        available_dates = list(session.exec(
            select(MarketDailyStat.stat_date).where(MarketDailyStat.stat_date <= today)
            .order_by(MarketDailyStat.stat_date)
        ).all())
        d = target_date or (available_dates[-1] if available_dates else today)
        rows = list(reversed(session.exec(
            select(MarketDailyStat).where(MarketDailyStat.stat_date <= d)
            .order_by(MarketDailyStat.stat_date.desc()).limit(61)
        ).all()))
        current = next((r for r in rows if r.stat_date == d), None)
        prior = [r for r in rows if r.stat_date < d]
        previous = prior[-1] if prior else None
        current_snapshot = self._snapshot(current)
        history = [self._snapshot(r) for r in rows[-60:]]
        benchmark = [r.total_turnover for r in prior[-20:] if r.total_turnover > 0]
        indices = session.exec(select(IndexDaily).where(IndexDaily.trade_date == d)).all()
        index_map = {r.code: r for r in indices}
        ordered_indices = [index_map[c] for c in OverviewService.INDEX_CODES if c in index_map]
        status = "missing" if current is None else "ready"
        if current is not None and (current_snapshot["up_ratio"] is None
                                    or current_snapshot["total_turnover"] is None
                                    or len(ordered_indices) < len(OverviewService.INDEX_CODES)):
            status = "partial"
        return {
            "date": d.isoformat(),
            "latest_date": available_dates[-1].isoformat() if available_dates else None,
            "available_dates": [value.isoformat() for value in available_dates],
            "status": status,
            "updated_at": current.updated_at.replace(tzinfo=timezone.utc).isoformat() if current else None,
            "current": current_snapshot,
            "previous": self._snapshot(previous),
            "history": history,
            "turnover_average": sum(benchmark) / len(benchmark) if benchmark else None,
            "turnover_average_days": len(benchmark),
            "indices": [{"code": r.code, "name": r.name, "price": r.close,
                         "change": r.change, "change_pct": r.change_pct} for r in ordered_indices],
            "short_term": self._short_term(d, current, previous, session),
            "sectors": self._sectors(d, previous.stat_date if previous else None, session),
        }

    @staticmethod
    def _short_term(d, current, previous, session):
        dates = [d] + ([previous.stat_date] if previous else [])
        limits = session.exec(select(LimitUpDaily).where(LimitUpDaily.trade_date.in_(dates))).all()
        today_rows = [r for r in limits if r.trade_date == d]
        today_up = [r for r in today_rows if r.limit_type == "U"]
        prev_up = [r for r in limits if previous and r.trade_date == previous.stat_date and r.limit_type == "U"]
        ready = current is not None and len(today_up) == current.limit_up
        prev_ready = previous is not None and len(prev_up) == previous.limit_up
        groups = Counter((r.limit_times or 1) for r in today_up) if ready else Counter()
        prev_codes = {r.stock_code for r in prev_up}
        promoted = len(prev_codes & {r.stock_code for r in today_up}) if ready and prev_ready else None
        pcts = {}
        if ready and prev_ready and prev_codes:
            quotes = session.exec(select(StockDailyQuote).where(
                StockDailyQuote.trade_date == d, StockDailyQuote.stock_code.in_(prev_codes)
            )).all()
            pcts = {r.stock_code: r.change_pct for r in quotes if r.change_pct is not None}
            pcts.update({r.stock_code: r.pct_chg for r in today_rows
                         if r.stock_code in prev_codes and r.pct_chg is not None})
        return {
            "ready": ready,
            "first_board": groups.get(1, 0) if ready else None,
            "second_board": groups.get(2, 0) if ready else None,
            "higher_board": sum(n for b, n in groups.items() if b >= 3) if ready else None,
            "max_board": max(groups, default=0) if ready else None,
            "leaders": [{"code": r.stock_code, "name": r.name, "boards": r.limit_times or 1}
                        for r in today_up if (r.limit_times or 1) == max(groups, default=0)][:8] if ready else [],
            "previous_count": len(prev_up) if prev_ready else None,
            "promoted": promoted,
            "promote_rate": round(promoted / len(prev_up) * 100, 2)
            if promoted is not None and prev_up else None,
            "avg_pct": round(sum(pcts.values()) / len(pcts), 2) if pcts else None,
            "quote_samples": len(pcts),
        }

    @staticmethod
    def _sectors(d, previous_date, session):
        dates = [d] + ([previous_date] if previous_date else [])
        rows = session.exec(select(SectorDaily).where(SectorDaily.trade_date.in_(dates))).all()
        result = {}
        for kind in ("industry", "concept"):
            current = sorted([r for r in rows if r.trade_date == d and r.sector_type == kind],
                             key=lambda r: (-r.change_pct, r.sector_code))
            prior = sorted([r for r in rows if r.trade_date == previous_date and r.sector_type == kind],
                           key=lambda r: (-r.change_pct, r.sector_code))
            prior_ranks = {r.sector_code: i + 1 for i, r in enumerate(prior)}
            result[kind] = [{"sector_code": r.sector_code, "sector_name": r.sector_name,
                             "change_pct": r.change_pct, "volume": r.volume, "rank": i + 1,
                             "rank_change": prior_ranks[r.sector_code] - i - 1
                             if r.sector_code in prior_ranks else None}
                            for i, r in enumerate(current)]
        return result
