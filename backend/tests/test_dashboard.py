import os
import unittest
from datetime import date
from unittest.mock import patch

with patch.dict(os.environ, {
    "AUTH_USERNAME": "test-user", "AUTH_PASSWORD": "test-password-only",
    "AUTH_SECRET": "test-signing-key-only-" * 3,
}):
    from sqlmodel import SQLModel, Session, create_engine, select
    from app.models import IndexDaily, LimitUpDaily, MarketDailyStat, SectorDaily, StockDailyQuote
    from app.services.dashboard_service import DashboardService
    from app.services.overview_service import OverviewService


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)
        self.service = DashboardService()
        self.before = date(2026, 1, 5)
        self.today = date(2026, 1, 6)

    def stat(self, day, **values):
        data = dict(up=3, down=2, flat=0, total=5, total_turnover=1000000000,
                    limit_up=2, limit_down=1, opened_limit=1)
        data.update(values)
        self.session.add(MarketDailyStat(stat_date=day, **data))
        self.session.commit()

    def indices(self, day):
        for code, name in OverviewService.INDEX_CODES.items():
            self.session.add(IndexDaily(code=code, name=name, trade_date=day,
                open=10, high=12, low=9, close=11, volume=100, amount=1000,
                change=1, change_pct=10))
        self.session.commit()

    def limits(self, day, codes):
        for i, code in enumerate(codes):
            self.session.add(LimitUpDaily(stock_code=code, name=code, trade_date=day,
                limit_type="U", limit_times=i + 1, pct_chg=10))
        self.session.commit()

    def test_empty_cache_does_not_fabricate_zero_stats(self):
        result = self.service.get_dashboard(self.today, self.session)
        self.assertEqual(result["status"], "missing")
        self.assertIsNone(result["current"])
        self.assertIsNone(result["updated_at"])
        self.assertIsNone(result["short_term"]["first_board"])

    def test_comparisons_and_averages_exclude_current_and_future(self):
        self.stat(self.before)
        self.stat(self.today, total_turnover=2000000000)
        self.stat(date(2026, 1, 7), total_turnover=9000000000)
        self.indices(self.today)
        result = self.service.get_dashboard(self.today, self.session)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["previous"]["date"], self.before.isoformat())
        self.assertEqual(result["turnover_average"], 1000000000)
        self.assertEqual(result["turnover_average_days"], 1)
        self.assertEqual(result["current"]["up_ratio"], 60)
        self.assertAlmostEqual(result["current"]["break_rate"], 33.33)
        self.assertTrue(all(r["date"] <= self.today.isoformat() for r in result["history"]))
        self.assertTrue(result["updated_at"].endswith("+00:00"))

    def test_legacy_missing_breadth_and_turnover_are_null(self):
        self.stat(self.today, up=0, down=0, total=0, total_turnover=0)
        result = self.service.get_dashboard(self.today, self.session)
        self.assertEqual(result["status"], "partial")
        self.assertIsNone(result["current"]["up_ratio"])
        self.assertIsNone(result["current"]["total_turnover"])
        self.assertIsNone(result["current"]["up"])

    def test_missing_date_is_not_replaced_with_another_date(self):
        self.stat(self.before)
        result = self.service.get_dashboard(self.today, self.session)
        self.assertEqual(result["date"], self.today.isoformat())
        self.assertEqual(result["latest_date"], self.before.isoformat())
        self.assertIsNone(result["current"])

    def test_short_term_coverage_and_continuation(self):
        self.stat(self.before)
        self.stat(self.today)
        self.limits(self.before, ["000001", "000002"])
        self.limits(self.today, ["000001", "000003"])
        self.session.add(StockDailyQuote(stock_code="000002", trade_date=self.today, change_pct=-4))
        self.session.commit()
        short = self.service.get_dashboard(self.today, self.session)["short_term"]
        self.assertTrue(short["ready"])
        self.assertEqual(short["promote_rate"], 50)
        self.assertEqual(short["avg_pct"], 3)
        self.assertEqual(short["quote_samples"], 2)
        self.assertEqual(short["first_board"], 1)
        self.assertEqual(short["second_board"], 1)
        self.assertEqual(short["max_board"], 2)

    def test_incomplete_limit_details_do_not_produce_fake_structure(self):
        self.stat(self.today)
        self.limits(self.today, ["000001"])
        short = self.service.get_dashboard(self.today, self.session)["short_term"]
        self.assertFalse(short["ready"])
        self.assertIsNone(short["max_board"])
        self.assertIsNone(short["promote_rate"])

    def test_sector_universe_is_not_truncated_to_top_fifty(self):
        self.stat(self.before)
        self.stat(self.today)
        for day in (self.before, self.today):
            for i in range(55):
                self.session.add(SectorDaily(sector_code=str(i), sector_name=str(i),
                    sector_type="industry", trade_date=day,
                    change_pct=i if day == self.before else -i, volume=i * 100))
        self.session.commit()
        sectors = self.service.get_dashboard(self.today, self.session)["sectors"]["industry"]
        self.assertEqual(len(sectors), 55)
        self.assertEqual(max(sectors, key=lambda r: r["volume"])["sector_code"], "54")
        self.assertEqual(sectors[0]["rank_change"], 54)

    def test_sync_failure_keeps_existing_cache(self):
        self.stat(self.today)
        with patch.object(OverviewService, "fetch_market_stats_for_date", return_value=({}, False)):
            with self.assertRaises(ValueError):
                self.service.sync_daily(self.today, self.session)
        self.assertEqual(self.session.exec(select(MarketDailyStat)).one().total_turnover, 1000000000)

    def test_missing_index_during_sync_keeps_all_existing_values(self):
        self.stat(self.today)
        self.indices(self.today)
        with patch.object(OverviewService, "fetch_market_stats_for_date", return_value=({}, True)), \
             patch.object(OverviewService, "fetch_index_for_date", return_value=None):
            with self.assertRaises(ValueError):
                self.service.sync_daily(self.today, self.session)
        self.assertEqual(len(self.session.exec(select(IndexDaily)).all()), 5)
        self.assertEqual(self.session.exec(select(MarketDailyStat)).one().total_turnover, 1000000000)


if __name__ == "__main__":
    unittest.main()
