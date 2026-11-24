from collections import Counter
from datetime import date, datetime, timedelta, timezone
from statistics import median

from sqlmodel import select
from ..models import (LimitUpDaily, MarketDailyStat, StockDailyQuote, Stock,
                      ReviewObservation, ReviewVerification)
from .dashboard_service import DashboardService


def today_shanghai():
    return datetime.now(timezone(timedelta(hours=8))).date()


class ReviewWorkbench:
    @staticmethod
    def dates(session, target=None):
        d = target or session.exec(select(MarketDailyStat.stat_date)
            .where(MarketDailyStat.stat_date <= today_shanghai())
            .order_by(MarketDailyStat.stat_date.desc()).limit(1)).first() or today_shanghai()
        current = session.exec(select(MarketDailyStat).where(MarketDailyStat.stat_date == d)).first()
        previous = session.exec(select(MarketDailyStat).where(MarketDailyStat.stat_date < d)
                                .order_by(MarketDailyStat.stat_date.desc()).limit(1)).first()
        return d, current, previous

    @staticmethod
    def performance(session, d, current, previous):
        days = [d] + ([previous.stat_date] if previous else [])
        limits = session.exec(select(LimitUpDaily).where(LimitUpDaily.trade_date.in_(days))).all()
        today = [r for r in limits if r.trade_date == d]
        prev = [r for r in limits if previous and r.trade_date == previous.stat_date and r.limit_type == "U"]
        counts = Counter(r.limit_type for r in today)
        ready = bool(current is not None and counts['U'] == current.limit_up
                     and counts['D'] == current.limit_down and counts['Z'] == current.opened_limit)
        prev_ready = previous is not None and len(prev) == previous.limit_up
        codes = {r.stock_code for r in prev}
        quotes = session.exec(select(StockDailyQuote).where(
            StockDailyQuote.trade_date == d, StockDailyQuote.stock_code.in_(codes))).all() if codes else []
        pct = {r.stock_code: r.change_pct for r in quotes if r.change_pct is not None}
        by_code = {r.stock_code: r for r in today}
        pct.update({r.stock_code: r.pct_chg for r in today if r.pct_chg is not None})
        items = []
        for old in prev:
            now = by_code.get(old.stock_code)
            value = pct.get(old.stock_code)
            status = {"U": "晋级", "D": "跌停", "Z": "炸板"}.get(now.limit_type) if now else None
            if status is None:
                status = "未知" if value is None else "红盘" if value > 0 else "绿盘" if value < 0 else "平盘"
            items.append({"code": old.stock_code, "name": old.name,
                          "prev_boards": old.limit_times or 1, "today_pct": value,
                          "today_boards": now.limit_times if now and now.limit_type == "U" else None,
                          "status": status})
        values = [r['today_pct'] for r in items if r['today_pct'] is not None]
        promoted = sum(r['status'] == '晋级' for r in items)
        full = ready and prev_ready
        groups = []
        for low, high, label in [(1, 1, "对比日首板"), (2, 2, "对比日二板"), (3, 999, "对比日三板及以上")]:
            subset = [r for r in items if low <= r['prev_boards'] <= high]
            groups.append({"label": label, "total": len(subset), "continued": sum(r['status'] == '晋级' for r in subset) if full else None,
                           "rate": round(sum(r['status'] == '晋级' for r in subset)/len(subset)*100, 1) if full and subset else None})
        max_before = max((r['prev_boards'] for r in items), default=0)
        return {"trade_date": d.isoformat(), "prev_date": previous.stat_date.isoformat() if previous else None,
                "ready": full, "groups": groups, "leaders": [r for r in items if r['prev_boards'] == max_before],
                "stats": {"total": len(items), "promoted": promoted if full else None,
                          "promote_rate": round(promoted/len(items)*100, 1) if full and items else None,
                          "opened": sum(r['status'] == '炸板' for r in items) if full else None,
                          "limit_down": sum(r['status'] == '跌停' for r in items) if full else None,
                          "avg_pct": round(sum(values)/len(values), 2) if values else None,
                          "median_pct": round(median(values), 2) if values else None, "quote_samples": len(values),
                          "unknown": sum(r['status'] == '未知' for r in items)},
                "items": sorted(items, key=lambda r: (-r['prev_boards'], r['today_pct'] is None, -(r['today_pct'] or 0), r['code']))}

    def get(self, session, target=None, include_observations=True):
        d, current, previous = self.dates(session, target)
        performance = self.performance(session, d, current, previous)
        rows = session.exec(select(LimitUpDaily).where(LimitUpDaily.trade_date == d, LimitUpDaily.limit_type == 'U')).all()
        ready = current is not None and len(rows) == current.limit_up
        counts = Counter(r.limit_times or 1 for r in rows)
        return {"date": d.isoformat(), "previous_date": previous.stat_date.isoformat() if previous else None,
                "snapshot": DashboardService._snapshot(current), "performance": performance,
                "structure": {"ready": ready, "first": counts[1] if ready else None,
                              "second": counts[2] if ready else None,
                              "higher": sum(v for k,v in counts.items() if k >= 3) if ready else None,
                              "highest": max(counts, default=0) if ready else None},
                "available_dates": [v.isoformat() for v in session.exec(select(MarketDailyStat.stat_date).where(
                    MarketDailyStat.stat_date <= today_shanghai()).order_by(MarketDailyStat.stat_date)).all()],
                "observations": self.observations(session, d) if include_observations else []}

    @staticmethod
    def observations(session, d, records=None):
        observations = records if records is not None else session.exec(select(ReviewObservation).where(ReviewObservation.observation_date <= d)
            .order_by(ReviewObservation.observation_date.desc(), ReviewObservation.id.desc()).limit(500)).all()
        from .review_records import chunks, latest_records
        codes = {r.stock_code for r in observations}
        names = {}
        for batch in chunks(list(codes)):
            names.update({r.code: r.name for r in session.exec(select(Stock).where(Stock.code.in_(batch))).all()})
        ids = [r.id for r in observations]
        latest = latest_records(session, ReviewVerification, ids, ReviewVerification.review_date, d)
        prices = {}
        for batch in chunks(observations):
            dates = {r.observation_date for r in batch} | {d}
            quotes = session.exec(select(StockDailyQuote.stock_code, StockDailyQuote.trade_date, StockDailyQuote.close).where(
                StockDailyQuote.stock_code.in_({r.stock_code for r in batch}), StockDailyQuote.trade_date.in_(dates))).all()
            prices.update({(code, day): close for code, day, close in quotes})
        result = []
        for r in observations:
            base, current = prices.get((r.stock_code, r.observation_date)), prices.get((r.stock_code, d))
            v = latest.get(r.id)
            result.append({"id": r.id, "code": r.stock_code, "name": names.get(r.stock_code, r.stock_code),
                           "observation_date": r.observation_date.isoformat(), "reason": r.reason,
                           "criterion": r.criterion, "deadline": r.deadline.isoformat(),
                           "created_at": r.created_at.replace(tzinfo=timezone.utc).isoformat(),
                           "base_close": base, "close": current,
                           "price_change": round((current/base-1)*100, 2) if base and base > 0 and current is not None else None,
                           "verdict": v.verdict if v else "待验证", "explanation": v.explanation if v else "",
                           "verified_on": v.review_date.isoformat() if v else None,
                           "verified_at": v.updated_at.replace(tzinfo=timezone.utc).isoformat() if v else None})
        return result
