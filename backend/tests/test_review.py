import os
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

with patch.dict(os.environ, {'AUTH_USERNAME':'test-user', 'AUTH_PASSWORD':'test-password-only',
                              'AUTH_SECRET':'test-signing-key-only-'*3}):
    from sqlmodel import SQLModel, Session, create_engine, select
    from app.models import (MarketDailyStat, LimitUpDaily, StockDailyQuote, Stock,
                            ReviewObservation, ReviewVerification, TradeJournal)
    from app.services.review_workbench import ReviewWorkbench
    from app.services.review_service import ReviewService
    from app.services.journal_service import JournalService
    from app.routers.review import create_observation, verify_observation, ObservationIn, VerificationIn
    from fastapi import HTTPException


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://')
        SQLModel.metadata.create_all(self.engine)
        self.session=Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)
        self.prev,self.day=date(2026,1,5),date(2026,1,6)

    def stat(self, day, count):
        self.session.add(MarketDailyStat(stat_date=day,limit_up=count))
        self.session.commit()

    def limit(self, day, code):
        self.session.add(LimitUpDaily(stock_code=code,name=code,trade_date=day,limit_type='U',limit_times=1,pct_chg=10))
        self.session.commit()

    def test_unknown_quote_is_not_decline_and_flat_is_not_up(self):
        self.stat(self.prev,2);self.stat(self.day,0)
        self.limit(self.prev,'000001');self.limit(self.prev,'000002')
        self.session.add(StockDailyQuote(stock_code='000002',trade_date=self.day,change_pct=0))
        self.session.commit()
        result=ReviewWorkbench().get(self.session,self.day)['performance']
        self.assertEqual({r['code']:r['status'] for r in result['items']},{'000001':'未知','000002':'平盘'})
        self.assertEqual(result['stats']['avg_pct'],0)
        self.assertEqual(result['stats']['quote_samples'],1)
        self.assertEqual(result['stats']['unknown'],1)

    def test_incomplete_today_cannot_report_zero_continuation(self):
        self.stat(self.prev,1);self.stat(self.day,1);self.limit(self.prev,'000001')
        result=ReviewWorkbench().get(self.session,self.day)
        self.assertFalse(result['performance']['ready'])
        self.assertIsNone(result['performance']['stats']['promote_rate'])
        self.assertIsNone(result['structure']['highest'])

    def test_history_first_rate_is_independent_of_selected_range(self):
        self.stat(self.prev,2);self.stat(self.day,1)
        self.limit(self.prev,'000001');self.limit(self.prev,'000002');self.limit(self.day,'000001')
        result=ReviewService().get_emotion_series(self.day,self.day,self.session)
        self.assertEqual(result[0]['promote_rate'],50)
        wider=ReviewService().get_emotion_series(self.prev,self.day,self.session)
        self.assertEqual(wider[-1]['promote_rate'],result[0]['promote_rate'])

    def test_historical_observation_does_not_read_future_verdict_or_price(self):
        self.session.add(Stock(code='000001',name='Example',exchange='SZ'))
        row=ReviewObservation(stock_code='000001',observation_date=self.prev,reason='original',criterion='test',deadline=self.day)
        self.session.add(row);self.session.commit();self.session.refresh(row)
        self.session.add(ReviewVerification(observation_id=row.id,review_date=self.day,verdict='符合预期'))
        for d,price in [(self.prev,10),(self.day,20)]:
            self.session.add(StockDailyQuote(stock_code='000001',trade_date=d,close=price))
        self.session.commit()
        old=ReviewWorkbench.observations(self.session,self.prev)[0]
        self.assertEqual(old['verdict'],'待验证')
        self.assertEqual(old['price_change'],0)
        now=ReviewWorkbench.observations(self.session,self.day)[0]
        self.assertEqual(now['price_change'],100)
        self.assertEqual(now['verdict'],'符合预期')

    def test_verification_does_not_overwrite_original_reason(self):
        self.session.add(Stock(code='000001',name='Example',exchange='SZ'));self.session.commit()
        created=create_observation(ObservationIn(code='000001',observation_date=self.prev,
            reason='original',criterion='condition',deadline=self.day),self.session)
        verify_observation(created['id'],VerificationIn(verdict='继续观察',explanation='evidence'),self.day,self.session)
        row=self.session.get(ReviewObservation,created['id'])
        self.assertEqual(row.reason,'original')
        self.assertEqual(row.criterion,'condition')
        with self.assertRaises(HTTPException):
            verify_observation(created['id'],VerificationIn(verdict='继续观察',explanation='evidence'),date(2026,1,1),self.session)


class JournalIntegrityTests(unittest.TestCase):
    setUp = ReviewTests.setUp
    def trade(self, direction, qty, time):
        return JournalService().create_trade('000001',direction,10,qty,0,time,None,self.session)

    def test_edit_or_delete_buy_cannot_create_later_oversell(self):
        buy=self.trade('buy',100,datetime(2026,1,5,1))
        self.trade('sell',100,datetime(2026,1,6,1))
        with self.assertRaises(ValueError):
            JournalService().delete_trade(buy['id'],self.session)
        with self.assertRaises(ValueError):
            JournalService().update_trade(buy['id'],self.session,quantity=50)
        self.assertEqual(self.session.get(TradeJournal,buy['id']).quantity,100)

    def test_legacy_missing_buy_does_not_fabricate_profit(self):
        self.session.add(TradeJournal(stock_code='000001',direction='sell',price=10,quantity=100,fee=0,traded_at=datetime(2026,1,5)))
        self.session.commit()
        stats=JournalService().get_stats(self.session)
        self.assertIsNone(stats['total_realized'])
        self.assertIsNone(stats['win_rate'])
        self.assertEqual(stats['incomplete_sell_count'],1)

    def test_negative_fee_is_rejected(self):
        with self.assertRaises(ValueError):
            JournalService().create_trade('000001','buy',10,100,-1,datetime(2026,1,5),None,self.session)
        self.assertFalse(self.session.exec(select(TradeJournal)).all())

    def test_local_calendar_day_uses_utc_boundary(self):
        self.trade('buy',100,datetime(2026,1,5,16,30,tzinfo=timezone.utc))
        service=JournalService()
        self.assertEqual(len(service.list_trades(self.session,start=self.day,end=self.day)),1)
        self.assertEqual(len(service.list_trades(self.session,start=self.prev,end=self.prev)),0)
        self.assertEqual(service.list_trade_dates(2026,1,self.session),['2026-01-06'])


if __name__=='__main__':
    unittest.main()
