import configparser
import json
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

with patch.dict(os.environ, {'AUTH_USERNAME': 'test-user', 'AUTH_PASSWORD': 'test-password-only',
                              'AUTH_SECRET': 'test-signing-key-only-' * 3}):
    from fastapi import HTTPException
    from sqlmodel import SQLModel, Session, create_engine, select
    from app.config import Settings, _load_service_config, _load_tushare_token
    from app.models import ReviewAudit, ReviewCondition, ReviewObservation, ReviewVerification, StockDailyQuote
    from app.routers.review import (AuditIn, ReminderIn, audit_observation, condition_history, update_reminder)
    from app.services.review_assistant import ConditionInput, ReviewAssistant, save_condition
    from app.services.review_ai import AuditBusy, AuditUnavailable, generate_audit, request_audit
    from app.services.runtime_state import redact


RESULT = {'supporting_evidence': [], 'counter_evidence': [],
          'uncertainties': [{'text': '缺少足够证据证明因果关系。', 'evidence_ids': ['observation']}],
          'next_checks': [{'text': '对照原始条件记录反例。', 'evidence_ids': ['coverage']}]}


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)
        self.start, self.day, self.end = date(2026, 1, 5), date(2026, 1, 7), date(2026, 1, 8)
        self.days = [self.start + timedelta(days=i) for i in range(4)]
        self.assistant = ReviewAssistant(calendar=lambda start, end: ([d for d in self.days if start <= d <= end], datetime(2026, 1, 1)))
        self.obs = ReviewObservation(stock_code='600519', observation_date=self.start,
            deadline=self.end, reason='original reason', criterion='original criterion')
        self.session.add(self.obs)
        self.session.commit()
        self.session.refresh(self.obs)
        self.quote(self.start, 10)
        self.quote(self.start + timedelta(days=1), 10)
        self.quote(self.day, 9)
        self.quote(self.end, 11)

    def quote(self, day, value):
        self.session.add(StockDailyQuote(stock_code='600519', trade_date=day, close=value))
        self.session.commit()

    def rule(self, kind='hold_change', threshold='0', effective=None):
        return save_condition(self.session, self.obs, ConditionInput(effective_date=effective or self.start,
            kind=kind, operator='ge', threshold_pct=threshold, note='manual confirmation'))

    def context(self, day=None):
        return self.assistant.context(self.session, self.obs, day or self.end)

    def test_free_text_never_becomes_an_automatic_pass_or_fail(self):
        self.assertEqual(self.context()['evaluation']['status'], 'not_configured')

    def test_hold_condition_keeps_earliest_counterexample_even_after_price_recovers(self):
        self.rule()
        result = self.context()['evaluation']
        self.assertEqual(result['status'], 'not_met')
        self.assertEqual(result['first_violation'], str(self.day))
        self.assertEqual(result['valid_samples'], 3)

    def test_end_condition_uses_deadline_and_never_reads_later_price(self):
        self.rule('end_change')
        self.quote(self.end + timedelta(days=1), 1)
        current = self.context(self.end + timedelta(days=1))
        self.assertEqual(current['evaluation']['status'], 'met')
        self.assertNotIn('quote-2026-01-09', [f['id'] for f in current['context']['facts']])

    def test_observation_period_cannot_pass_early_and_history_has_no_future_quote(self):
        self.rule('end_change')
        current = self.context(self.day)
        self.assertEqual(current['evaluation']['status'], 'pending')
        self.assertNotIn('quote-2026-01-08', [f['id'] for f in current['context']['facts']])

    def test_missing_intermediate_quote_blocks_hold_but_not_end_only_check(self):
        row = self.session.exec(select(StockDailyQuote).where(StockDailyQuote.trade_date == self.day)).one()
        self.session.delete(row)
        self.session.commit()
        self.rule()
        self.assertEqual(self.context()['evaluation']['status'], 'unknown')
        self.rule('end_change')
        self.assertEqual(self.context()['evaluation']['status'], 'met')

    def test_missing_calendar_or_base_never_synthesizes_success(self):
        self.rule('end_change')
        no_calendar = ReviewAssistant(calendar=lambda start, end: None)
        self.assertEqual(no_calendar.context(self.session, self.obs, self.end)['evaluation']['status'], 'unknown')
        row = self.session.exec(select(StockDailyQuote).where(StockDailyQuote.trade_date == self.start)).one()
        self.session.delete(row)
        self.session.commit()
        self.assertEqual(self.context()['evaluation']['status'], 'unknown')

    def test_holiday_deadline_uses_last_real_trade_date(self):
        self.obs.deadline = date(2026, 1, 11)
        self.session.add(self.obs)
        self.session.commit()
        self.rule('end_change')
        self.assertEqual(self.context(date(2026, 1, 11))['evaluation']['end_date'], str(self.end))

    def test_decimal_threshold_boundary_is_not_lost_to_float_division(self):
        self.rule('end_change', threshold='10')
        self.assertEqual(self.context()['evaluation']['status'], 'met')

    def test_rule_revisions_keep_original_and_do_not_leak_into_earlier_date(self):
        first = self.rule('hold_change')
        self.rule('end_change', effective=self.end)
        self.assertEqual(self.context(self.day)['rule']['id'], first['id'])
        self.assertEqual(len(condition_history(self.obs.id, self.end, self.session)), 2)
        self.assertEqual(self.obs.reason, 'original reason')
        self.assertEqual(self.obs.criterion, 'original criterion')

    def test_manual_pass_with_counterexample_gets_a_conflict_without_overwrite(self):
        self.rule()
        self.session.add(ReviewVerification(observation_id=self.obs.id, review_date=self.end,
            verdict='符合预期', explanation='manual evidence'))
        self.session.commit()
        dashboard = self.assistant.dashboard(self.session, self.end)
        self.assertTrue(any(row['kind'] == 'conflict' for row in dashboard['reminders']))
        self.assertEqual(self.context()['verdict'], '符合预期')

    def test_read_is_durable_and_new_rule_event_can_reappear(self):
        self.rule()
        dashboard = self.assistant.dashboard(self.session, self.end)
        condition = next(r for r in dashboard['reminders'] if r['kind'] == 'condition')
        with patch('app.routers.review.ReviewAssistant', return_value=self.assistant):
            update_reminder(condition['key'], ReminderIn(date=self.end, action='read'), self.session)
        again = self.assistant.dashboard(self.session, self.end)
        self.assertTrue(next(r for r in again['reminders'] if r['key'] == condition['key'])['hidden'])
        self.rule()
        new = self.assistant.dashboard(self.session, self.end)
        self.assertFalse(next(r for r in new['reminders'] if r['kind'] == 'condition')['hidden'])

    def test_snooze_expires_and_does_not_modify_older_review(self):
        reminder = self.assistant.dashboard(self.session, self.end)['reminders'][0]
        with patch('app.routers.review.ReviewAssistant', return_value=self.assistant):
            update_reminder(reminder['key'], ReminderIn(date=self.end, action='snooze', snooze_until=self.end+timedelta(days=1)), self.session)
        self.assertTrue(next(r for r in self.assistant.dashboard(self.session, self.end)['reminders'] if r['key'] == reminder['key'])['hidden'])
        self.assertFalse(next(r for r in self.assistant.dashboard(self.session, self.end+timedelta(days=1))['reminders'] if r['key'] == reminder['key'])['hidden'])

    def test_identical_ai_context_reuses_saved_result_and_data_change_marks_stale(self):
        with patch('app.services.review_ai.request_audit', return_value=RESULT) as remote:
            first = generate_audit(self.session, self.obs, self.end, self.assistant)
            second = generate_audit(self.session, self.obs, self.end, self.assistant)
        self.assertTrue(second['cached'])
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(remote.call_count, 1)
        self.rule('end_change')
        self.assertTrue(self.assistant.dashboard(self.session, self.end)['entries'][0]['audit']['stale'])
        self.assertFalse(self.session.exec(select(ReviewVerification)).all())

    def test_provider_failure_saves_no_fake_audit(self):
        with patch('app.services.review_ai.request_audit', side_effect=AuditUnavailable('unavailable')):
            with self.assertRaises(AuditUnavailable):
                generate_audit(self.session, self.obs, self.end, self.assistant)
        self.assertFalse(self.session.exec(select(ReviewAudit)).all())

    def test_ai_duplicate_generation_has_cooldown(self):
        with patch('app.services.review_ai.request_audit', return_value=RESULT):
            generate_audit(self.session, self.obs, self.end, self.assistant)
            with self.assertRaises(AuditBusy):
                generate_audit(self.session, self.obs, self.end, self.assistant, force=True)

    def test_future_dates_cannot_trigger_ai_request(self):
        with patch('app.services.review_ai.request_audit') as remote:
            with self.assertRaises(HTTPException) as caught:
                audit_observation(self.obs.id, AuditIn(date=date.today()+timedelta(days=3)), self.session)
        self.assertEqual(caught.exception.status_code, 400)
        remote.assert_not_called()


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.context = {'as_of': '2026-01-08', 'facts': [{'id': 'observation'}, {'id': 'coverage'}]}
        for field, value in [('ai_base_url', 'https://api.example.test/v1'), ('ai_api_key', 'test-only-ai-key'), ('ai_model', 'test-model')]:
            patcher = patch('app.services.review_ai.settings.'+field, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def response(self, result=RESULT, status=200, finish='stop'):
        response = Mock(status_code=status)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_content.return_value = [json.dumps({'choices': [{'finish_reason': finish,
            'message': {'content': json.dumps(result)}}]}).encode()]
        return response

    def test_valid_result_and_real_client_identity(self):
        with patch('app.services.review_ai.requests.post', return_value=self.response()) as post:
            self.assertEqual(request_audit(self.context), RESULT)
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs['headers']['User-Agent'], 'Stocks-Review-Assistant/1.0')
        self.assertNotIn('tools', kwargs['json'])
        self.assertNotIn('temperature', kwargs['json'])

    def test_unknown_citations_and_truncated_output_are_rejected(self):
        bad = {**RESULT, 'counter_evidence': [{'text': 'Unsupported fact', 'evidence_ids': ['future-news']}]}
        for response in (self.response(bad), self.response(finish='length')):
            with patch('app.services.review_ai.requests.post', return_value=response):
                with self.assertRaises(AuditUnavailable):
                    request_audit(self.context)

    def test_auth_failure_never_returns_vendor_body_or_api_key(self):
        with patch('app.services.review_ai.requests.post', return_value=self.response(status=401)):
            with self.assertRaises(AuditUnavailable) as caught:
                request_audit(self.context)
        self.assertNotIn('test-only-ai-key', str(caught.exception))
        self.assertNotIn('test-only-ai-key', redact('api_key=test-only-ai-key'))

    def test_http_redirect_and_plaintext_remote_endpoint_are_not_followed(self):
        with patch('app.services.review_ai.requests.post', return_value=self.response(status=302)) as post:
            with self.assertRaises(AuditUnavailable):
                request_audit(self.context)
        self.assertFalse(post.call_args.kwargs['allow_redirects'])
        with patch('app.services.review_ai.settings.ai_base_url', 'http://remote.example/v1'):
            with self.assertRaises(AuditUnavailable):
                request_audit(self.context)

    def test_bare_kimi_code_key_does_not_break_tushare_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'base.conf'
            path.write_text('[tushare]\ntoken=test-tushare\n[kimi]\nsk-kimi-test-only\n', encoding='utf-8')
            with patch('app.config.SERVICE_CONFIG_PATH', path), patch.dict(os.environ, {'AI_API_KEY': '', 'AI_BASE_URL': '', 'AI_MODEL': ''}):
                self.assertEqual(_load_tushare_token(), 'test-tushare')
                self.assertEqual(_load_service_config('kimi')['api_key'], 'sk-kimi-test-only')
                config = Settings(_env_file=None, auth_username='test', auth_password='test', auth_secret='x'*32)
                self.assertEqual(config.ai_model, 'k3')
                self.assertEqual(config.ai_base_url, 'https://api.kimi.com/coding/v1')
                self.assertNotIn('sk-kimi-test-only', repr(config))


if __name__ == '__main__':
    unittest.main()
