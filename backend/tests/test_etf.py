import os
import unittest
from datetime import date, timedelta
from unittest.mock import patch, Mock
import pandas as pd

with patch.dict(os.environ, {"AUTH_USERNAME": "test-user", "AUTH_PASSWORD": "test-only-password", "AUTH_SECRET": "test-signing-key-only-" * 3}):
    from app.services.etf_dashboard import summarize, build_dashboard
    from app.services.etf_service import _extract_category, EtfService


class EtfTests(unittest.TestCase):
    def result(self, basic, daily, bases=None, threshold=10000000):
        return summarize(basic, daily, bases or {}, '2026-11-16', '2026-11-16', {}, threshold)

    def test_units_liquidity_and_non_etf_exclusion(self):
        basic = [{"code": "1", "name": "芯片ETF"}, {"code": "2", "name": "普通LOF"}, {"code": "3", "name": "银行ETF"}]
        daily = [{"code": c, "close": 1, "amount": amount} for c, amount in [('1', 10000), ('2', 20000), ('3', 9999)]]
        result = self.result(basic, daily)
        self.assertEqual([r['code'] for r in result['items']], ['1'])
        self.assertEqual(result['items'][0]['amount'], 10000000)

    def test_missing_baseline_is_null_and_zero_gain_is_preserved(self):
        result = self.result([{"code": "1", "name": "芯片ETF"}], [{"code": "1", "close": 1, "amount": 10000}], {2: {'1': 1}, 5: {'1': float('nan')}})
        item = result['items'][0]
        self.assertEqual(item['gain_2'], 0)
        self.assertIsNone(item['gain_5'])
        self.assertIsNone(result['directions'][0]['median_5'])
        self.assertEqual(item['state'], '数据不足')

    def test_group_median_samples_and_representative_liquidity(self):
        basic = [{"code": str(i), "name": "芯片ETF"} for i in range(3)]
        daily = [{"code": str(i), "close": close, "amount": (i+1)*10000} for i, close in enumerate([1,2,10])]
        result = self.result(basic, daily, {5: {'0': 1, '1': 1, '2': 1}})
        group = result['directions'][0]
        self.assertEqual(group['median_5'], 100)
        self.assertEqual(group['samples_5'], 3)
        self.assertEqual(group['positive_5'], 2)
        self.assertEqual(group['representative'], '2')

    def test_specific_classification_precedes_broad_keyword(self):
        self.assertEqual(_extract_category('新能源汽车ETF', ''), '汽车-新能源')
        self.assertEqual(_extract_category('有色金属ETF', ''), '周期-有色')
        self.assertEqual(_extract_category('有色金属期货ETF', ''), '商品-有色金属')

    def test_invalid_close_never_enters_universe(self):
        for close in (None, 0, -1, float('nan'), float('inf')):
            result = self.result([{'code': '1', 'name': '芯片ETF'}], [{'code': '1', 'close': close, 'amount': 10000}])
            self.assertFalse(result['items'])

    def test_historical_request_never_reads_future_and_reports_fallback(self):
        target = date(2026, 11, 16)
        days = [target-timedelta(days=i) for i in range(40)][::-1]
        service = Mock()
        service.cache_fallbacks.return_value = []
        service._fetch_trade_dates.return_value = days
        def daily(day):
            self.assertLessEqual(day, target)
            return pd.DataFrame() if day == target else pd.DataFrame([{'code': '1', 'close': 1, 'amount': 10000}])
        service._fetch_etf_daily_for_date.side_effect = daily
        service._get_etf_list_with_cache.return_value = pd.DataFrame([{'code': '1', 'name': '芯片ETF'}])
        result = build_dashboard(service, target)
        self.assertEqual(result['effective_date'], (target-timedelta(days=1)).isoformat())
        self.assertEqual(result['target_date'], target.isoformat())

    def test_calendar_failure_does_not_invent_weekday_trading_days(self):
        service = EtfService()
        with patch.object(service, '_get_tushare_pro', side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError):
                service._fetch_trade_dates(date(2026, 1, 1), date(2026, 1, 5))


if __name__ == '__main__':
    unittest.main()
