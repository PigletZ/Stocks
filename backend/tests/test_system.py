import json
import os
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

with patch.dict(os.environ, {"AUTH_USERNAME": "test-user", "AUTH_PASSWORD": "test-only-password", "AUTH_SECRET": "test-signing-key-only-" * 3}):
    from pydantic import ValidationError
    from sqlmodel import SQLModel, Session, create_engine, select
    from app.models import IndexDaily, MarketDailyStat, SectorDaily, Stock, StockDailyQuote
    from app.services.etf_service import EtfService
    from app.services.job_monitor import JobRun, record_progress, tracked_job
    from app.services.runtime_state import RuntimeStore, SystemPreferences, get_preferences, save_preferences
    from app.services.system_diagnostics import SystemDiagnostics
    from app.services.system_jobs import JOBS, discover_schedules, job_statuses, schedule_times
    from app.services.system_service import SystemService, expected_trade_date
    from app.services.tushare_client import TushareError
    from app.services.tushare_client import TushareClient
    from app.services.tushare_stock_service import TushareStockService
    from app.services.overview_service import OverviewService
    from app.services.financial_service import FinancialService
    from scripts.backup_database import backup_database

UTC = timezone.utc


class SystemTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.store = RuntimeStore(self.root / 'system')
        patcher = patch('app.services.runtime_state.settings.system_state_dir', str(self.store.directory))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.engine = create_engine('sqlite://')
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)
        self.now = datetime(2026, 11, 19, 14, tzinfo=UTC)  # 北京时间 22:00
        self.discovered = ({job['key']: [] for job in JOBS}, True)
        self.etf = EtfService(cache_dir=self.root / 'etf')
        self.service = SystemService(self.store, self.etf, self.now, self.root / 'logs', self.discovered)

    def index(self, day, code='000001'):
        self.session.add(IndexDaily(code=code, name=code, trade_date=day, open=1, high=1, low=1,
                                    close=1, volume=1, amount=1, change=0, change_pct=0))
        self.session.commit()

    def test_holidays_and_ready_time_use_real_calendar_and_shanghai_time(self):
        days = [date(2026, 9, 30), date(2026, 10, 9)]
        self.assertEqual(expected_trade_date(days, datetime(2026, 10, 7, 15, tzinfo=UTC), 21), date(2026, 9, 30))
        self.assertEqual(expected_trade_date(days, datetime(2026, 10, 9, 12, tzinfo=UTC), 21), date(2026, 9, 30))
        self.assertEqual(expected_trade_date(days, datetime(2026, 10, 9, 13, tzinfo=UTC), 21), date(2026, 10, 9))

    def test_status_refresh_never_calls_tushare_and_unknown_calendar_is_not_green(self):
        for code in OverviewService.INDEX_CODES:
            self.index(date(2026, 11, 19), code)
        with patch('app.services.tushare_client.requests.post') as post:
            result = self.service.get_status(self.session)
        post.assert_not_called()
        indices = next(row for row in result['tables'] if row['table'] == 'indexdaily')
        self.assertEqual(indices['status'], 'unknown')
        self.assertIsNone(result['summary']['expected_date'])
        self.assertGreater(result['summary']['alert_count'], 0)
        self.assertEqual(result['summary']['data_total'], 8)
        self.assertTrue(result['generated_at'].endswith('+00:00'))

    def test_fresh_max_date_with_one_index_is_incomplete(self):
        self.index(date(2026, 11, 19))
        rows = self.service._table_freshness(self.session, date(2026, 11, 19))
        index = next(row for row in rows if row['table'] == 'indexdaily')
        self.assertEqual(index['status'], 'partial')
        self.assertEqual(index['coverage_pct'], 20)

    def test_one_trading_day_behind_is_stale_without_three_day_grace(self):
        self.index(date(2026, 11, 18))
        row = next(row for row in self.service._table_freshness(self.session, date(2026, 11, 19)) if row['table'] == 'indexdaily')
        self.assertEqual(row['status'], 'stale')
        self.assertEqual(row['rows'], 0)

    def test_snapshot_pool_coverage_uses_only_valid_prices(self):
        for i in range(10):
            code = f'6000{i:02d}'
            self.session.add(Stock(code=code, name=code, exchange='SH'))
            self.session.add(StockDailyQuote(stock_code=code, trade_date=date(2026, 11, 19), close=1 if i == 0 else None))
        self.session.commit()
        row = next(row for row in self.service._table_freshness(self.session, date(2026, 11, 19)) if row['table'] == 'stockdailyquote')
        self.assertEqual(row['status'], 'partial')
        self.assertEqual(row['rows'], 10)
        self.assertEqual(row['coverage_pct'], 10)

    def test_market_totals_must_reconcile(self):
        self.session.add(MarketDailyStat(stat_date=date(2026, 11, 19), up=1, down=1, total=100, total_turnover=1000))
        self.session.commit()
        row = self.service._table_freshness(self.session, date(2026, 11, 19))[0]
        self.assertEqual(row['status'], 'partial')

    def test_preferences_are_bounded_and_cannot_accept_credentials(self):
        for values in ({'request_timeout': 0}, {'etf_snapshot_limit': 1}, {'auth_password': 'not-allowed'}, {'request_timeout': True}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                SystemPreferences(**values)
        saved = SystemPreferences(request_timeout=20, data_ready_hour=22)
        save_preferences(saved, self.store)
        self.assertEqual(get_preferences(self.store).request_timeout, 20)
        self.assertEqual(self.service._configuration()['preferences_status'], 'ok')

    def test_corrupted_preferences_fall_back_and_are_reported(self):
        self.store.directory.mkdir()
        self.store.path('preferences').write_text('{broken', encoding='utf-8')
        self.assertEqual(get_preferences(self.store).request_timeout, 10)
        self.assertEqual(self.service._configuration()['preferences_status'], 'error')

    def test_saved_timeout_is_applied_to_subsequent_requests(self):
        save_preferences(SystemPreferences(request_timeout=20), self.store)
        response = Mock(status_code=200)
        response.json.return_value = {'code':0, 'data':{'fields':[], 'items':[]}}
        with patch('app.services.tushare_client.requests.post', return_value=response) as post:
            TushareClient('test-token').daily()
        self.assertEqual(post.call_args.kwargs['timeout'], 20)

    def test_job_counts_partial_failure_and_redacts_credentials(self):
        with patch('app.services.runtime_state.settings.tushare_token', 'private-token-for-test'):
            run = JobRun('quotes', self.store)
            run.write(force=True)
            run.record(succeeded=2, failed=1, written_rows=10, message='private-token-for-test failed')
            run.finish()
        saved = self.store.read('job-quotes')
        self.assertEqual(saved['status'], 'partial')
        self.assertEqual(saved['succeeded'], 2)
        self.assertEqual(saved['written_rows'], 10)
        self.assertNotIn('private-token-for-test', json.dumps(saved))
        self.assertTrue(saved['finished_at'].endswith('+00:00'))

    def test_decorator_records_error_before_reraising(self):
        @tracked_job('daily')
        def fail():
            raise RuntimeError('example upstream error')
        with self.assertRaises(RuntimeError):
            fail()
        saved = self.store.read('job-daily')
        self.assertEqual(saved['status'], 'error')
        self.assertEqual(saved['failed'], 1)

    def test_empty_results_are_unknown_but_confirmed_holiday_is_skipped(self):
        run = JobRun('bars', self.store)
        run.record(skipped=1, message='No quotes')
        run.finish()
        self.assertEqual(self.store.read('job-bars')['status'], 'unknown')
        holiday = JobRun('daily', self.store)
        holiday.record(skipped=1, confirmed_skip=True)
        holiday.finish()
        self.assertEqual(self.store.read('job-daily')['status'], 'skipped')

    def test_duplicate_job_does_not_overwrite_running_record(self):
        calls = []
        @tracked_job('quotes')
        def execute():
            calls.append(1)
            execute()
            record_progress(succeeded=1, unit='交易日')
        execute()
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.store.read('job-quotes')['status'], 'success')

    def test_old_log_mtime_cannot_prove_task_success(self):
        folder = self.root / 'logs'
        folder.mkdir()
        (folder / 'sync_quotes.log').write_text('任务完成\n', encoding='utf-8')
        rows = job_statuses(self.now, folder, self.store, self.discovered)
        row = next(job for job in rows if job['key'] == 'quotes')
        self.assertEqual(row['status'], 'unverified')
        self.assertIsNone(row['last_run'])
        self.assertIsNotNone(row['log_updated_at'])

    def test_success_record_takes_precedence_over_old_error_log(self):
        folder = self.root / 'logs'
        folder.mkdir()
        (folder / 'sync_quotes.log').write_text('旧记录失败\n', encoding='utf-8')
        self.store.write('job-quotes', {'status':'success', 'started_at':self.now.isoformat(), 'finished_at':self.now.isoformat(), 'message':'完成'})
        row = next(job for job in job_statuses(self.now, folder, self.store, self.discovered) if job['key'] == 'quotes')
        self.assertEqual(row['status'], 'success')

    def test_dead_process_is_interrupted_instead_of_running_forever(self):
        self.store.write('job-quotes', {'status':'running', 'pid':999999999, 'started_at':self.now.isoformat(), 'message':'运行'})
        row = next(job for job in job_statuses(self.now, self.root / 'logs', self.store, self.discovered) if job['key'] == 'quotes')
        self.assertEqual(row['status'], 'interrupted')

    def test_schedule_matches_weekdays_and_both_real_snapshot_invocations(self):
        cron = '20 16 * * 1-5 python scripts/sync_strategy_data.py --skip-bars\n40 16 * * 1-5 python scripts/sync_strategy_data.py --bar-days 10\n'
        with patch('app.services.system_jobs.subprocess.run', return_value=Mock(returncode=0, stdout=cron)):
            schedules, known = discover_schedules(self.now)
        self.assertTrue(known)
        self.assertEqual(len(schedules['quotes']), 2)
        self.assertEqual(len(schedules['bars']), 1)
        previous, upcoming = schedule_times('20 16 * * 1-5', datetime(2026, 11, 21, 2, tzinfo=UTC), timezone(timedelta(hours=8)))
        self.assertEqual(previous.date(), date(2026, 11, 20))
        self.assertEqual(upcoming.date(), date(2026, 11, 23))

    def test_overdue_schedule_does_not_keep_old_success_green(self):
        self.store.write('job-quotes', {'status':'success', 'started_at':(self.now-timedelta(days=1)).isoformat(), 'message':'完成'})
        plans = {key: list(value) for key,value in self.discovered[0].items()}
        plans['quotes'] = [{'previous':(self.now-timedelta(hours=1)).isoformat(), 'next':None, 'expression':'0 16 * * *', 'timezone':'UTC'}]
        row = next(job for job in job_statuses(self.now, self.root / 'logs', self.store, (plans, True)) if job['key'] == 'quotes')
        self.assertEqual(row['status'], 'stale')

    def test_diagnostics_distinguish_http_failure_and_throttle_repeated_checks(self):
        diagnostics = SystemDiagnostics(self.store)
        with patch('app.services.runtime_state.settings.tushare_token', 'private-token-for-test'), patch(
                'app.services.tushare_client.requests.post', return_value=Mock(status_code=502)) as post:
            report = diagnostics.run()
            repeated = diagnostics.run()
        self.assertEqual(post.call_count, 7)
        self.assertEqual(report['status'], 'error')
        self.assertTrue(all(item['http_status'] == 502 for item in report['checks']))
        self.assertEqual(repeated['checked_at'], report['checked_at'])
        self.assertNotIn('private-token-for-test', json.dumps(report))

    def test_old_diagnostic_is_unknown_instead_of_current_success(self):
        self.store.write('diagnostics', {'checked_at':(self.now-timedelta(hours=1)).isoformat(), 'checks':[{'key':'calendar','status':'ok'}]})
        report = SystemDiagnostics(self.store).get_report(self.now)
        self.assertFalse(report['fresh'])
        self.assertEqual(report['status'], 'unknown')

    def test_successful_diagnostic_warms_real_calendar_cache_without_writing_quotes(self):
        def respond(url, json, **kwargs):
            api, params = json['api_name'], json['params']
            if api == 'trade_cal':
                days = pd.date_range(params['start_date'], params['end_date'])
                fields = ['exchange','cal_date','is_open']
                items = [['SSE',day.strftime('%Y%m%d'),int(day.weekday()<5)] for day in days]
            elif api in {'daily','index_daily','fund_daily'}:
                fields, items = ['ts_code','trade_date','close'], [[params['ts_code'],'20261119',1]]
            else:
                fields, items = ['ts_code','end_date'], [[params['ts_code'],'20260930']]
            response = Mock(status_code=200)
            response.json.return_value = {'code':0,'data':{'fields':fields,'items':items}}
            return response
        with patch('app.services.runtime_state.settings.tushare_token', 'test-token'), patch(
                'app.services.system_diagnostics.utc_now', return_value=self.now), patch(
                'app.services.system_diagnostics.EtfService', return_value=self.etf), patch(
                'app.services.tushare_client.requests.post', side_effect=respond):
            result = SystemDiagnostics(self.store).run()
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(len(result['checks']), 7)
        self.assertIsNotNone(self.etf.cached_trade_dates(date(2026, 9, 20),date(2026, 11, 19)))
        self.assertFalse(list(self.etf._frame_cache.directory.glob('daily-*.json')))

    def test_state_json_contains_no_credentials(self):
        with patch('app.services.runtime_state.settings.tushare_token', 'private-token-for-test'):
            result = self.service.get_status(self.session)
        self.assertNotIn('private-token-for-test', json.dumps(result))
        self.assertTrue(result['configuration']['tushare_configured'])

    def test_pagination_failure_cannot_return_truncated_dataset(self):
        pro = Mock()
        pro.daily.side_effect = [pd.DataFrame({'ts_code': ['600001.SH']*5000}), TushareError('HTTP 502')]
        with self.assertRaises(TushareError):
            TushareStockService._fetch_all_pages(pro, 'daily')

    def test_calendar_unavailable_is_service_unavailable_in_overview_routes(self):
        from fastapi import HTTPException
        from app.routers.overview import get_trade_dates, get_market_history
        with patch.object(OverviewService, 'fetch_trade_dates', side_effect=RuntimeError('calendar unavailable')):
            for call in (lambda:get_trade_dates(start='2026-11-18',end='2026-11-19'),
                         lambda:get_market_history(start='2026-11-18',end='2026-11-19',session=self.session)):
                with self.assertRaises(HTTPException) as caught:
                    call()
                self.assertEqual(caught.exception.status_code, 503)

    def test_empty_sector_fetch_keeps_existing_data(self):
        day = date(2026, 11, 19)
        self.session.add(SectorDaily(sector_type='industry',sector_code='one',sector_name='one',trade_date=day,change_pct=1,volume=1))
        self.session.commit()
        service = OverviewService()
        with patch.object(service, '_fetch_sector_daily_from_tushare', return_value={}):
            self.assertEqual(service.sync_sector_ranking_for_date(day, 'industry', self.session), 0)
        self.assertEqual(len(self.session.exec(select(SectorDaily)).all()), 1)

    def test_financial_sync_strict_mode_cannot_treat_outage_as_no_new_report(self):
        service = FinancialService()
        pro = Mock()
        pro.income.side_effect = TushareError('upstream failed')
        with patch.object(service, '_get_tushare_pro', return_value=pro):
            with self.assertRaises(TushareError):
                service.ensure_fresh(['600519'], self.session, strict=True)

    def test_online_backup_is_readable_and_manifest_is_verified(self):
        source = self.root / 'original.db'
        with sqlite3.connect(source) as connection:
            connection.execute('CREATE TABLE sample(value TEXT)')
            connection.execute('INSERT INTO sample VALUES (?)', ('persisted',))
        directory = self.root / 'backups'
        manifest = backup_database('sqlite:///'+str(source), directory, self.store)
        with sqlite3.connect(directory / manifest['filename']) as copied:
            self.assertEqual(copied.execute('SELECT value FROM sample').fetchone()[0], 'persisted')
        self.assertEqual(self.store.read('backup')['check'], 'ok')
        with patch('app.services.system_service.settings.backup_dir', str(directory)):
            self.service.now = datetime.now(UTC)
            self.assertEqual(self.service._backup_info()['status'], 'ok')
            (directory / manifest['filename']).unlink()
            self.assertEqual(self.service._backup_info()['status'], 'warning')


if __name__ == '__main__':
    unittest.main()
