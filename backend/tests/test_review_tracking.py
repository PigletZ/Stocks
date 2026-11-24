import unittest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import test_review_assistant as fixtures
from sqlalchemy import event
from sqlmodel import select
from fastapi import HTTPException

from app.models import ReviewAudit, ReviewCondition, ReviewObservation, ReviewVerification, Stock, StockDailyQuote
from app.routers.review import ObservationIn, create_observation, get_saved_audit
from app.services.review_ai import generate_audit
from app.services.review_tracking import audit_history, list_observations, observation_detail, trading_deadlines


class TrackingTests(unittest.TestCase):
    setUp = fixtures.AssistantTests.setUp
    quote = fixtures.AssistantTests.quote
    rule = fixtures.AssistantTests.rule
    context = fixtures.AssistantTests.context

    def seed_records(self, count=505, completed=False):
        records = [ReviewObservation(stock_code=str(100000+i), observation_date=self.start+timedelta(days=1),
            deadline=self.end, reason='later record', criterion='manual criterion') for i in range(count)]
        self.session.add_all(records)
        self.session.flush()
        if completed:
            self.session.add_all([ReviewVerification(observation_id=row.id, review_date=self.end,
                verdict='不符合预期', explanation='completed') for row in records])
        self.session.commit()
        return records

    def report(self, day=None):
        with patch('app.services.review_ai.request_audit', return_value=fixtures.RESULT):
            return generate_audit(self.session, self.obs, day or self.end, self.assistant)

    def test_older_pending_record_survives_more_than_500_newer_records(self):
        self.seed_records()
        result = self.assistant.dashboard(self.session, self.end, include_entries=False)
        self.assertEqual(result['pending_count'], 506)
        self.assertTrue(any(item['observation_id'] == self.obs.id for item in result['reminders']))

    def test_completed_history_does_not_push_old_pending_record_out(self):
        self.seed_records(completed=True)
        result = list_observations(self.session, self.end, 'pending', assistant=self.assistant)
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['items'][0]['id'], self.obs.id)
        reminders = self.assistant.dashboard(self.session, self.end, include_entries=False)
        self.assertEqual(reminders['scope_count'], 1)

    def test_reminder_pagination_counts_all_pending_records(self):
        self.seed_records()
        result = self.assistant.dashboard(self.session, self.end, include_entries=False, page=1, page_size=5)
        self.assertEqual(len(result['reminders']), 5)
        self.assertEqual(result['pending_count'], 506)
        self.assertGreater(result['active_count'], 500)
        self.assertGreater(result['pages'], 1)

    def test_batched_reminder_queries_do_not_grow_one_query_per_observation(self):
        self.seed_records()
        statements = []
        def count_statement(*args):
            statements.append(args[2])
        event.listen(self.engine, 'before_cursor_execute', count_statement)
        try:
            result = self.assistant.dashboard(self.session, self.end, include_entries=False, page=1)
        finally:
            event.remove(self.engine, 'before_cursor_execute', count_statement)
        self.assertEqual(result['scope_count'], 506)
        self.assertLess(len(statements), 30)

    def test_history_is_paginated_with_no_silent_500_record_limit(self):
        self.seed_records()
        result = list_observations(self.session, self.end, 'all', page=26, page_size=20, assistant=self.assistant)
        self.assertEqual(result['total'], 506)
        self.assertEqual(result['pages'], 26)
        self.assertTrue(any(row['id'] == self.obs.id for row in result['items']))
        clamped = list_observations(self.session, self.end, 'all', page=999, page_size=20, assistant=self.assistant)
        self.assertEqual(clamped['page'], 26)

    def test_name_search_and_literal_wildcards_are_not_lost_to_sql_like(self):
        self.session.add(Stock(code='600519', name='Search Example', exchange='SH'))
        self.session.commit()
        result = list_observations(self.session, self.end, search='Search Example', assistant=self.assistant)
        self.assertEqual(result['total'], 1)
        empty = list_observations(self.session, self.end, search='%', assistant=self.assistant)
        self.assertEqual(empty['total'], 0)

    def test_status_uses_latest_verdict_up_to_selected_date(self):
        self.session.add_all([
            ReviewVerification(observation_id=self.obs.id, review_date=self.day, verdict='不符合预期'),
            ReviewVerification(observation_id=self.obs.id, review_date=self.end, verdict='继续观察')])
        self.session.commit()
        before = list_observations(self.session, self.day, status='pending', assistant=self.assistant)
        after = list_observations(self.session, self.end, status='pending', assistant=self.assistant)
        self.assertEqual(before['total'], 0)
        self.assertEqual(after['total'], 1)
        self.assertEqual(after['items'][0]['verdict'], '继续观察')

    def test_future_verification_cannot_close_historical_pending_record(self):
        self.session.add(ReviewVerification(observation_id=self.obs.id, review_date=self.end+timedelta(days=1), verdict='符合预期'))
        self.session.commit()
        result = list_observations(self.session, self.end, assistant=self.assistant)
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['items'][0]['verdict'], '待验证')

    def test_batch_context_has_the_same_fingerprint_as_single_review(self):
        self.rule()
        single = self.context()
        batch = self.assistant.contexts(self.session, [self.obs], self.end)[self.obs.id]
        self.assertEqual(single['context_hash'], batch['context_hash'])
        self.assertEqual(single['context'], batch['context'])

    def test_last_ai_report_stays_visible_on_the_next_review_day(self):
        original = self.report()
        with patch('app.services.review_ai.request_audit') as remote:
            detail = observation_detail(self.session, self.obs, self.end+timedelta(days=1), self.assistant)
        self.assertEqual(detail['entry']['audit']['id'], original['id'])
        self.assertTrue(detail['entry']['audit']['historical'])
        self.assertEqual(detail['entry']['audit']['date'], str(self.end))
        remote.assert_not_called()

    def test_changed_quote_is_reported_without_rewriting_original_evidence(self):
        report = self.report()
        original_record = self.session.get(ReviewAudit, report['id'])
        snapshot = original_record.context_json
        quote = self.session.exec(select(StockDailyQuote).where(StockDailyQuote.trade_date == self.end)).one()
        quote.close = 12
        self.session.add(quote)
        self.session.commit()
        detail = observation_detail(self.session, self.obs, self.end, self.assistant)
        saved = detail['entry']['audit']
        self.assertTrue(saved['stale'])
        self.assertTrue(any('报价' in item for item in saved['changes']))
        original_price = next(row['value'] for row in saved['facts'] if row['id'] == 'quote-'+str(self.end))
        self.assertEqual(Decimal(original_price), Decimal('11'))
        self.assertEqual(self.session.get(ReviewAudit, report['id']).context_json, snapshot)

    def test_new_rule_and_verification_are_listed_as_changes(self):
        self.report()
        self.rule()
        self.session.add(ReviewVerification(observation_id=self.obs.id, review_date=self.end, verdict='继续观察', explanation='new explanation'))
        self.session.commit()
        audit = observation_detail(self.session, self.obs, self.end, self.assistant)['entry']['audit']
        self.assertIn('已确认的量化规则有变化', audit['changes'])
        self.assertIn('人工验证已更新', audit['changes'])

    def test_list_returns_lightweight_audit_summary_and_detail_has_snapshot(self):
        self.report()
        row = list_observations(self.session, self.end, assistant=self.assistant)['items'][0]
        self.assertNotIn('facts', row['last_audit'])
        self.assertNotIn('result', row['last_audit'])
        self.assertTrue(observation_detail(self.session, self.obs, self.end, self.assistant)['entry']['audit']['facts'])

    def test_audit_history_is_paginated_and_hides_future_business_dates(self):
        self.report(self.day)
        self.report(self.end)
        older = audit_history(self.session, self.obs, self.day)
        self.assertEqual(older['total'], 1)
        first = audit_history(self.session, self.obs, self.end, page_size=1)
        second = audit_history(self.session, self.obs, self.end, page=2, page_size=1)
        self.assertEqual(first['total'], 2)
        self.assertEqual(first['items'][0]['date'], str(self.end))
        self.assertEqual(second['items'][0]['date'], str(self.day))

    def test_individual_saved_audit_cannot_bypass_historical_cutoff(self):
        report = self.report()
        with self.assertRaises(HTTPException) as caught:
            get_saved_audit(self.obs.id, report['id'], self.day, self.session)
        self.assertEqual(caught.exception.status_code, 404)

    def new_body(self, deadline=None):
        return ObservationIn(code='600000', observation_date=self.start, reason='actual reason', criterion='actual criterion',
            deadline=deadline or self.end, condition={'kind': 'hold_change', 'operator': 'ge', 'threshold_pct': '0', 'note': 'explicitly confirmed'})

    def test_create_can_save_observation_and_confirmed_rule_in_one_transaction(self):
        self.session.add(Stock(code='600000', name='fixture', exchange='SH'))
        self.session.commit()
        created = create_observation(self.new_body(), self.session)
        self.assertEqual(self.session.get(ReviewObservation, created['id']).reason, 'actual reason')
        rule = self.session.exec(select(ReviewCondition).where(ReviewCondition.observation_id == created['id'])).one()
        self.assertEqual(rule.note, 'explicitly confirmed')

    def test_invalid_initial_rule_rolls_back_the_observation_too(self):
        self.session.add(Stock(code='600000', name='fixture', exchange='SH'))
        self.session.commit()
        with self.assertRaises(HTTPException) as caught:
            create_observation(self.new_body(deadline=self.start), self.session)
        self.assertEqual(caught.exception.status_code, 400)
        self.assertFalse(self.session.exec(select(ReviewObservation).where(ReviewObservation.stock_code == '600000')).all())

    def test_creating_without_confirmed_rule_does_not_synthesize_one(self):
        self.session.add(Stock(code='600000', name='fixture', exchange='SH'))
        self.session.commit()
        body = self.new_body().model_copy(update={'condition': None})
        created = create_observation(body, self.session)
        self.assertFalse(self.session.exec(select(ReviewCondition).where(ReviewCondition.observation_id == created['id'])).all())

    def test_deadlines_use_actual_calendar_sequence_across_holidays(self):
        base = date(2026, 9, 30)
        days = [date(2026, 10, n) for n in (9, 12, 13, 14, 15, 16, 19, 20, 21, 22)]
        result = trading_deadlines(base, lambda start, end: [base]+days)
        self.assertEqual([row['date'] for row in result['options']], ['2026-10-13', '2026-10-15', '2026-10-22'])

    def test_deadlines_do_not_require_next_year_when_current_year_is_enough(self):
        base = date(2026, 11, 24)
        def calendar(start, end):
            self.assertEqual(end.year, 2026)
            return [base+timedelta(days=i) for i in range(1, 11)]
        self.assertEqual(len(trading_deadlines(base, calendar)['options']), 3)

    def test_missing_calendar_is_not_replaced_with_weekday_estimates(self):
        with self.assertRaises(RuntimeError):
            trading_deadlines(self.start, lambda start, end: [])


if __name__ == '__main__':
    unittest.main()
