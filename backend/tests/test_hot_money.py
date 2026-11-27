import json
import unittest
from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

import pandas as pd
from sqlmodel import select
import test_system as fixtures
from app.models import HotMoneyCatalog, SeatDisclosureBatch, SeatFollow, ShortTermEvent, ShortTermEventState, Stock, WatchlistItem
from app.services import hot_money as service
from app.services.seat_disclosures import (associate, association_index, build_payload, canonical_top_frame,
    catalog_entries, dumps, normalize_seat, seat_records, top_records)
from app.services.short_term import current_events, event_view
from app.services.review_assistant import ReviewAssistant
from scripts.install_hot_money_monitor import updated_crontab


class HotMoneyTests(unittest.TestCase):
    setUp = fixtures.SystemTests.setUp

    def source(self, day=None, net='10000000', reason='日涨幅偏离值达到7%的前5只证券'):
        day = day or self.now.date()
        buy, sell = Decimal('20000000'), Decimal('20000000')-Decimal(net)
        top = {'trade_date': day.strftime('%Y%m%d'), 'ts_code': '600519.SH', 'name': 'fixture',
            'reason': reason, 'close': '10', 'pct_change': '5', 'l_buy': str(buy), 'l_sell': str(sell), 'net_amount': net}
        seat = {'trade_date': top['trade_date'], 'ts_code': top['ts_code'], 'reason': reason,
            'exalter': '测试证券股份有限公司杭州路证券营业部', 'side': '0', 'buy': str(buy), 'sell': str(sell), 'net_buy': net}
        return top, seat

    def catalog(self):
        row = HotMoneyCatalog(digest='fixture', entries_json=dumps([{'name': '样例游资', 'orgs': ['测试证券杭州路']}]),
                              created_at=self.now.replace(tzinfo=None))
        self.session.add(row); self.session.commit(); self.session.refresh(row)
        return row

    def sync(self, day=None, net='10000000', reason='日涨幅偏离值达到7%的前5只证券', now=None):
        day = day or self.now.date()
        top, seat = self.source(day, net, reason)
        client = Mock()
        client.hm_list.return_value = pd.DataFrame([{'name': '样例游资', 'orgs': '["测试证券杭州路"]'}])
        client.top_list.return_value = pd.DataFrame([top])
        client.top_inst.return_value = pd.DataFrame([seat, {**seat, 'side': '1'}])
        batch, changed = service.sync_day(self.session, day, client, now=now or self.now)
        return batch, changed, client

    def calendar(self, size=25):
        natural = pd.date_range(self.now.date()-timedelta(days=80), self.now.date())
        dates = [day.date() for day in natural if day.weekday() < 5][-size:]
        patcher = patch('app.services.hot_money.EtfService.cached_trade_dates', return_value=(dates, self.now))
        patcher.start(); self.addCleanup(patcher.stop)
        return dates

    def watch(self):
        self.session.add(Stock(code='600519', name='fixture', exchange='SH'))
        self.session.add(WatchlistItem(stock_code='600519', created_at=self.now.replace(tzinfo=None)-timedelta(days=1)))
        self.session.commit()

    def test_named_seat_cross_buy_sell_and_multi_reason_are_not_added(self):
        top, seat = self.source()
        other = {**top, 'reason': '日换手率达到20%的前5只证券'}
        seats = [seat, {**seat, 'side': '1'}, {**seat, 'reason': other['reason']}]
        payload = build_payload(top_records(pd.DataFrame([top, other]), self.now.date()),
            seat_records(pd.DataFrame(seats), self.now.date()), json.loads(self.catalog().entries_json))
        selected = [row for row in payload['reports'] if row['selected']]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['net'], '10000000')
        self.assertEqual(len(selected[0]['seats']), 1)

    def test_anonymous_same_side_rows_are_preserved_without_identity(self):
        top, seat = self.source()
        institution = {**seat, 'exalter': '机构专用'}
        payload = build_payload([top], [institution, institution, {**institution, 'side': '1'}], [])
        seats = payload['reports'][0]['seats']
        self.assertEqual(len(seats), 2)
        self.assertTrue(all(row['type'] == 'institution' and not row['names'] for row in seats))

    def test_daily_and_cumulative_reports_are_separate(self):
        top, seat = self.source()
        multi, multi_seat = self.source(net='30000000', reason='连续三个交易日内涨幅偏离值累计达到20%')
        payload = build_payload([top, multi], [seat, multi_seat], [])
        self.assertEqual({row['period'] for row in payload['reports'] if row['selected']}, {'day', 'multi'})
        self.assertEqual(len(canonical_top_frame(pd.DataFrame([multi, top]))), 1)
        self.assertEqual(canonical_top_frame(pd.DataFrame([multi, top])).iloc[0]['net_amount'], '10000000')

    def test_catalog_json_legal_suffix_and_ambiguous_alias(self):
        entries = catalog_entries(pd.DataFrame([{'name': '甲', 'orgs': '["测试证券杭州路"]'},
            {'name': '乙', 'orgs': '["测试证券股份有限公司杭州路证券营业部"]'}]))
        index = association_index(entries)
        matched = associate('测试证券有限责任公司杭州路证券营业部', index)
        self.assertEqual(matched['association'], 'ambiguous')
        self.assertEqual(associate('机构专用', index)['association'], 'anonymous')
        self.assertEqual(associate('未知营业部', index)['association'], 'unmapped')

    def test_conflicting_named_seat_amounts_not_summed_into_history(self):
        top, seat = self.source()
        other = {**seat, 'buy': '30000000', 'net_buy': '20000000'}
        payload = build_payload([top], [seat, other], [])
        self.assertTrue(all(row['conflict'] for row in payload['reports'][0]['seats']))
        self.assertEqual(payload['quality']['warnings'], 1)

    def test_decimal_finite_nonnegative_and_wrong_date_rejected(self):
        top, seat = self.source()
        for key, value in [('l_buy', '-1'), ('net_amount', 'NaN'), ('trade_date', '20270101')]:
            with self.assertRaises(ValueError):
                top_records(pd.DataFrame([{**top, key: value}]), self.now.date())
        with self.assertRaises(ValueError):
            seat_records(pd.DataFrame([{**seat, 'side': '2'}]), self.now.date())
        broken = seat_records(pd.DataFrame([{**seat, 'net_buy': '9'}]), self.now.date())[0]
        self.assertIsNone(broken['net_buy'])
        self.assertTrue(broken['amount_issue'])

    def test_invalid_source_seat_amount_keeps_report_and_marks_unknown(self):
        top, seat = self.source()
        for bad in ({'buy': '-1'}, {'sell': float('nan')}, {'net_buy': float('inf')}):
            payload = build_payload([top], seat_records(pd.DataFrame([{**seat, **bad}]), self.now.date()), [])
            report = payload['reports'][0]
            self.assertEqual(report['net'], '10000000')
            self.assertIsNone(report['seats'][0]['net'])
            self.assertTrue(report['seats'][0]['amount_issue'])
            self.assertTrue(report['warnings'])

    def test_convertible_bonds_excluded(self):
        top, seat = self.source()
        records = top_records(pd.DataFrame([top, {**top, 'ts_code': '123456.SZ'}]), self.now.date())
        self.assertEqual(len(records), 1)

    def test_sync_idempotent_and_revision_keeps_original_raw(self):
        self.catalog()
        first, changed, _ = self.sync()
        original = first.raw_json
        same, changed, _ = self.sync()
        self.assertFalse(changed); self.assertEqual(first.id, same.id)
        later, changed, _ = self.sync(net='9000000', now=self.now+timedelta(minutes=1))
        self.assertTrue(changed); self.assertNotEqual(first.id, later.id)
        self.assertEqual(self.session.get(SeatDisclosureBatch, first.id).raw_json, original)
        detail = service.stock_detail(self.session, '600519', self.now.date(), first.id)
        self.assertEqual(detail['reports'][0]['net'], '10000000')
        self.assertEqual(len(detail['versions']), 2)

    def test_empty_source_and_actual_exception_preserve_old_batch(self):
        self.catalog(); old, _, client = self.sync()
        client.top_inst.return_value = pd.DataFrame()
        self.assertIsNone(service.sync_day(self.session, self.now.date(), client, now=self.now)[0])
        client.top_inst.side_effect = RuntimeError('permission denied fixture')
        with self.assertRaises(RuntimeError):
            service.sync_day(self.session, self.now.date(), client, now=self.now)
        self.assertEqual(service.latest_batch(self.session, self.now.date()).id, old.id)

    def test_future_and_unclosed_day_cannot_be_synced(self):
        with self.assertRaises(ValueError):
            service.sync_day(self.session, self.now.date()+timedelta(days=1), Mock(), now=self.now)
        with self.assertRaises(ValueError):
            service.sync_day(self.session, self.now.date(), Mock(), now=self.now.replace(hour=1))

    def test_history_excludes_future_and_requires_actual_calendar_for_first_tag(self):
        self.catalog(); dates = self.calendar()
        self.sync(dates[-2]); self.sync(dates[-1])
        history = service.seat_history(self.session, dates[-2], 'person', '样例游资', 20)
        self.assertTrue(all(item['date'] <= str(dates[-2]) for item in history['items']))
        dashboard = service.dashboard(self.session, dates[-1])
        self.assertFalse(dashboard['coverage']['complete'])
        self.assertNotIn('近20交易日首次披露', dashboard['items'][0]['tags'])

    def test_calendar_complete_window_detects_first_and_contiguous_not_gaps(self):
        self.catalog(); dates = self.calendar()
        for day in dates[-20:]:
            batch, _, _ = self.sync(day)
            # Distinct fixture stock on earlier days, with verified reports still present.
            if day != dates[-1]:
                value = json.loads(batch.payload_json)
                for report in value['reports']:report['code'] = '000001'
                batch.payload_json = dumps(value);self.session.add(batch);self.session.commit()
        result = service.dashboard(self.session, dates[-1])
        self.assertTrue(result['coverage']['complete'])
        self.assertIn('近20交易日首次披露', result['items'][0]['tags'])
        for day in dates[-3:]:
            self.sync(day, net='9000000')
        result = service.dashboard(self.session, dates[-1])
        self.assertIn('连续3交易日披露净买', result['items'][0]['tags'])

    def test_follow_confirmation_idempotency_tombstone_and_anonymous_guard(self):
        self.catalog()
        with self.assertRaises(ValueError):service.save_follow(self.session, 'seat', '机构专用', True)
        with self.assertRaises(ValueError):service.save_follow(self.session, 'person', '伪造游资', True)
        service.save_follow(self.session, 'person', '样例游资', True)
        service.save_follow(self.session, 'person', '样例游资', True)
        self.assertEqual(len(self.session.exec(select(SeatFollow)).all()), 1)
        service.save_follow(self.session, 'person', '样例游资', False)
        self.assertEqual(service.follows(self.session), [])

    def test_watch_priority_focus_and_followed_seat_filter(self):
        self.catalog(); self.watch(); self.sync()
        service.save_follow(self.session, 'person', '样例游资', True)
        result = service.dashboard(self.session, self.now.date(), 'followed')
        self.assertEqual(result['counts']['mine'], 1)
        self.assertEqual(result['counts']['followed'], 1)
        self.assertEqual(result['focus'][0]['names'], ['样例游资'])

    def test_events_reuse_read_ignore_upgrade_and_history_backfill_is_silent(self):
        self.catalog(); self.watch(); batch, _, _ = self.sync()
        service.publish_events(self.session, batch, notify=False, now=self.now)
        old = current_events(self.session, self.now.date(), 'close')[0]
        self.assertFalse(event_view(old, now=self.now)['unread'])
        self.assertEqual(json.loads(old.snapshot_json)['batch_id'], batch.id)
        newer, _, _ = self.sync(net='-60000000', now=self.now+timedelta(minutes=1))
        self.session.add(ShortTermEventState(event_key=old.event_key, cycle=old.cycle, action='read', level=1, effective_date=self.now.date()))
        self.session.commit()
        service.publish_events(self.session, newer, notify=True, now=self.now+timedelta(minutes=1))
        event = current_events(self.session, self.now.date(), 'close')[0]
        self.assertEqual(event.level, 2)
        state = self.session.exec(select(ShortTermEventState)).first()
        self.assertTrue(event_view(event, state, self.now+timedelta(minutes=2))['unread'])
        count = len(self.session.exec(select(ShortTermEvent)).all())
        service.publish_events(self.session, newer, notify=True, now=self.now+timedelta(minutes=2))
        self.assertEqual(len(self.session.exec(select(ShortTermEvent)).all()), count)

    def test_gets_and_fact_collection_never_call_source_or_model(self):
        self.catalog(); self.sync()
        with patch('app.services.tushare_client.requests.post') as post:
            service.dashboard(self.session, self.now.date())
            service.stock_detail(self.session, '600519', self.now.date())
            facts = service.facts_for_codes(self.session, {'600519'}, self.now.date())
        post.assert_not_called()
        self.assertEqual(facts['600519'][0]['value']['disclosed_net_yuan'], '10000000')
        earlier = service.facts_for_codes(self.session, {'600519'}, self.now.date()-timedelta(days=1))
        self.assertFalse(earlier)

    def test_cron_is_idempotent_preserves_other_jobs_and_rejects_malformed_block(self):
        original = 'CRON_TZ=Asia/Shanghai\n0 16 * * 1-5 other-job\n'
        new = updated_crontab(original, '/project/backend', '/project/venv/python')
        self.assertIn('other-job', new)
        self.assertEqual(updated_crontab(new, '/project/backend', '/project/venv/python'), new)
        self.assertIn('45 16,18,20,21,22,23', new)
        with self.assertRaises(ValueError):updated_crontab('# BEGIN stocks hot money monitor\n', '/x', '/y')

    def test_routes_require_auth_and_reject_future_dates_before_reading(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.auth import create_token
        from app.config import settings
        client = TestClient(app)
        self.assertEqual(client.get('/api/hot-money/dashboard?date=2099-01-01').status_code, 401)
        client.headers['Authorization'] = 'Bearer '+create_token(settings.auth_username)['token']
        self.assertEqual(client.get('/api/hot-money/dashboard?date=2099-01-01').status_code, 400)
        self.assertEqual(client.get('/api/hot-money/history?date=2026-11-19&subject=fixture&days=7').status_code, 422)


if __name__ == '__main__':unittest.main()
