"""补齐最近三个真实交易日；日期较新或已有一行不代表整个数据集完整。"""
from datetime import timedelta

from sqlalchemy import func
from sqlmodel import select

from ..models import DragonTigerDaily, IndexDaily, LimitUpDaily, MarketDailyStat, SectorDaily
from .dashboard_service import DashboardService
from .job_monitor import record_progress
from .overview_service import OverviewService
from .review_service import ReviewService


class DailySyncService:
    def __init__(self, overview=None, review=None):
        self.overview = overview or OverviewService()
        self.review = review or ReviewService()

    def sync_recent(self, target, session):
        days = self.overview.fetch_trade_dates(target-timedelta(days=45), target)[-3:]
        if not days:
            record_progress(skipped=1, confirmed_skip=True, message="官方日历确认区间内无交易日", unit="数据集")
            return
        for day in days:
            self._sync_market(day, session)
            for kind in ("industry", "concept"):
                column = SectorDaily.trade_date
                count = session.exec(select(func.count()).select_from(SectorDaily).where(column == day, SectorDaily.sector_type == kind)).one()
                previous = session.exec(select(func.max(column)).where(column < day, SectorDaily.sector_type == kind)).first()
                reference = session.exec(select(func.count()).select_from(SectorDaily).where(column == previous, SectorDaily.sector_type == kind)).one() if previous else 0
                if count and count >= reference*.85:
                    record_progress(skipped=1, confirmed_skip=True, unit="数据集")
                    continue
                self._run(lambda: self.overview.sync_sector_ranking_for_date(day, kind, session), f"{day} {kind} 板块", session)

            stat = session.exec(select(MarketDailyStat).where(MarketDailyStat.stat_date == day)).first()
            counts = dict(session.exec(select(LimitUpDaily.limit_type, func.count()).where(LimitUpDaily.trade_date == day).group_by(LimitUpDaily.limit_type)).all())
            limit_complete = stat is not None and stat.total > 0 and all(counts.get(kind, 0) == expected for kind, expected in
                                                     (("U", stat.limit_up), ("D", stat.limit_down), ("Z", stat.opened_limit)))
            if limit_complete:
                record_progress(skipped=1, confirmed_skip=True, unit="数据集")
            else:
                self._run(lambda: self.review.sync_limit_daily(day, session, strict=True), f"{day} 涨跌停明细", session)
            dragon = session.exec(select(DragonTigerDaily.id).where(DragonTigerDaily.trade_date == day).limit(1)).first()
            if dragon:
                record_progress(skipped=1, confirmed_skip=True, unit="数据集")
            else:
                self._run(lambda: self.review.sync_dragon_tiger_daily(day, session, strict=True), f"{day} 龙虎榜", session)

    def _sync_market(self, day, session):
        stat = session.exec(select(MarketDailyStat).where(MarketDailyStat.stat_date == day)).first()
        codes = set(session.exec(select(IndexDaily.code).where(IndexDaily.trade_date == day)).all())
        ready = (stat is not None and stat.total > 0 and stat.up+stat.down+stat.flat == stat.total
                 and stat.total_turnover > 0 and set(self.overview.INDEX_CODES).issubset(codes))
        if ready:
            record_progress(skipped=2, confirmed_skip=True, unit="数据集")
            return
        try:
            result = DashboardService.sync_daily(day, session)
            record_progress(succeeded=2, written_rows=result["indices_count"]+1, unit="数据集")
        except ValueError:
            session.rollback()
            record_progress(deferred=2, message=f"{day} 统计或指数尚未齐备，保留旧数据，等待补齐", unit="数据集")
        except Exception as error:
            session.rollback()
            record_progress(failed=1, message=f"{day} 统计/指数同步失败：{error}", unit="数据集")

    @staticmethod
    def _run(sync, label, session):
        try:
            count = sync()
            record_progress(succeeded=int(count > 0), deferred=int(count == 0), written_rows=count,
                            message=f"{label}：{'已写入' if count else '未返回有效数据，等待后续补齐'}", unit="数据集")
        except Exception as error:
            session.rollback()
            record_progress(failed=1, message=f"{label}：{error}", unit="数据集")
