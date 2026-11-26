import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
from sqlmodel import select
from sqlalchemy import delete

import test_system as fixtures
from app.models import StockAdjustmentFactor, StockDailyQuote
from app.services.system_maintenance import (MaintenanceBusy, maintenance_status,
                                             start_maintenance, _launch_lock)
from app.services.system_price_coverage import price_coverage
from app.services.daily_sync import DailySyncService
from app.models import SectorDaily
from app.services.tushare_client import TushareError


class MaintenanceTests(unittest.TestCase):
    setUp = fixtures.SystemTests.setUp

    def backend(self):
        scripts = self.root / 'scripts'
        scripts.mkdir(exist_ok=True)
        for name in ('import_daily.py', 'sync_price_factors.py', 'backup_database.py'):
            (scripts / name).write_text('# test stub', encoding='utf-8')
        return self.root

    def record(self, status='success', started=None):
        self.store.write('job-daily', {'status': status, 'started_at': (started or self.now).isoformat(),
            'pid': 12345, 'message': 'actual result', 'failed': int(status == 'partial'), 'deferred': 1})

    def test_unrequested_maintenance_is_idle_not_failed(self):
        result = maintenance_status('factors', self.store, self.now)
        self.assertEqual(result['status'], 'idle')
        self.assertTrue(result['can_start'])

    def test_unsupported_action_cannot_start_any_command(self):
        with patch('app.services.system_maintenance.subprocess.Popen') as spawn:
            with self.assertRaises(ValueError):
                start_maintenance('../../unexpected', self.store, self.now, self.root)
        spawn.assert_not_called()

    def test_submit_uses_bounded_script_and_does_not_report_completion(self):
        child = Mock(pid=12345)
        with patch('app.services.system_maintenance.subprocess.Popen', return_value=child) as spawn, patch(
                'app.services.system_maintenance.process_alive', return_value=True):
            result = start_maintenance('factors', self.store, self.now, self.backend())
        command = spawn.call_args.args[0]
        self.assertEqual(command[-2:], ['--days', '35'])
        self.assertEqual(Path(command[2]).name, 'sync_price_factors.py')
        self.assertNotIn('shell', spawn.call_args.kwargs)
        self.assertEqual(result['job']['status'], 'queued')
        self.assertTrue(result['accepted'])
        self.assertIsNone(result['job']['record'])

    def test_repeated_submission_reuses_receipt_without_spawning_twice(self):
        with patch('app.services.system_maintenance.subprocess.Popen', return_value=Mock(pid=12345)) as spawn, patch(
                'app.services.system_maintenance.process_alive', return_value=True):
            first = start_maintenance('daily', self.store, self.now, self.backend())
            second = start_maintenance('daily', self.store, self.now, self.root)
        self.assertTrue(first['accepted'])
        self.assertFalse(second['accepted'])
        self.assertEqual(spawn.call_count, 1)

    def test_running_cron_is_reused_without_manual_spawn(self):
        self.record('running')
        with patch('app.services.system_maintenance.process_alive', return_value=True), patch(
                'app.services.system_maintenance.subprocess.Popen') as spawn:
            result = start_maintenance('daily', self.store, self.now, self.backend())
        self.assertFalse(result['accepted'])
        self.assertEqual(result['job']['status'], 'running')
        spawn.assert_not_called()

    def test_old_success_cannot_hide_queued_new_run(self):
        self.record(started=self.now-timedelta(hours=1))
        self.store.write('maintenance-daily', {'requested_at': self.now.isoformat(), 'pid': 12345})
        with patch('app.services.system_maintenance.process_alive', return_value=True):
            result = maintenance_status('daily', self.store, self.now)
        self.assertEqual(result['status'], 'queued')
        self.assertIsNone(result['record'])

    def test_dead_launcher_and_dead_running_job_are_interrupted(self):
        self.store.write('maintenance-daily', {'requested_at': self.now.isoformat(), 'pid': 999999999})
        self.assertEqual(maintenance_status('daily', self.store, self.now)['status'], 'interrupted')
        self.record('running')
        with patch('app.services.system_maintenance.process_alive', return_value=False):
            self.assertEqual(maintenance_status('daily', self.store, self.now)['status'], 'interrupted')

    def test_finished_record_preserves_partial_and_cooldown_then_allows_retry(self):
        self.store.write('maintenance-daily', {'requested_at': self.now.isoformat(), 'pid': 12345})
        self.record('partial')
        first = maintenance_status('daily', self.store, self.now+timedelta(seconds=10))
        self.assertEqual(first['status'], 'partial')
        self.assertFalse(first['can_start'])
        self.assertEqual(first['record']['deferred'], 1)
        self.assertTrue(maintenance_status('daily', self.store, self.now+timedelta(seconds=61))['can_start'])

    def test_failed_launch_does_not_leave_a_success_receipt(self):
        with patch('app.services.system_maintenance.subprocess.Popen', side_effect=OSError('unavailable')):
            with self.assertRaises(OSError):
                start_maintenance('backup', self.store, self.now, self.backend())
        self.assertIsNone(self.store.read('maintenance-backup'))

    def test_overlapping_launches_are_rejected(self):
        _launch_lock.acquire()
        try:
            with self.assertRaises(MaintenanceBusy):
                start_maintenance('daily', self.store, self.now, self.backend())
        finally:
            _launch_lock.release()


class PriceCoverageTests(unittest.TestCase):
    setUp = fixtures.SystemTests.setUp

    def seed(self):
        self.day = self.now.date()
        natural = pd.date_range(self.day-timedelta(days=110), self.day)
        frame = pd.DataFrame([{'cal_date': day.strftime('%Y%m%d'), 'is_open': int(day.weekday() < 5)} for day in natural])
        self.etf._frame_cache.put('calendar-2026', frame)
        self.dates = [day.date() for day in natural if day.weekday() < 5]
        self.needed = {self.dates[-1-n] for n in (0, 2, 5, 10, 20)}
        self.etf._frame_cache.put('basic', pd.DataFrame([{'code': '510300', 'name': 'fixture ETF', 'status': 'L'},
                                                                   {'code': '501000', 'name': 'fixture LOF', 'status': 'L'}]))
        for day in self.needed:
            self.session.add(StockDailyQuote(stock_code='600519', trade_date=day, close=10))
            self.session.add(StockAdjustmentFactor(stock_code='600519', trade_date=day, factor='1'))
            self.etf._frame_cache.put('daily-'+day.strftime('%Y%m%d'), pd.DataFrame([
                {'code': '510300', 'trade_date': day.strftime('%Y%m%d'), 'close': 10},
                {'code': '501000', 'trade_date': day.strftime('%Y%m%d'), 'close': 10}]))
            self.etf._frame_cache.put('factor-'+day.strftime('%Y%m%d'), pd.DataFrame([
                {'ts_code': '510300.SH', 'trade_date': day.strftime('%Y%m%d'), 'adj_factor': 1}]))
        self.session.commit()

    def report(self):
        return price_coverage(self.session, self.etf, self.day, self.day)

    def test_complete_date_pairs_are_checked_without_network_or_non_etf_samples(self):
        self.seed()
        with patch('app.services.tushare_client.requests.post') as post:
            reports = self.report()
        post.assert_not_called()
        for report in reports:
            self.assertEqual(report['status'], 'ok')
            self.assertTrue(all(row['valid'] == row['total'] == 1 for row in report['windows']))

    def test_missing_stock_factor_affects_its_interval_only(self):
        self.seed()
        self.session.exec(delete(StockAdjustmentFactor).where(StockAdjustmentFactor.trade_date == self.dates[-21]))
        self.session.commit()
        report = self.report()[0]
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(report['windows'][-1]['missing_factors'], 1)
        self.assertEqual(report['windows'][0]['valid'], 1)

    def test_future_factor_and_quote_cannot_fill_older_missing_endpoint(self):
        self.seed()
        self.session.exec(delete(StockAdjustmentFactor).where(StockAdjustmentFactor.trade_date == self.dates[-21]))
        self.session.add(StockAdjustmentFactor(stock_code='600519', trade_date=self.day+timedelta(days=1), factor='1'))
        self.session.add(StockDailyQuote(stock_code='600519', trade_date=self.day+timedelta(days=1), close=10))
        self.session.commit()
        report = self.report()[0]
        self.assertEqual(report['effective_date'], str(self.day))
        self.assertEqual(report['windows'][-1]['valid'], 0)

    def test_wrong_date_fund_factor_is_missing_not_a_valid_cached_file(self):
        self.seed()
        base = self.dates[-21]
        self.etf._frame_cache.put('factor-'+base.strftime('%Y%m%d'), pd.DataFrame([
            {'ts_code':'510300.SH', 'trade_date':self.day.strftime('%Y%m%d'), 'adj_factor':1}]))
        report = self.report()[1]
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(report['windows'][-1]['missing_factors'], 1)

    def test_invalid_stock_factor_never_counts_as_coverage(self):
        self.seed()
        row = self.session.exec(select(StockAdjustmentFactor).where(StockAdjustmentFactor.trade_date == self.day)).one()
        row.factor = 'NaN'
        self.session.add(row)
        self.session.commit()
        self.assertTrue(all(window['valid'] == 0 for window in self.report()[0]['windows']))
        table = next(row for row in self.service._table_freshness(self.session, self.day) if row['table'] == 'stock_adjustment_factor')
        self.assertEqual(table['coverage_pct'], 0)
        self.assertEqual(table['status'], 'partial')

    def test_missing_official_calendar_stays_unknown(self):
        self.seed()
        self.etf._frame_cache._memory.pop('calendar-2026', None)
        (self.etf._frame_cache.directory / 'calendar-2026.json').unlink()
        self.assertTrue(all(row['status'] == 'unknown' for row in self.report()))

    def test_latest_quotes_cannot_hide_expected_date_lag(self):
        self.seed()
        next_day = self.day+timedelta(days=1)
        reports = price_coverage(self.session, self.etf, next_day, next_day)
        self.assertTrue(all(row['status'] == 'stale' for row in reports))

    def test_no_expected_date_is_not_green_even_with_local_pairs(self):
        self.seed()
        reports = price_coverage(self.session, self.etf, None, self.day)
        self.assertTrue(all(row['status'] == 'unknown' for row in reports))


class SectorFailureTests(unittest.TestCase):
    setUp = fixtures.SystemTests.setUp

    def test_failed_concept_metadata_cannot_cache_industry_only_result(self):
        service = fixtures.OverviewService()
        client = Mock()
        industry = pd.DataFrame([{'ts_code': '881001.TI', 'name': 'industry'}])
        concept = pd.DataFrame([{'ts_code': '885001.TI', 'name': 'concept'}])
        client.ths_index.side_effect = [industry, TushareError('upstream failed')]
        with patch.object(service, '_get_tushare_pro', return_value=client):
            with self.assertRaises(TushareError):
                service._get_sector_index_info(strict=True)
            self.assertFalse(getattr(service, '_sector_index_info', {}))
            client.ths_index.side_effect = [industry, concept]
            self.assertEqual(len(service._get_sector_index_info(strict=True)), 2)

    def test_strict_sync_keeps_existing_rows_and_reports_http_failure_as_failure(self):
        day = self.now.date()
        self.session.add(SectorDaily(sector_type='industry', sector_code='881001.TI',
            sector_name='saved', trade_date=day, change_pct=1, volume=10))
        self.session.commit()
        service, client = fixtures.OverviewService(), Mock()
        client.ths_daily.side_effect = TushareError('upstream HTTP 502')
        with patch.object(service, '_get_tushare_pro', return_value=client), patch.object(
                service, '_get_sector_index_info', return_value={'881001.TI': {'type':'industry', 'name':'saved'}}):
            @fixtures.tracked_job('daily')
            def execute():
                DailySyncService._run(lambda: service.sync_sector_ranking_for_date(day, 'industry', self.session), 'sector', self.session)
            execute()
        result = self.store.read('job-daily')
        self.assertEqual(result['failed'], 1)
        self.assertEqual(result['deferred'], 0)
        self.assertEqual(self.session.exec(select(SectorDaily.sector_name)).all(), ['saved'])

    def test_true_empty_daily_response_remains_deferred_not_an_exception(self):
        service, client = fixtures.OverviewService(), Mock()
        client.ths_daily.return_value = pd.DataFrame()
        with patch.object(service, '_get_tushare_pro', return_value=client), patch.object(
                service, '_get_sector_index_info', return_value={'881001.TI': {'type':'industry', 'name':'saved'}}):
            self.assertEqual(service.sync_sector_ranking_for_date(self.now.date(), 'industry', self.session), 0)

    def test_wrong_date_daily_response_is_rejected_and_read_fallback_is_empty(self):
        service, client = fixtures.OverviewService(), Mock()
        client.ths_daily.return_value = pd.DataFrame([{'ts_code':'881001.TI', 'trade_date':'20261118', 'pct_change':1, 'vol':1}])
        with patch.object(service, '_get_tushare_pro', return_value=client), patch.object(
                service, '_get_sector_index_info', return_value={'881001.TI': {'type':'industry', 'name':'saved'}}):
            with self.assertRaises(RuntimeError):
                service.sync_sector_ranking_for_date(self.now.date(), 'industry', self.session)
            self.assertEqual(service._fetch_sector_daily_from_tushare(self.now.date()), {'industry':[], 'concept':[]})


if __name__ == '__main__':
    unittest.main()
