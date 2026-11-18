import json
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import requests

with patch.dict(os.environ, {"AUTH_USERNAME": "test-user", "AUTH_PASSWORD": "test-only-password", "AUTH_SECRET": "test-signing-key-only-" * 3}):
    from app.services.etf_dashboard import build_dashboard
    from app.services.etf_service import EtfService
    from app.services.tushare_client import TushareClient, TushareError


class TushareTransportTests(unittest.TestCase):
    def test_http_502_is_not_empty_data_and_repeated_calls_back_off(self):
        client = TushareClient("test-private-token")
        response = Mock(status_code=502, text="body test-private-token")
        with patch("app.services.tushare_client.requests.post", return_value=response) as post:
            for _ in range(2):
                with self.assertRaisesRegex(TushareError, "HTTP 502") as error:
                    client.trade_cal(exchange="SSE")
                self.assertNotIn("test-private-token", str(error.exception))
            self.assertEqual(post.call_count, 1)
            response.json.assert_not_called()

    def test_official_protocol_preserves_fields_parameters_and_string_codes(self):
        response = Mock(status_code=200)
        response.json.return_value = {"code": 0, "data": {"fields": ["ts_code", "close"], "items": [["000001.SZ", 12.3]]}}
        with patch("app.services.tushare_client.requests.post", return_value=response) as post:
            frame = TushareClient("test-token").daily(ts_code="000001.SZ", fields="ts_code,close")
        self.assertEqual(frame.iloc[0]["ts_code"], "000001.SZ")
        self.assertEqual(post.call_args.kwargs["json"]["params"], {"ts_code": "000001.SZ"})
        self.assertEqual(post.call_args.kwargs["json"]["fields"], "ts_code,close")
        self.assertFalse(post.call_args.kwargs["allow_redirects"])

    def test_permission_error_is_explicit_and_token_is_redacted(self):
        response = Mock(status_code=200)
        response.json.return_value = {"code": 2002, "msg": "token test-token has no permission", "data": None}
        with patch("app.services.tushare_client.requests.post", return_value=response):
            with self.assertRaisesRegex(TushareError, "no permission") as error:
                TushareClient("test-token").trade_cal()
        self.assertNotIn("test-token", str(error.exception))

    def test_timeout_and_malformed_responses_are_not_valid_empty_data(self):
        response = Mock(status_code=200)
        response.json.return_value = {"code": 0, "data": None}
        for value in (requests.Timeout("private connection details"), response):
            kwargs = {"side_effect": value} if isinstance(value, Exception) else {"return_value": value}
            with self.subTest(value=type(value).__name__), patch("app.services.tushare_client.requests.post", **kwargs):
                with self.assertRaises(TushareError) as error:
                    TushareClient("test-token").trade_cal()
                self.assertNotIn("private connection details", str(error.exception))

    def test_valid_empty_daily_response_remains_empty(self):
        response = Mock(status_code=200)
        response.json.return_value = {"code": 0, "data": {"fields": ["ts_code", "trade_date"], "items": []}}
        with patch("app.services.tushare_client.requests.post", return_value=response):
            self.assertTrue(TushareClient("test-token").fund_daily().empty)

    def test_requests_resume_after_backoff_expires(self):
        success = Mock(status_code=200)
        success.json.return_value = {"code": 0, "data": {"fields": ["value"], "items": [[1]]}}
        client = TushareClient("test-token")
        with patch("app.services.tushare_client.monotonic", side_effect=[100, 101, 132]), patch(
                "app.services.tushare_client.requests.post", side_effect=[Mock(status_code=502), success]) as post:
            with self.assertRaises(TushareError):
                client.trade_cal()
            self.assertEqual(client.trade_cal().iloc[0]["value"], 1)
            self.assertEqual(post.call_count, 2)


class EtfCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.service = EtfService(cache_dir=self.directory.name)
        self.pro = Mock()
        self.service._tushare_pro = self.pro

    @staticmethod
    def calendar():
        days = pd.date_range("2026-01-01", "2026-12-31")
        # 测试数据特意把周四元旦标为休市，不能由工作日推断。
        return pd.DataFrame({"cal_date": days.strftime("%Y%m%d"),
                             "is_open": [str(int(day.weekday() < 5 and day.strftime("%m%d") != "0101")) for day in days],
                             "exchange": "SSE"})

    def age_cache(self):
        for path in Path(self.directory.name).glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["fetched_at"] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
            path.write_text(json.dumps(payload), encoding="utf-8")

    def offline_service(self):
        offline = EtfService(cache_dir=self.directory.name)
        offline._tushare_pro = TushareClient("test-token")
        return offline

    def test_string_calendar_flags_and_holiday_are_respected(self):
        self.pro.trade_cal.return_value = self.calendar()
        days = self.service._fetch_trade_dates(date(2026, 1, 1), date(2026, 1, 5))
        self.assertEqual(days, [date(2026, 1, 2), date(2026, 1, 5)])
        self.service._fetch_trade_dates(date(2026, 1, 2), date(2026, 1, 6))
        self.assertEqual(self.pro.trade_cal.call_count, 1)

    def test_stale_calendar_survives_restart_and_failed_refresh(self):
        self.pro.trade_cal.return_value = self.calendar()
        expected = self.service._fetch_trade_dates(date(2026, 1, 1), date(2026, 1, 5))
        self.age_cache()
        offline = self.offline_service()
        with patch("app.services.tushare_client.requests.post", return_value=Mock(status_code=502)):
            actual = offline._fetch_trade_dates(date(2026, 1, 1), date(2026, 1, 5))
        self.assertEqual(actual, expected)
        self.assertEqual(offline.cache_fallbacks()[0]["resource"], "2026 年交易日历")
        # 失败的刷新不得覆盖最后一次成功的数据。
        again = EtfService(cache_dir=self.directory.name)
        self.assertEqual(len(again._frame_cache.get("calendar-2026")[1]), 365)

    def test_cross_year_calendar_does_not_duplicate_days_or_open_new_year_holiday(self):
        self.pro.trade_cal.return_value = pd.DataFrame({
            "cal_date": pd.date_range("2025-12-30", "2026-01-05").strftime("%Y%m%d"),
            "is_open": [1, 1, 0, 1, 0, 0, 1]})
        days = self.service._fetch_trade_dates(date(2025, 12, 30), date(2026, 1, 5))
        self.assertEqual(days, [date(2025, 12, 30), date(2025, 12, 31), date(2026, 1, 2), date(2026, 1, 5)])

    def test_empty_incomplete_or_invalid_calendar_is_not_cached(self):
        full = self.calendar()
        invalid = full.copy()
        invalid.loc[0, "is_open"] = "unknown"
        for frame in (pd.DataFrame(), full[full.cal_date != "20260102"], invalid):
            with self.subTest(rows=len(frame)):
                self.pro.trade_cal.return_value = frame
                with self.assertRaisesRegex(RuntimeError, "暂无可用缓存"):
                    self.service._fetch_trade_dates(date(2026, 1, 1), date(2026, 1, 5))
                self.assertFalse(list(Path(self.directory.name).glob("*.json")))

    def test_cached_calendar_must_cover_the_requested_range(self):
        self.pro.trade_cal.return_value = self.calendar().iloc[:5]
        self.service._fetch_trade_dates(date(2026, 1, 1), date(2026, 1, 5))
        offline = self.offline_service()
        with patch("app.services.tushare_client.requests.post", return_value=Mock(status_code=502)):
            with self.assertRaises(RuntimeError):
                offline._fetch_trade_dates(date(2026, 1, 1), date(2026, 1, 6))

    def seed_dashboard(self):
        self.pro.trade_cal.return_value = self.calendar()
        self.pro.fund_basic.return_value = pd.DataFrame([{"ts_code": "510001.SH", "name": "测试ETF", "status": "L"}])

        def daily(trade_date):
            day = datetime.strptime(trade_date, "%Y%m%d").date()
            return pd.DataFrame([{"ts_code": "510001.SH", "trade_date": trade_date,
                                  "close": 1 + (day-date(2026, 1, 1)).days / 1000,
                                  "pct_chg": 1, "amount": 20000}])
        self.pro.fund_daily.side_effect = daily
        result = build_dashboard(self.service, date(2026, 11, 16))
        self.age_cache()
        return result

    def test_outage_serves_last_real_quotes_and_all_windows_after_restart(self):
        expected = self.seed_dashboard()
        offline = self.offline_service()
        with patch("app.services.tushare_client.requests.post", return_value=Mock(status_code=502)) as post:
            actual = build_dashboard(offline, date(2026, 11, 17))
            self.assertEqual(post.call_count, 1)
        self.assertEqual(actual["effective_date"], "2026-11-16")
        self.assertEqual(actual["target_date"], "2026-11-17")
        self.assertEqual(actual["items"], expected["items"])
        self.assertEqual(actual["base_dates"], expected["base_dates"])
        self.assertEqual(actual["missing_windows"], [])
        self.assertEqual(len(actual["cache_fallbacks"]), 7)

    def test_missing_uncached_baseline_is_null_instead_of_invented(self):
        original = self.seed_dashboard()
        baseline = original["base_dates"]["20"].replace("-", "")
        (Path(self.directory.name) / f"daily-{baseline}.json").unlink()
        with patch("app.services.tushare_client.requests.post", return_value=Mock(status_code=502)):
            result = build_dashboard(self.offline_service(), date(2026, 11, 17))
        self.assertEqual(result["missing_windows"], [20])
        self.assertIsNone(result["items"][0]["gain_20"])
        self.assertIsNotNone(result["items"][0]["gain_5"])

    def test_wrong_quote_date_is_not_cached(self):
        self.pro.fund_daily.return_value = pd.DataFrame([{"ts_code": "510001.SH", "trade_date": "20261117", "close": 1, "pct_chg": 1, "amount": 20000}])
        with self.assertRaises(RuntimeError):
            self.service._fetch_etf_daily_for_date(date(2026, 11, 16))
        self.assertIsNone(self.service._frame_cache.get("daily-20261116"))

    def test_corrupted_disk_cache_can_be_repaired_by_live_data(self):
        path = Path(self.directory.name) / "calendar-2026.json"
        path.write_text("{broken JSON", encoding="utf-8")
        self.pro.trade_cal.return_value = self.calendar()
        result = self.service._fetch_trade_dates(date(2026, 1, 1), date(2026, 1, 5))
        self.assertEqual(result, [date(2026, 1, 2), date(2026, 1, 5)])
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["version"], 1)


if __name__ == "__main__":
    unittest.main()
