import os
import tempfile
import unittest
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from unittest.mock import Mock, patch

import pandas as pd

with patch.dict(os.environ, {'AUTH_USERNAME':'test-user','AUTH_PASSWORD':'test-password-only','AUTH_SECRET':'test-signing-key-only-'*3}):
    from fastapi import HTTPException
    from sqlmodel import SQLModel, Session, create_engine, select
    from app.models import Bar, Stock, FinIncome, FinBalance, FinCashflow, MarketDailyStat, IndexDaily, SectorDaily, LimitUpDaily
    from app.routers.bars import _ensure_stock_and_sync, get_bars
    from app.routers.review import sync_review_data
    from app.services.financial_service import FinancialService
    from app.services.tushare_stock_service import TushareStockService
    from app.services.tushare_client import TushareError
    from app.services.etf_service import EtfService
    from app.services.overview_service import OverviewService
    from app.services.review_service import ReviewService
    from app.services.daily_sync import DailySyncService
    from app.services.dashboard_service import DashboardService
    from app.services.runtime_state import RuntimeStore
    from app.services.job_monitor import JobRun
    from app.services.journal_service import JournalService
    from app.validation import parse_iso_date
    from scripts.install_daily_catchup import updated_crontab, BEGIN, END


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://')
        SQLModel.metadata.create_all(self.engine)
        self.session=Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)
        self.session.add(Stock(code='600519',name='fixture',exchange='SH'))
        self.session.commit()
        self.old,self.new=date(2026,6,30),date(2026,9,30)

    def seed_financial(self, period):
        for model in (FinIncome,FinBalance,FinCashflow):
            self.session.add(model(stock_code='600519',end_date=period,f_ann_date=date(2026,7,30)))
        self.session.commit()

    def frame(self, period=None):
        return pd.DataFrame([{'ts_code':'600519.SH','end_date':(period or self.new).strftime('%Y%m%d'),
                              'f_ann_date':'20261030','report_type':'1','revenue':100,'total_assets':200,'n_cashflow_act':30}])

    def bar(self, price, hour=0):
        return Bar(stock_code='600519',timestamp=datetime(2026,11,18,hour),interval='1d',open=price,high=price,low=price,close=price,volume=1)

    def test_repeated_kline_sync_updates_instead_of_unique_key_failure(self):
        self.session.add(self.bar(1));self.session.commit()
        old_id=self.session.exec(select(Bar)).one().id
        with patch.object(TushareStockService,'ensure_stock_exists'),patch.object(TushareStockService,'fetch_daily_bars',return_value=[self.bar(2)]):
            _ensure_stock_and_sync('600519',None,None,self.session)
            _ensure_stock_and_sync('600519',None,None,self.session)
        rows=self.session.exec(select(Bar)).all()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0].id,old_id)
        self.assertEqual(rows[0].close,2)

    def test_empty_or_failed_kline_fetch_cannot_remove_existing_cache(self):
        self.session.add(self.bar(1));self.session.commit()
        with patch.object(TushareStockService,'ensure_stock_exists'),patch.object(TushareStockService,'fetch_daily_bars',return_value=[]):
            self.assertEqual(_ensure_stock_and_sync('600519',None,None,self.session),[])
        with patch.object(TushareStockService,'ensure_stock_exists'),patch.object(TushareStockService,'fetch_daily_bars',side_effect=TushareError('HTTP 502')):
            with self.assertRaises(HTTPException) as error:
                _ensure_stock_and_sync('600519',None,None,self.session)
            self.assertEqual(error.exception.status_code,503)
        self.assertEqual(self.session.exec(select(Bar)).one().close,1)

    def test_kline_end_date_includes_the_entire_day_and_rejects_reversed_range(self):
        self.session.add(self.bar(1,12));self.session.commit()
        rows=get_bars('600519','1d',date(2026,11,18),date(2026,11,18),False,self.session)
        self.assertEqual(len(rows),1)
        with self.assertRaises(HTTPException):
            get_bars('600519','1d',date(2026,11,19),date(2026,11,18),False,self.session)

    def test_financial_fetch_failure_does_not_commit_only_income(self):
        self.seed_financial(self.old)
        service=FinancialService()
        with patch.object(service,'_fetch_statement',side_effect=[self.frame(),TushareError('HTTP 502')]):
            with self.assertRaises(TushareError):
                service.refresh_stock('600519',self.session,strict=True)
        for model in (FinIncome,FinBalance,FinCashflow):
            self.assertEqual(self.session.exec(select(model.end_date)).all(),[self.old])

    def test_financial_write_failure_rolls_back_all_three_statements(self):
        self.seed_financial(self.old)
        service=FinancialService()
        original=service._upsert_rows
        def write(kind,code,rows,session,commit=True):
            if kind=='balance':raise RuntimeError('fixture write failure')
            return original(kind,code,rows,session,commit=commit)
        with patch.object(service,'_fetch_statement',return_value=self.frame()),patch.object(service,'_upsert_rows',side_effect=write):
            with self.assertRaises(RuntimeError):
                service.refresh_stock('600519',self.session,strict=True)
        self.assertEqual(self.session.exec(select(FinIncome.end_date)).all(),[self.old])

    def test_missing_companion_statement_is_retried_even_when_income_is_current(self):
        self.session.add(FinIncome(stock_code='600519',end_date=self.new,f_ann_date=date(2026,10,30)));self.session.commit()
        service=FinancialService();pro=Mock();pro.income.return_value=self.frame()
        with patch.object(service,'_get_tushare_pro',return_value=pro),patch.object(service,'refresh_stock',return_value={'income':1,'balance':1,'cashflow':1}) as refresh,patch('app.services.financial_service.time.sleep'):
            result=service.ensure_fresh(['600519'],self.session,strict=True)
        refresh.assert_called_once()
        self.assertIn('600519',result)

    def test_new_period_must_be_available_in_all_three_reports(self):
        self.seed_financial(self.old)
        service=FinancialService()
        with patch.object(service,'_fetch_statement',side_effect=[self.frame(),self.frame(),self.frame(self.old)]):
            with self.assertRaises(RuntimeError):service.refresh_stock('600519',self.session,strict=True)
        self.assertEqual(self.session.exec(select(FinIncome.end_date)).all(),[self.old])

    def test_failed_refresh_is_not_reported_as_successful_and_cache_warning_is_returned(self):
        self.seed_financial(self.old)
        service=FinancialService();pro=Mock();pro.income.side_effect=TushareError('HTTP 502')
        with patch.object(service,'_get_tushare_pro',return_value=pro),self.assertLogs('app.services.financial_service'):
            result=service.get_compare(['600519'],self.session)
        self.assertTrue(result['warnings'])
        self.assertEqual(result['stocks'][0]['periods'],[self.old.isoformat()])

    def test_financial_merged_report_and_known_announcement_take_priority(self):
        frame=pd.DataFrame([{'end_date':'20260930','ann_date':'20261020','report_type':1.0,'revenue':100},
                            {'end_date':'20260930','ann_date':'20261030','report_type':2.0,'revenue':200}])
        row=FinancialService()._dedupe(frame)[0]
        self.assertEqual(float(row['fields']['revenue']),100)
        self.assertEqual(row['f_ann_date'],date(2026,10,20))
        frame=pd.DataFrame([{'end_date':'20260930','f_ann_date':'20261030','report_type':'1','revenue':100},
                            {'end_date':'20260930','f_ann_date':None,'report_type':'1','revenue':200}])
        self.assertEqual(float(FinancialService()._dedupe(frame)[0]['fields']['revenue']),100)

    def test_legacy_etf_list_without_daily_quotes_returns_empty_instead_of_key_error(self):
        service=EtfService()
        with patch.object(service,'_fetch_etf_daily_for_date',return_value=pd.DataFrame()),patch.object(service,'_get_previous_trade_date',return_value=None),patch.object(service,'_get_etf_list_with_cache',return_value=pd.DataFrame([{'code':'510300','name':'fixture ETF'}])):
            result=service.fetch_etf_list()
        self.assertEqual(result,{'total':0,'items':[],'effective_date':None})

    def test_invalid_calendar_dates_are_client_errors_in_all_legacy_parsers(self):
        from app.routers import overview,review,stocks,etf,journal
        for parse in (overview._parse_date,review._parse_date,stocks._parse_date,etf._parse_date,journal._parse_date,parse_iso_date):
            for value in ('2026-02-30','bad','2026-13-01'):
                with self.subTest(parse=parse.__module__,value=value),self.assertRaises(HTTPException) as error:parse(value)
                self.assertEqual(error.exception.status_code,400)

    def test_review_sync_upstream_failure_cannot_return_success_with_zero_rows(self):
        with patch.object(ReviewService,'_get_tushare_pro',side_effect=TushareError('HTTP 502')):
            with self.assertRaises(HTTPException) as error:sync_review_data('2026-11-18',self.session)
        self.assertEqual(error.exception.status_code,503)

    def test_incomplete_limit_response_cannot_replace_existing_rows(self):
        day=date(2026,11,18)
        self.session.add(MarketDailyStat(stat_date=day,up=1,total=1,limit_up=2))
        self.session.add(LimitUpDaily(stock_code='600519',trade_date=day,name='original',limit_type='U'))
        self.session.commit()
        service=ReviewService();pro=Mock()
        pro.limit_list_d.return_value=pd.DataFrame([{'ts_code':'600520.SH','trade_date':'20261118','limit':'U'}])
        with patch.object(service,'_get_tushare_pro',return_value=pro):
            with self.assertRaises(RuntimeError):service.sync_limit_daily(day,self.session,strict=True)
        self.assertEqual(self.session.exec(select(LimitUpDaily.stock_code)).all(),['600519'])

    def test_partial_sector_response_cannot_replace_complete_cache(self):
        day=date(2026,11,18)
        for i in range(10):self.session.add(SectorDaily(sector_type='industry',sector_code=str(i),sector_name=str(i),trade_date=day,change_pct=1,volume=1))
        self.session.commit()
        service=OverviewService()
        with patch.object(service,'_fetch_sector_daily_from_tushare',return_value={'industry':[{}]}):
            self.assertEqual(service.sync_sector_ranking_for_date(day,'industry',self.session),0)
        self.assertEqual(len(self.session.exec(select(SectorDaily)).all()),10)

    def test_recent_sync_repairs_missing_previous_indices_and_partial_limit_details(self):
        previous,target=date(2026,11,17),date(2026,11,18)
        self.session.add(MarketDailyStat(stat_date=previous,up=1,total=1,limit_up=2,total_turnover=100))
        self.session.add(LimitUpDaily(stock_code='600519',trade_date=previous,name='partial',limit_type='U'))
        self.session.commit()
        overview=Mock();overview.INDEX_CODES=OverviewService.INDEX_CODES;overview.fetch_trade_dates.return_value=[previous,target]
        overview.sync_sector_ranking_for_date.return_value=1
        review=Mock();review.sync_limit_daily.return_value=2;review.sync_dragon_tiger_daily.return_value=1
        with patch.object(DashboardService,'sync_daily',return_value={'indices_count':5}) as sync:
            DailySyncService(overview,review).sync_recent(target,self.session)
        self.assertEqual([call.args[0] for call in sync.call_args_list],[previous,target])
        self.assertIn(previous,[call.args[0] for call in review.sync_limit_daily.call_args_list])

    def test_unpublished_data_are_deferred_instead_of_failed_or_successful(self):
        with tempfile.TemporaryDirectory() as folder:
            run=JobRun('daily',RuntimeStore(folder));run.record(deferred=2);run.finish()
            self.assertEqual(run.data['failed'],0)
            self.assertEqual(run.data['status'],'unknown')
            run=JobRun('daily',RuntimeStore(folder));run.record(skipped=2,confirmed_skip=True);run.finish()
            self.assertEqual(run.data['status'],'skipped')
            self.assertNotEqual(run.data['message'],'正在执行')
            run=JobRun('daily',RuntimeStore(folder));run.record(deferred=2,message='sector pending');run.record(succeeded=1,message='dragon done');run.finish()
            self.assertEqual(run.data['status'],'partial')
            self.assertEqual(run.data['deferred_items'],['sector pending'])
            self.assertIn('2',run.data['message'])

    def test_catchup_cron_is_idempotent_and_preserves_unrelated_jobs(self):
        original='SHELL=/bin/bash\n0 16 * * 1-5 python other_task.py\n'
        updated=updated_crontab(original,'/project/backend','/project/backend/venv/bin/python')
        self.assertTrue(updated.startswith(original.rstrip()))
        self.assertIn('30 18,20,21,22,23 * * 1-5',updated)
        self.assertEqual(updated_crontab(updated,'/project/backend','/project/backend/venv/bin/python'),updated)
        self.assertEqual(updated.count(BEGIN),1)
        with self.assertRaises(RuntimeError):updated_crontab(original+BEGIN+'\n','/project/backend','python')

    def test_two_concurrent_sells_cannot_both_pass_the_same_position_check(self):
        with tempfile.TemporaryDirectory() as directory:
            engine=create_engine('sqlite:///'+os.path.join(directory,'ledger.db'),connect_args={'check_same_thread':False})
            try:
                SQLModel.metadata.create_all(engine)
                with Session(engine) as session:
                    JournalService().create_trade('600519','buy',10,100,0,datetime(2026,11,17),None,session)
                barrier=threading.Barrier(2)
                original=JournalService._validate_history
                def delayed(service,*args,**kwargs):
                    original(service,*args,**kwargs)
                    time.sleep(.1)  # 强制覆盖两个请求都完成读取后才写入的竞态窗口。
                def sell():
                    barrier.wait(timeout=5)
                    with Session(engine) as session:
                        try:
                            JournalService().create_trade('600519','sell',11,100,0,datetime(2026,11,18),None,session)
                            return 'saved'
                        except ValueError:return 'rejected'
                with patch.object(JournalService,'_validate_history',delayed),ThreadPoolExecutor(max_workers=2) as pool:
                    results=list(pool.map(lambda _:sell(),range(2)))
                self.assertEqual(sorted(results),['rejected','saved'])
            finally:engine.dispose()

    def test_trade_note_can_be_explicitly_cleared(self):
        service=JournalService()
        trade=service.create_trade('600519','buy',10,100,0,datetime(2026,11,17),'old note',self.session)
        result=service.update_trade(trade['id'],self.session,note=None)
        self.assertIsNone(result['note'])


if __name__=='__main__':unittest.main()
