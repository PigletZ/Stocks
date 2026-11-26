import json
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch,Mock

from pydantic import ValidationError
from sqlmodel import select
import test_review_assistant as fixtures
import test_system as system_fixtures
from app.models import ReviewAudit,ReviewAuditFeedback,ReviewCorrection,ReviewVerification
from app.services.review_ai import generate_audit
from app.services.review_feedback import FeedbackInput,save_feedback,attach_feedback
from app.services.review_corrections import history
from app.services.collection_timing import collection_target,record_missing
from app.services.job_monitor import JobRun,_active_run,waiting_expired
from app.services.system_jobs import job_statuses
from app.services.system_maintenance import maintenance_status
from app.services.daily_sync import DailySyncService
from app.services.overview_service import OverviewService
from app.services.tushare_client import TushareError


class CorrectionTests(unittest.TestCase):
    setUp=fixtures.AssistantTests.setUp
    quote=fixtures.AssistantTests.quote

    def audit(self):
        with patch('app.services.review_ai.request_audit',return_value=fixtures.RESULT):
            result=generate_audit(self.session,self.obs,self.end,self.assistant)
        return self.session.get(ReviewAudit,result['id'])

    def body(self,reuse=None,comment='The price condition does not prove the stated causal explanation.',day=None):
        return FeedbackInput(date=day or self.end,section='uncertainties',item_index=0,rating='insufficient',comment=comment,reuse_for_audit=reuse)

    def context(self,day=None):return self.assistant.context(self.session,self.obs,day or self.end)

    def corrections(self,day=None):return [fact for fact in self.context(day)['context']['facts'] if fact['id'].startswith('correction-')]

    def test_ordinary_feedback_does_not_automatically_enter_context(self):
        audit=self.audit();before=self.context()['context_hash']
        saved=save_feedback(self.session,audit,self.body())
        self.assertFalse(saved['reuse_for_audit']);self.assertFalse(saved['context_changed'])
        self.assertEqual(self.context()['context_hash'],before)

    def test_explicit_confirmation_keeps_source_time_and_separate_market_facts(self):
        audit=self.audit();original=(audit.context_json,audit.result_json)
        before=self.context()['context_hash']
        saved=save_feedback(self.session,audit,self.body(True))
        facts=self.corrections()
        self.assertTrue(saved['reuse_for_audit'] and saved['context_changed'])
        self.assertEqual(len(facts),1)
        self.assertEqual(facts[0]['value']['source_feedback_id'],saved['id'])
        self.assertEqual(facts[0]['value']['source_audit_id'],audit.id)
        self.assertIn('confirmed_at',facts[0]['value'])
        self.assertIn('非行情事实',facts[0]['value']['source_type'])
        self.assertNotEqual(self.context()['context_hash'],before)
        self.assertEqual((audit.context_json,audit.result_json),original)
        self.assertFalse(self.session.exec(select(ReviewVerification)).all())

    def test_idempotency_and_withdrawal_do_not_duplicate_feedback_or_resurrect_old_note(self):
        audit=self.audit();baseline=self.context()['context_hash']
        first=save_feedback(self.session,audit,self.body(True))
        repeat=save_feedback(self.session,audit,self.body(True))
        self.assertEqual(first['id'],repeat['id']);self.assertFalse(repeat['context_changed'])
        withdrawn=save_feedback(self.session,audit,self.body(False))
        self.assertFalse(withdrawn['reuse_for_audit']);self.assertTrue(withdrawn['context_changed'])
        self.assertFalse(self.corrections())
        self.assertEqual(self.context()['context_hash'],baseline)
        self.assertEqual(len(self.session.exec(select(ReviewAuditFeedback)).all()),1)
        records=history(self.session,audit.id,self.end,'uncertainties',0)
        self.assertEqual(records['total'],2);self.assertFalse(records['items'][0]['active'])

    def test_future_confirmation_and_withdrawal_are_cut_off_by_selected_date(self):
        audit=self.audit()
        save_feedback(self.session,audit,self.body(True,day=self.end+timedelta(days=1)))
        self.assertFalse(self.corrections())
        self.assertEqual(len(self.corrections(self.end+timedelta(days=1))),1)
        save_feedback(self.session,audit,self.body(False,day=self.end+timedelta(days=2)))
        self.assertEqual(len(self.corrections(self.end+timedelta(days=1))),1)
        self.assertFalse(self.corrections(self.end+timedelta(days=2)))

    def test_batch_and_single_contexts_match_with_correction_sources(self):
        audit=self.audit();save_feedback(self.session,audit,self.body(True))
        batch=self.assistant.contexts(self.session,[self.obs],self.end)[self.obs.id]
        self.assertEqual(batch['context_hash'],self.context()['context_hash'])

    def test_unspecified_reuse_from_older_client_preserves_confirmed_note(self):
        audit=self.audit();save_feedback(self.session,audit,self.body(True))
        save_feedback(self.session,audit,self.body(None,comment='A newer unconfirmed comment.'))
        current=attach_feedback(self.session,{'id':audit.id},self.end)['feedback'][0]
        self.assertTrue(current['reuse_for_audit'])
        self.assertNotEqual(current['comment'],current['reused_note'])
        self.assertEqual(self.corrections()[0]['value']['manual_note'],current['reused_note'])

    def test_saving_confirmed_note_never_calls_the_model(self):
        audit=self.audit()
        with patch('app.services.review_ai.request_audit') as remote:
            save_feedback(self.session,audit,self.body(True))
            self.context()
        remote.assert_not_called()

    def test_correction_cannot_be_attached_to_another_observation(self):
        audit=self.audit();save_feedback(self.session,audit,self.body(True))
        from app.models import ReviewObservation
        other=ReviewObservation(stock_code='000001',observation_date=self.start,reason='other',criterion='other',deadline=self.end)
        self.session.add(other);self.session.commit()
        context=self.assistant.context(self.session,other,self.end)
        self.assertFalse(any(fact['id'].startswith('correction-') for fact in context['context']['facts']))

    def test_positive_rating_or_blank_comment_cannot_be_confirmed_as_correction(self):
        for rating,comment in [('helpful','some comment'),('insufficient','')]:
            with self.assertRaises(ValidationError):FeedbackInput(date=self.end,section='uncertainties',item_index=0,rating=rating,comment=comment,reuse_for_audit=True)

    def test_new_manual_audit_receives_the_confirmed_note_and_caches_it(self):
        audit=self.audit();save_feedback(self.session,audit,self.body(True))
        audit.created_at-=timedelta(minutes=3);self.session.add(audit);self.session.commit()
        with patch('app.services.review_ai.request_audit',return_value=fixtures.RESULT) as remote:
            fresh=generate_audit(self.session,self.obs,self.end,self.assistant)
            cached=generate_audit(self.session,self.obs,self.end,self.assistant)
        self.assertEqual(remote.call_count,1)
        self.assertTrue(any(row['id'].startswith('correction-') for row in fresh['facts']))
        self.assertTrue(cached['cached'])


class TimingTests(unittest.TestCase):
    setUp=system_fixtures.SystemTests.setUp

    def test_morning_target_excludes_unclosed_day_but_calendar_selects_real_days(self):
        early=datetime(2026,11,19,1,tzinfo=timezone.utc)
        self.assertEqual(collection_target(early),early.date()-timedelta(days=1))
        self.assertEqual(collection_target(early+timedelta(hours=8)),early.date())

    def run_missing(self,now,day):
        run=JobRun('daily',self.store)
        token=_active_run.set(run)
        try:
            run.record(succeeded=1)
            record_missing(day,'fixture waiting sample',now=now)
            run.finish()
        finally:_active_run.reset(token)
        return self.store.read('job-daily')

    def test_normal_publication_waiting_is_not_a_failure_or_overdue(self):
        now=datetime(2026,11,19,10,tzinfo=timezone.utc)
        result=self.run_missing(now,now.date())
        self.assertEqual(result['status'],'waiting')
        self.assertEqual(result['waiting'],1);self.assertEqual(result['failed'],0);self.assertEqual(result['deferred'],0)
        self.assertFalse(waiting_expired(result,now))

    def test_waiting_turns_into_attention_after_expected_time(self):
        now=datetime(2026,11,19,10,tzinfo=timezone.utc)
        self.run_missing(now,now.date())
        before=next(row for row in job_statuses(now,self.root/'logs',self.store,self.discovered) if row['key']=='daily')
        after=next(row for row in job_statuses(now+timedelta(hours=4),self.root/'logs',self.store,self.discovered) if row['key']=='daily')
        self.assertEqual(before['status'],'waiting');self.assertEqual(after['status'],'unknown')
        self.assertEqual(maintenance_status('daily',self.store,now+timedelta(hours=4))['status'],'unknown')

    def test_old_day_and_late_today_remain_deferred(self):
        now=datetime(2026,11,19,14,tzinfo=timezone.utc)
        for day in (now.date(),now.date()-timedelta(days=1)):
            result=self.run_missing(now,day)
            self.assertEqual(result['deferred'],1);self.assertEqual(result['waiting'],0)
            self.assertEqual(result['status'],'partial')

    def test_real_source_failure_is_not_hidden_in_waiting_window(self):
        run=JobRun('daily',self.store);token=_active_run.set(run)
        try:
            DailySyncService._run(Mock(side_effect=TushareError('HTTP 502')),'fixture',self.session,self.now.date())
            run.finish()
        finally:_active_run.reset(token)
        self.assertEqual(run.data['failed'],1);self.assertEqual(run.data['waiting'],0)

    def test_strict_market_and_index_sync_propagate_http_failure(self):
        source=OverviewService();client=Mock()
        client.daily.side_effect=TushareError('HTTP 502');client.index_daily.side_effect=TushareError('HTTP 502')
        with patch.object(source,'_get_tushare_pro',return_value=client):
            with self.assertRaises(TushareError):source.fetch_market_stats_for_date(self.now.date(),strict=True)
            with self.assertRaises(TushareError):source.fetch_index_for_date('000001','fixture',self.now.date(),strict=True)

    def test_expired_manual_diagnostics_are_informational_not_a_new_source_failure(self):
        self.store.write('diagnostics',{'checked_at':(self.now-timedelta(hours=1)).isoformat(),
            'checks':[{'key':'calendar','label':'fixture','status':'ok','message':'sample passed'}]})
        with patch('app.services.runtime_state.settings.tushare_token','test-token'):
            result=self.service.get_status(self.session)
        self.assertFalse(any(alert['key']=='source' for alert in result['alerts']))
        self.assertEqual(result['diagnostics']['status'],'unknown')

    def test_fresh_diagnostic_failure_still_requires_attention(self):
        self.store.write('diagnostics',{'checked_at':self.now.isoformat(),
            'checks':[{'key':'calendar','label':'fixture','status':'error','message':'HTTP 502'}]})
        with patch('app.services.runtime_state.settings.tushare_token','test-token'):
            result=self.service.get_status(self.session)
        self.assertTrue(any(alert['key']=='source' and alert['severity']=='error' for alert in result['alerts']))


if __name__=='__main__':unittest.main()
