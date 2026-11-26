import json
import unittest
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from unittest.mock import Mock,patch

import pandas as pd
from sqlalchemy import delete
from sqlmodel import select
import test_system as fixtures
from app.models import (LimitUpDaily,MarketDailyStat,SectorDaily,ShortTermEvent,ShortTermEventState,
    ShortTermMinute,Stock,StockDailyQuote,StockAdjustmentFactor,WatchlistItem)
from app.services.short_term import (SH,ShortTermSettings,candidate,close_signals,current_events,event_view,
    minute_phase,minute_signals,persist)
from app.services.short_term_monitor import normalize_minutes,scan_intraday
from scripts.install_short_term_monitor import updated_crontab


class ShortTermTests(unittest.TestCase):
    setUp=fixtures.SystemTests.setUp

    def calendar(self):
        natural=pd.date_range(self.now.date()-timedelta(days=110),self.now.date())
        self.etf._frame_cache.put('calendar-2026',pd.DataFrame([{'cal_date':d.strftime('%Y%m%d'),'is_open':int(d.weekday()<5)} for d in natural]))
        return [d.date() for d in natural if d.weekday()<5]

    def minutes(self,count=21):
        end=datetime(2026,11,19,2,1)
        return [ShortTermMinute(stock_code='600519',bar_time=end-timedelta(minutes=i),close='10.3' if i==0 else '10',
            amount='100000000' if i==0 else '10000000') for i in range(count)]

    def signal(self,level=1,active=True,actual='3'):
        return candidate(self.now.date(),'intraday','move_5m','600519','fixture',level,actual,'0','fixture rule',self.now.isoformat(),triggered=active)

    def test_continuous_minutes_trigger_price_and_amount_with_separate_baselines(self):
        rows=self.minutes();now=rows[0].bar_time.replace(tzinfo=timezone.utc)
        signals,coverage=minute_signals('600519','fixture',rows,now,ShortTermSettings())
        self.assertTrue(coverage['move_ready'] and coverage['amount_ready'])
        self.assertTrue(all(item['active'] for item in signals))
        self.assertEqual(Decimal(signals[0]['snapshot']['actual']),3)

    def test_missing_minute_and_lunch_are_not_stitched(self):
        rows=self.minutes();now=rows[0].bar_time.replace(tzinfo=timezone.utc)
        signals,coverage=minute_signals('600519','fixture',rows[:3]+rows[4:],now,ShortTermSettings())
        self.assertFalse(coverage['move_ready']);self.assertFalse(signals)
        rows=[ShortTermMinute(stock_code='600519',bar_time=datetime(2026,11,19,5,1),close='11',amount='1'),
              ShortTermMinute(stock_code='600519',bar_time=datetime(2026,11,19,3,30),close='10',amount='1')]
        self.assertFalse(minute_signals('600519','fixture',rows,rows[0].bar_time.replace(tzinfo=timezone.utc),ShortTermSettings())[1]['move_ready'])

    def test_future_and_stale_minutes_cannot_trigger(self):
        rows=self.minutes();now=rows[0].bar_time.replace(tzinfo=timezone.utc)
        self.assertFalse(minute_signals('600519','fixture',rows,now-timedelta(minutes=30),ShortTermSettings())[0])
        self.assertFalse(minute_signals('600519','fixture',rows,now+timedelta(minutes=3),ShortTermSettings())[0])

    def test_normalization_rejects_future_wrong_security_and_unclosed_values(self):
        now=datetime(2026,11,19,2,1,tzinfo=timezone.utc)
        good={'ts_code':'600519.SH','time':'2026-11-19 10:01:00','close':10,'amount':100,'freq':'1MIN'}
        for changes in ({'time':'2026-11-19 10:02:00'},{'ts_code':'000001.SZ'},{'close':float('nan')},
                        {'amount':-1},{'time':'2026-11-19 12:00:00'},{'freq':'5MIN'}):
            with self.assertRaises(ValueError):normalize_minutes(pd.DataFrame([{**good,**changes}]),{'600519.SH'},now)
        self.assertEqual(normalize_minutes(pd.DataFrame([good]),{'600519.SH'},now)[0]['amount'],'100')

    def test_rescanning_same_level_retains_first_trigger_snapshot(self):
        self.assertEqual(persist(self.session,[self.signal()],self.now),1)
        original=current_events(self.session,self.now.date(),'intraday')[0].snapshot_json
        self.assertEqual(persist(self.session,[self.signal(actual='3.5')],self.now+timedelta(minutes=1)),0)
        self.assertEqual(current_events(self.session,self.now.date(),'intraday')[0].snapshot_json,original)

    def test_read_low_level_does_not_hide_upgrade_and_high_read_covers_downgrade(self):
        persist(self.session,[self.signal()],self.now)
        old=current_events(self.session,self.now.date(),'intraday')[0]
        state=ShortTermEventState(event_key=old.event_key,cycle=1,level=1,action='read',effective_date=self.now.date())
        self.assertFalse(event_view(old,state,self.now)['unread'])
        persist(self.session,[self.signal(level=2)],self.now+timedelta(minutes=1))
        new=current_events(self.session,self.now.date(),'intraday')[0]
        self.assertTrue(event_view(new,state,self.now+timedelta(minutes=1))['unread'])
        state.level=2
        self.assertFalse(event_view(old,state,self.now+timedelta(minutes=1))['unread'])

    def test_new_cycle_obeys_cooldown_and_does_not_reuse_old_read_state(self):
        persist(self.session,[self.signal()],self.now)
        persist(self.session,[self.signal(active=False)],self.now+timedelta(minutes=1))
        persist(self.session,[self.signal()],self.now+timedelta(minutes=2))
        new=current_events(self.session,self.now.date(),'intraday')[0]
        self.assertEqual(new.cycle,2)
        self.assertTrue(event_view(new,None,self.now+timedelta(minutes=2))['cooling'])
        self.assertTrue(event_view(new,None,self.now+timedelta(minutes=16))['unread'])

    def test_historical_backfill_is_recorded_without_unread_notification(self):
        persist(self.session,[self.signal()],self.now,notify=False)
        row=current_events(self.session,self.now.date(),'intraday')[0]
        self.assertFalse(event_view(row,None,self.now)['unread'])

    def test_outside_trading_hours_never_calls_source(self):
        self.calendar();client=Mock()
        result=scan_intraday(self.session,client,self.etf,self.store,self.now)
        self.assertEqual(result['status'],'skipped');client.query.assert_not_called()

    def test_unknown_calendar_is_not_a_confirmed_holiday_or_success(self):
        client=Mock();now=datetime(2026,11,19,2,1,tzinfo=timezone.utc)
        with patch.object(self.etf,'_fetch_trade_dates',side_effect=RuntimeError('calendar unavailable')):
            result=scan_intraday(self.session,client,self.etf,self.store,now)
        self.assertEqual(result['status'],'unknown');self.assertEqual(result['source_errors'],1)
        client.query.assert_not_called()

    def test_real_minute_source_failure_is_recorded_separately_from_missing_samples(self):
        self.calendar();now=datetime(2026,11,19,2,1,tzinfo=timezone.utc)
        self.session.add(Stock(code='600519',name='fixture',exchange='SH'))
        self.session.add(WatchlistItem(stock_code='600519',created_at=datetime(2026,11,18)));self.session.commit()
        client=Mock();client.query.side_effect=RuntimeError('source HTTP 502')
        report=scan_intraday(self.session,client,self.etf,self.store,now)
        self.assertEqual(report['source_errors'],1)
        self.assertEqual(report['fresh'],0)

    def test_stale_source_is_not_used_to_resolve_an_existing_event(self):
        self.calendar();now=datetime(2026,11,19,2,1,tzinfo=timezone.utc)
        self.session.add(Stock(code='600519',name='fixture',exchange='SH'))
        self.session.add(WatchlistItem(stock_code='600519',created_at=datetime(2026,11,18)))
        self.session.commit();persist(self.session,[self.signal()],now)
        client=Mock();client.query.return_value=pd.DataFrame([{'ts_code':'600519.SH','time':'2026-11-19 09:58:00','close':10,'amount':100}])
        report=scan_intraday(self.session,client,self.etf,self.store,now)
        self.assertEqual(report['fresh'],0);self.assertEqual(report['status'],'partial')
        self.assertTrue(current_events(self.session,self.now.date(),'intraday')[0].active)

    def close_fixture(self):
        dates=self.calendar()[-21:];day=dates[-1]
        self.session.add(Stock(code='600519',name='fixture',exchange='SH'))
        self.session.add(WatchlistItem(stock_code='600519',created_at=datetime(2026,1,1)))
        for d in dates:
            current=d==day;up,down,opened=(1,20,50) if current else (20,1,5)
            self.session.add(MarketDailyStat(stat_date=d,up=50,down=50,total=100,total_turnover=1e9,limit_up=up,limit_down=down,opened_limit=opened))
            for kind,count in [('U',up),('D',down),('Z',opened)]:
                for i in range(count):
                    code='600519' if kind=='U' and i==0 and not current else f'{dict(U=1,D=2,Z=3)[kind]}{i:05d}'
                    self.session.add(LimitUpDaily(stock_code=code,name=code,trade_date=d,limit_type=kind,
                        limit_times=5 if d==dates[-2] else 1 if current else 2))
            self.session.add(StockDailyQuote(stock_code='600519',trade_date=d,close=9 if current else 10,amount=50000000 if current else 10000000))
        for d in dates[-2:]:self.session.add(StockAdjustmentFactor(stock_code='600519',trade_date=d,factor='1'))
        self.session.commit();return day,dates

    def test_close_scan_uses_covered_history_and_independent_price_factors(self):
        day,dates=self.close_fixture()
        signals,coverage=close_signals(self.session,day,ShortTermSettings(),self.etf)
        kinds={item['kind'] for item in signals if item['active']}
        self.assertTrue({'break_rate','limit_down','height_drop','promotion_drop','daily_move','after_limit_weak','daily_amount'}<=kinds)
        self.assertEqual(coverage['price_pairs'],1)
        self.session.exec(delete(StockAdjustmentFactor).where(StockAdjustmentFactor.trade_date==dates[-2]));self.session.commit()
        signals,coverage=close_signals(self.session,day,ShortTermSettings(),self.etf)
        self.assertFalse(any(item['kind']=='daily_move' for item in signals))
        self.assertEqual(coverage['price_pairs'],0)

    def test_incomplete_limit_rows_do_not_create_market_alerts(self):
        day,_=self.close_fixture()
        row=self.session.exec(select(LimitUpDaily).where(LimitUpDaily.trade_date==day,LimitUpDaily.limit_type=='Z')).first()
        self.session.delete(row);self.session.commit()
        signals,coverage=close_signals(self.session,day,ShortTermSettings(),self.etf)
        self.assertFalse(coverage['market_ready'])
        self.assertFalse(any(item['category']=='market' for item in signals))

    def test_future_prices_do_not_change_historical_close_signal(self):
        day,_=self.close_fixture()
        before=close_signals(self.session,day,ShortTermSettings(),self.etf)[0]
        self.session.add(StockDailyQuote(stock_code='600519',trade_date=day+timedelta(days=1),close=1000,amount=1e12));self.session.commit()
        self.assertEqual(before,close_signals(self.session,day,ShortTermSettings(),self.etf)[0])

    def test_sector_rank_requires_comparable_universe(self):
        day,dates=self.close_fixture()
        for d in dates[-2:]:
            for i in range(20):self.session.add(SectorDaily(sector_type='industry',sector_code=str(i),sector_name=str(i),trade_date=d,
                change_pct=30 if d==day and i==19 else 20-i,volume=100))
        self.session.commit()
        signals,_=close_signals(self.session,day,ShortTermSettings(),self.etf)
        self.assertTrue(any(row['kind']=='sector_jump' and row['subject']=='industry:19' and row['active'] for row in signals))

    def test_cron_install_is_repeatable_and_preserves_other_jobs(self):
        from pathlib import Path
        old='CRON_TZ=Asia/Shanghai\n0 16 * * 1-5 python existing.py\n'
        new=updated_crontab(old,Path('/workspace/backend'),Path('/workspace/backend/venv/bin/python'))
        self.assertIn('existing.py',new)
        self.assertEqual(new,updated_crontab(new,Path('/workspace/backend'),Path('/workspace/backend/venv/bin/python')))
        self.assertIn('0,1 15 * * 1-5',new)


if __name__=='__main__':unittest.main()
