import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import test_review_assistant as fixtures
from pydantic import ValidationError
from sqlalchemy import text
from sqlmodel import Session, create_engine, select
from fastapi import HTTPException

from app.models import ReviewAudit, ReviewAuditFeedback, ReviewCondition, ReviewVerification, Stock, StockAdjustmentFactor
from app.services.price_basis import StockFactorService, fetch_daily_factors, normalize_factors, price_change
from app.services.review_assistant import ConditionInput, save_condition
from app.services.review_feedback import FeedbackInput, attach_feedback, history, save_feedback, summary
from app.services.review_ai import generate_audit
from app.services.review_tracking import observation_detail
from app.services.runtime_state import RuntimeStore
from app.services.etf_dashboard import summarize
from app.services.overview_service import OverviewService
from app.routers.review import submit_audit_feedback


class PriceBasisTests(unittest.TestCase):
    setUp = fixtures.AssistantTests.setUp
    quote = fixtures.AssistantTests.quote
    context = fixtures.AssistantTests.context

    def factor(self, day, value):
        self.session.add(StockAdjustmentFactor(stock_code=self.obs.stock_code, trade_date=day, factor=str(value)))
        self.session.commit()

    def adjusted_rule(self, kind='end_change', basis='adjusted', threshold='0'):
        return save_condition(self.session, self.obs, ConditionInput(effective_date=self.start, kind=kind,
            operator='ge', threshold_pct=threshold, price_basis=basis, note='explicit basis'))

    def test_adjustment_neutralizes_split_and_preserves_raw_comparison(self):
        self.assertEqual(price_change(10, 5, 1, 2), Decimal('0'))
        self.assertEqual(price_change(10, 5, basis='raw'), Decimal('-50'))
        self.assertEqual(price_change(10, 6, 1, 2), Decimal('20'))

    def test_missing_nonpositive_or_nonfinite_factors_never_default_to_one(self):
        for value in (None, 0, -1, float('nan'), float('inf'), 'bad'):
            self.assertIsNone(price_change(10, 11, value, 1))
            self.assertIsNone(price_change(10, 11, 1, value))
        self.assertEqual(price_change(10, 11, None, None, 'raw'), Decimal('10'))

    def test_existing_rules_keep_raw_basis_and_new_adjusted_rule_is_explicit(self):
        old = save_condition(self.session, self.obs, ConditionInput(effective_date=self.start, kind='end_change', operator='ge', threshold_pct='0', note='old client'))
        self.assertEqual(old['price_basis'], 'raw')
        self.assertEqual(self.context()['evaluation']['status'], 'met')
        self.adjusted_rule()
        self.assertEqual(self.context()['evaluation']['status'], 'unknown')
        self.assertEqual(self.session.get(ReviewCondition, old['id']).price_basis, 'raw')

    def test_adjusted_end_rule_uses_only_base_and_end_factors(self):
        self.factor(self.start, 1)
        self.factor(self.end, 1)
        self.adjusted_rule()
        self.assertEqual(self.context()['evaluation']['status'], 'met')

    def test_adjusted_hold_rule_requires_factors_for_each_observed_day(self):
        self.factor(self.start, 1)
        self.factor(self.end, 1)
        self.adjusted_rule('hold_change', threshold='-20')
        result = self.context()['evaluation']
        self.assertEqual(result['status'], 'unknown')
        self.assertIn(str(self.day), result['missing_factor_dates'])

    def test_valid_counterexample_can_be_reported_despite_other_missing_factors(self):
        self.factor(self.start, 1)
        self.factor(self.day, 1)
        self.adjusted_rule('hold_change')
        result = self.context()['evaluation']
        self.assertEqual(result['status'], 'not_met')
        self.assertEqual(result['first_violation'], str(self.day))

    def test_future_factor_cannot_fill_a_missing_selected_day(self):
        self.factor(self.start, 1)
        self.factor(self.end+timedelta(days=1), 2)
        self.adjusted_rule()
        current = self.context()
        self.assertEqual(current['evaluation']['status'], 'unknown')
        self.assertNotIn('factor-'+str(self.end+timedelta(days=1)), [row['id'] for row in current['context']['facts']])

    def test_batch_and_single_adjusted_context_fingerprints_match(self):
        for day in self.days:
            self.factor(day, 1)
        self.adjusted_rule('hold_change')
        self.assertEqual(self.context()['context_hash'], self.assistant.contexts(self.session,[self.obs],self.end)[self.obs.id]['context_hash'])

    def test_adjusted_change_is_separate_from_actual_closes_and_raw_change(self):
        self.factor(self.start, 1)
        self.factor(self.end, 2)
        record = observation_detail(self.session, self.obs, self.end, self.assistant)['observation']
        self.assertEqual(record['base_close'], 10)
        self.assertEqual(record['close'], 11)
        self.assertEqual(record['price_change'], 10)
        self.assertEqual(record['adjusted_price_change'], 120)

    def frame(self, day=None, factor=1, code='600519.SH'):
        return pd.DataFrame([{'ts_code':code,'trade_date':(day or self.end).strftime('%Y%m%d'),'adj_factor':factor}])

    def test_factor_normalization_rejects_wrong_day_invalid_value_and_conflicts(self):
        for frame in (self.frame(self.start), self.frame(factor=0), self.frame(factor=float('nan')),
                      pd.concat([self.frame(),self.frame(factor=2)],ignore_index=True)):
            with self.assertRaises(ValueError):
                normalize_factors(frame,day=self.end)

    def test_factor_sync_updates_in_place_and_empty_response_keeps_old_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            client=Mock();store=RuntimeStore(temporary)
            service=StockFactorService(client,store)
            client.query.return_value=self.frame(factor=1)
            self.assertEqual(service.sync_day(self.session,self.end),1)
            client.query.return_value=self.frame(factor=2)
            service.sync_day(self.session,self.end,force=True)
            self.assertEqual(self.session.exec(select(StockAdjustmentFactor)).one().factor,'2')
            client.query.return_value=pd.DataFrame()
            self.assertEqual(service.sync_day(self.session,self.end,force=True),0)
            self.assertEqual(self.session.exec(select(StockAdjustmentFactor)).one().factor,'2')

    def test_daily_factor_pagination_has_to_finish_without_duplicate_pages(self):
        frame=pd.DataFrame([{'ts_code':f'{i:06}.SH','trade_date':self.end.strftime('%Y%m%d'),'adj_factor':1} for i in range(2000)])
        client=Mock();client.query.side_effect=[frame,self.frame()]
        self.assertEqual(len(fetch_daily_factors(client,'fund_adj',self.end)),2001)
        self.assertEqual(client.query.call_args.kwargs['offset'],2000)
        client.query.side_effect=[frame,frame]
        with self.assertRaises(RuntimeError):
            fetch_daily_factors(client,'fund_adj',self.end)

    def test_failed_later_factor_page_cannot_commit_the_first_page(self):
        self.factor(self.end, 3)
        frame=pd.DataFrame([{'ts_code':f'{i:06}.SH','trade_date':self.end.strftime('%Y%m%d'),'adj_factor':1} for i in range(2000)])
        client=Mock();client.query.side_effect=[frame,RuntimeError('offline')]
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(RuntimeError):
                StockFactorService(client,RuntimeStore(temporary)).sync_day(self.session,self.end,force=True)
        self.assertEqual(self.session.exec(select(StockAdjustmentFactor)).one().factor,'3')

    def test_etf_factor_cache_survives_restart_and_failed_refresh(self):
        from app.services.etf_service import EtfService
        from datetime import timezone
        with tempfile.TemporaryDirectory() as temporary:
            service=EtfService(cache_dir=temporary)
            client=Mock();client.query.return_value=self.frame(code='510000.SH')
            service._tushare_pro=client
            self.assertEqual(len(service._fetch_etf_factors_for_date(self.end)),1)
            key='factor-'+self.end.strftime('%Y%m%d')
            path=Path(temporary)/(key+'.json')
            payload=json.loads(path.read_text(encoding='utf-8'))
            payload['fetched_at']=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
            path.write_text(json.dumps(payload),encoding='utf-8')
            offline=EtfService(cache_dir=temporary);offline._tushare_pro=Mock()
            offline._tushare_pro.query.side_effect=RuntimeError('offline')
            self.assertEqual(len(offline._fetch_etf_factors_for_date(self.end)),1)
            self.assertTrue(offline.cache_fallbacks())

    def test_etf_ranking_and_state_use_adjusted_change_and_keep_raw_reference(self):
        result=summarize([{'code':'510000','name':'fixtureETF'}],[{'code':'510000','close':5,'amount':10000}],
            {2:{'510000':10},5:{'510000':10},10:{'510000':10},20:{'510000':10}},'2026-01-08','2026-01-08',
            {str(w):'2026-01-05' for w in (2,5,10,20)},0,
            factor_maps={'2026-01-05':{'510000':1},'2026-01-08':{'510000':2}},price_basis='adjusted')
        item=result['items'][0]
        self.assertEqual(item['gain_5'],0)
        self.assertEqual(item['raw_gain_5'],-50)
        self.assertEqual(result['directions'][0]['median_5'],0)

    def test_missing_etf_factor_is_null_and_excluded_from_direction_sample(self):
        result=summarize([{'code':'510000','name':'fixtureETF'}],[{'code':'510000','close':5,'amount':10000}],
            {5:{'510000':10}},'2026-01-08','2026-01-08',{'5':'2026-01-05'},0,factor_maps={},price_basis='adjusted')
        self.assertIsNone(result['items'][0]['gain_5'])
        self.assertEqual(result['directions'][0]['samples_5'],0)
        self.assertEqual(result['factor_coverage']['5']['valid'],0)

    def test_stock_ranking_does_not_fall_back_to_raw_change(self):
        stock=Stock(code='600519',name='fixture',exchange='SH',list_date=date(2020,1,1))
        self.session.add(stock);self.session.commit()
        quotes={('600519',row.trade_date):row for row in self.session.exec(select(fixtures.StockDailyQuote)).all()}
        service=OverviewService()
        with patch('app.services.stock_filters.apply_base_filters',return_value=['600519']):
            self.assertFalse(service._build_gainer_ranking(self.end,self.start,quotes,{'600519':stock},self.session,{}))
            ranking=service._build_gainer_ranking(self.end,self.start,quotes,{'600519':stock},self.session,{('600519',self.start):'1',('600519',self.end):'2'})
        self.assertEqual(ranking[0]['gain'],120)

    def test_migration_is_repeatable_and_keeps_old_rules_raw(self):
        from scripts.migrate_add_price_basis_feedback import migrate
        old=create_engine('sqlite://')
        self.addCleanup(old.dispose)
        with old.begin() as connection:
            connection.execute(text('CREATE TABLE review_condition (id INTEGER PRIMARY KEY, threshold_pct VARCHAR, note VARCHAR)'))
            connection.execute(text("INSERT INTO review_condition (id,threshold_pct,note) VALUES (1,'3','original')"))
        migrate(old);migrate(old)
        with old.connect() as connection:
            self.assertEqual(connection.execute(text('SELECT threshold_pct,note,price_basis FROM review_condition')).one(),('3','original','raw'))


class FeedbackTests(unittest.TestCase):
    setUp = fixtures.AssistantTests.setUp
    quote = fixtures.AssistantTests.quote

    def audit(self):
        with patch('app.services.review_ai.request_audit',return_value=fixtures.RESULT):
            result=generate_audit(self.session,self.obs,self.end,self.assistant)
        return self.session.get(ReviewAudit,result['id'])

    def body(self,rating='helpful',comment='',day=None,index=0):
        return FeedbackInput(date=day or self.end,section='uncertainties',item_index=index,rating=rating,comment=comment)

    def test_feedback_is_separate_from_original_opinion_and_user_verdict(self):
        audit=self.audit();original=audit.result_json;snapshot=audit.context_json
        feedback=save_feedback(self.session,audit,self.body())
        self.assertEqual(feedback['rating'],'helpful')
        self.assertEqual(self.session.get(ReviewAudit,audit.id).result_json,original)
        self.assertEqual(self.session.get(ReviewAudit,audit.id).context_json,snapshot)
        self.assertFalse(self.session.exec(select(ReviewVerification)).all())

    def test_negative_feedback_requires_specific_reason(self):
        for rating in ('misunderstood','insufficient'):
            with self.assertRaises(ValidationError):
                self.body(rating,comment='  ')

    def test_identical_retry_is_idempotent_and_changes_append_a_revision(self):
        audit=self.audit()
        first=save_feedback(self.session,audit,self.body())
        duplicate=save_feedback(self.session,audit,self.body())
        second=save_feedback(self.session,audit,self.body('misunderstood','The cited fact does not support the inference.'))
        self.assertEqual(first['id'],duplicate['id'])
        self.assertEqual(second['revisions'],2)
        self.assertEqual(len(self.session.exec(select(ReviewAuditFeedback)).all()),2)
        saved=attach_feedback(self.session,{'id':audit.id},self.end)['feedback']
        self.assertEqual(saved[0]['rating'],'misunderstood')

    def test_summary_counts_latest_opinion_labels_instead_of_revision_count(self):
        audit=self.audit()
        save_feedback(self.session,audit,self.body())
        save_feedback(self.session,audit,self.body('insufficient','Missing independent evidence.'))
        result=summary(self.session,self.end)
        self.assertEqual(result['rated_count'],1)
        self.assertEqual(result['helpful'],0)
        self.assertEqual(result['insufficient'],1)

    def test_future_feedback_cannot_leak_into_historical_view_or_summary(self):
        audit=self.audit()
        save_feedback(self.session,audit,self.body())
        save_feedback(self.session,audit,self.body('misunderstood','A later correction.',self.end+timedelta(days=1)))
        self.assertEqual(attach_feedback(self.session,{'id':audit.id},self.end)['feedback'][0]['rating'],'helpful')
        self.assertEqual(summary(self.session,self.end)['helpful'],1)
        self.assertEqual(summary(self.session,self.end+timedelta(days=1))['misunderstood'],1)

    def test_feedback_history_retains_reason_and_actual_recording_time(self):
        audit=self.audit()
        save_feedback(self.session,audit,self.body())
        save_feedback(self.session,audit,self.body('misunderstood','Original correction reason.'))
        result=history(self.session,audit,self.end,'uncertainties',0)
        self.assertEqual(result['total'],2)
        self.assertEqual(result['items'][0]['comment'],'Original correction reason.')
        self.assertTrue(result['items'][0]['created_at'].endswith('+00:00'))

    def test_missing_item_and_wrong_observation_cannot_receive_feedback(self):
        audit=self.audit()
        with self.assertRaises(ValueError):
            save_feedback(self.session,audit,self.body(index=3))
        with self.assertRaises(HTTPException) as caught:
            submit_audit_feedback(9999,audit.id,self.body(),self.session)
        self.assertEqual(caught.exception.status_code,404)

    def test_feedback_cannot_be_backdated_before_audit_or_assigned_to_future(self):
        audit=self.audit()
        for day in (self.start,date.today()+timedelta(days=3)):
            with self.assertRaises(ValueError):
                save_feedback(self.session,audit,self.body(day=day))

    def test_reading_feedback_does_not_trigger_model_and_does_not_stale_audit(self):
        audit=self.audit()
        save_feedback(self.session,audit,self.body())
        with patch('app.services.review_ai.request_audit') as remote:
            detail=observation_detail(self.session,self.obs,self.end,self.assistant)
        self.assertEqual(detail['entry']['audit']['feedback'][0]['rating'],'helpful')
        self.assertFalse(detail['entry']['audit']['stale'])
        remote.assert_not_called()

    def test_cached_audit_reuses_model_result_but_includes_new_feedback(self):
        audit=self.audit()
        save_feedback(self.session,audit,self.body('insufficient','Needs additional evidence.'))
        with patch('app.services.review_ai.request_audit') as remote:
            result=generate_audit(self.session,self.obs,self.end,self.assistant)
        self.assertTrue(result['cached'])
        self.assertEqual(result['feedback'][0]['rating'],'insufficient')
        remote.assert_not_called()


if __name__=='__main__':
    unittest.main()
