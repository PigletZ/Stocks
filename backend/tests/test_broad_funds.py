import copy
import json
import unittest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

import pandas as pd
from pydantic import ValidationError
from sqlmodel import select
import test_system as fixtures
from app.models import BroadFundBatch, BroadFundEvidence, ShortTermEvent, ShortTermEventState
from app.services import broad_funds as funds, broad_fund_evidence as evidence
from app.services.short_term import current_events, event_view
from scripts.install_broad_funds_monitor import updated_crontab
from scripts.sync_broad_funds import missing_status


class BroadFundTests(unittest.TestCase):
    setUp = fixtures.SystemTests.setUp

    def data(self):
        dates = [day.date() for day in pd.date_range(self.now.date()-timedelta(days=90),self.now.date()) if day.weekday()<5][-45:]
        data = {'basket_version': funds.BASKET_VERSION, 'members': [], 'dates': list(map(str,dates)), 'records': {}, 'issues': []}
        for code,group in funds.BASKET.items():
            data['members'].append({'ts_code':code,'code':code.split('.')[0],'name':'fixture '+code,'group':group,'listed':'2000-01-01','benchmark':group})
            data['records'][code] = {str(day):{'shares':str(1000000000+index*10000000),'nav':'2',
                'nav_ann_date':str(day),'close':'2','factor':'1','amount':'1000000000' if day==dates[-1] else '100000000'} for index,day in enumerate(dates)}
        return data

    def batch(self,data=None):
        return funds.save_batch(self.session,data or self.data(),{'fixture':'source'},now=self.now)[0]

    def fake_client(self):
        data = self.data();client = Mock()
        client.fund_basic.return_value = pd.DataFrame([{'ts_code':code,'name':'fixture ETF '+code,'benchmark':group,'status':'L','list_date':'20000101'} for code,group in funds.BASKET.items()])
        client.fund_share.return_value = pd.DataFrame([{'ts_code':code,'trade_date':day.replace('-',''),'fd_share':Decimal(point['shares'])/10000}
            for code,points in data['records'].items() for day,point in points.items()])
        def query(api,ts_code,**kwargs):
            rows=[]
            for day,point in data['records'][ts_code].items():
                row={'ts_code':ts_code,'trade_date':day.replace('-','')}
                if api=='fund_daily':row.update(close=point['close'],amount=Decimal(point['amount'])/1000)
                elif api=='fund_nav':row.update(nav_date=row.pop('trade_date'),ann_date=day.replace('-',''),unit_nav=point['nav'])
                else:row.update(adj_factor=point['factor'])
                rows.append(row)
            return pd.DataFrame(rows)
        client.query.side_effect=query
        return client,data

    def body(self,**changes):
        values={'subject':'测试主体','kind':'bought','publication_date':self.now.date(),'report_date':None,
            'codes':[],'source_url':'https://www.sse.com.cn/disclosure/example.shtml','title':'测试官方原文','summary':'测试：原文明示的范围，非真实业务登记','confirmed':True}
        return evidence.EvidenceInput(**{**values,**changes})

    def test_units_converted_once_and_decimal_formula(self):
        client,original=self.fake_client()
        data,_=funds.collect(client,list(map(date.fromisoformat,original['dates'])),self.now)
        row=funds.point_view(data,'510300.SH',original['dates'][-1])
        self.assertEqual(Decimal(row['share_delta']),10000000)
        self.assertEqual(Decimal(row['estimate']),20000000)
        self.assertEqual(Decimal(row['amount']),1000000000)
        self.assertEqual(Decimal(row['amount_multiple']),10)

    def test_price_movement_not_used_as_flow_or_identity(self):
        data=self.data();code='510300.SH';day=data['dates'][-1]
        data['records'][code][day]['close']='200'
        view=funds.summarize(self.batch(data),self.now.date())
        self.assertEqual(view['members'][0]['flow']['estimate'],'20000000')
        self.assertTrue(all(row['buyer']=='未知' for row in view['members']))

    def test_no_close_price_substitute_when_nav_missing(self):
        data=self.data();data['records']['510300.SH'][data['dates'][-1]]['nav']=None
        view=funds.summarize(self.batch(data),self.now.date())
        self.assertIsNone(view['members'][0]['flow']['estimate'])
        self.assertEqual(view['flow_valid'],9)
        self.assertIsNone(view['estimate'])
        self.assertFalse(view['source_ready'])

    def test_zero_delta_is_zero_and_missing_is_not_zero(self):
        data=self.data();code='510300.SH';day=data['dates'][-1];prior=data['dates'][-2]
        data['records'][code][day]['shares']=data['records'][code][prior]['shares']
        self.assertEqual(Decimal(funds.point_view(data,code,day)['estimate']),0)
        del data['records'][code][prior]['shares']
        point=funds.point_view(data,code,day)
        self.assertIsNone(point['share_delta']);self.assertIsNone(point['estimate'])

    def test_factor_change_suppresses_split_or_dividend_flow(self):
        data=self.data();code='510300.SH';day=data['dates'][-1]
        data['records'][code][day].update(factor='2',close='1')
        point=funds.point_view(data,code,day)
        self.assertEqual(Decimal(point['change_pct']),0)
        self.assertIsNone(point['estimate'])
        self.assertTrue(any('口径' in line or '折算' in line for line in point['missing']))

    def test_exact_twenty_trade_day_baseline_no_gap_filling(self):
        data=self.data();code='510300.SH';day=data['dates'][-1]
        self.assertTrue(funds.point_view(data,code,day)['amount_spike'])
        del data['records'][code][data['dates'][-10]]['amount']
        point=funds.point_view(data,code,day)
        self.assertIsNone(point['amount_multiple']);self.assertFalse(point['amount_spike'])

    def test_market_and_share_dates_are_independent_and_not_stitched(self):
        data=self.data();last=data['dates'][-1]
        for code in funds.BASKET:del data['records'][code][last]['shares']
        view=funds.summarize(self.batch(data),self.now.date())
        self.assertEqual(view['market_date'],last)
        self.assertEqual(view['flow_date'],data['dates'][-2])
        self.assertEqual(view['flow_valid'],10)
        self.assertFalse(view['source_ready'])

    def test_consecutive_estimates_require_every_member_and_adjacent_days(self):
        data=self.data();day=data['dates'][-1]
        del data['records']['510300.SH'][data['dates'][-2]]['nav']
        view=funds.summarize(self.batch(data),self.now.date())
        group=next(row for row in view['groups'] if row['name']=='沪深300')
        self.assertFalse(group['streak_ready']);self.assertEqual(group['positive_days'],1)

    def test_future_price_and_share_points_do_not_enter_historical_view(self):
        data=self.data();batch=self.batch(data);target=date.fromisoformat(data['dates'][-2])
        view=funds.summarize(batch,target)
        self.assertLessEqual(view['market_date'],str(target));self.assertLessEqual(view['flow_date'],str(target))
        history=funds.history(self.session,target,'510300.SH',batch.id)
        self.assertTrue(all(point['date']<=str(target) for point in history['items']))
        self.assertEqual(Decimal(history['items'][0]['amount']),100000000)

    def test_revisions_preserve_source_snapshot_and_explicit_history_version(self):
        data=self.data();old=self.batch(data);original=old.data_json
        same,changed=funds.save_batch(self.session,data,{},now=self.now)
        self.assertEqual(same.id,old.id);self.assertFalse(changed)
        newer=copy.deepcopy(data);newer['records']['510300.SH'][data['dates'][-1]]['nav']='3'
        new,changed=funds.save_batch(self.session,newer,{},now=self.now+timedelta(minutes=1))
        self.assertTrue(changed);self.assertNotEqual(old.id,new.id)
        self.assertEqual(self.session.get(BroadFundBatch,old.id).data_json,original)
        self.assertEqual(funds.history(self.session,self.now.date(),'510300.SH',old.id)['items'][0]['nav'],'2')

    def test_backfilled_older_window_does_not_replace_latest_market_window(self):
        data=self.data();new=self.batch(data)
        older=copy.deepcopy(data);older['dates']=older['dates'][:-5]
        self.batch(older)
        self.assertEqual(funds.find_batch(self.session,self.now.date()).id,new.id)

    def test_request_failure_and_empty_market_cannot_replace_good_snapshot(self):
        old=self.batch();client,data=self.fake_client();client.query.side_effect=RuntimeError('fixture transport failure')
        with self.assertRaises(RuntimeError):funds.collect(client,list(map(date.fromisoformat,data['dates'])),self.now)
        blank=copy.deepcopy(data)
        for code in funds.BASKET:
            for row in blank['records'][code].values():row['close']=None
        self.assertIsNone(funds.save_batch(self.session,blank,{},self.now)[0])
        self.assertEqual(funds.find_batch(self.session,self.now.date()).id,old.id)

    def test_wrong_codes_dates_and_truncated_frames_rejected(self):
        sample=pd.DataFrame([{'ts_code':'510300.SH','trade_date':self.now.strftime('%Y%m%d'),'fd_share':1}])
        first=self.now.date()-timedelta(days=90);last=self.now.date()
        with self.assertRaises(ValueError):funds.source_rows(sample,'fund_share',['159919.SZ'],first,last)
        with self.assertRaises(ValueError):funds.source_rows(sample,'fund_share',['510300.SH'],first,last-timedelta(days=1))
        with self.assertRaises(ValueError):funds.source_rows(pd.concat([sample]*2000),'fund_share',['510300.SH'],first,last)

    def test_unknown_numeric_and_duplicate_nav_conflict_not_filled_with_zero(self):
        client,data=self.fake_client();original=client.query.side_effect
        def duplicate(api,**params):
            frame=original(api,**params)
            if api=='fund_nav' and params['ts_code']=='510300.SH':
                bad=frame.iloc[[-1]].copy();bad['unit_nav']=999
                frame=pd.concat([frame,bad])
            return frame
        client.query.side_effect=duplicate
        result,_=funds.collect(client,list(map(date.fromisoformat,data['dates'])),self.now)
        self.assertIsNone(result['records']['510300.SH'][data['dates'][-1]]['nav'])
        self.assertTrue(result['issues'])

    def test_future_nav_announcement_not_treated_as_available(self):
        client,data=self.fake_client();original=client.query.side_effect
        def future(api,**params):
            frame=original(api,**params)
            if api=='fund_nav':frame.loc[frame.nav_date==self.now.strftime('%Y%m%d'),'ann_date']='20990101'
            return frame
        client.query.side_effect=future
        result,_=funds.collect(client,list(map(date.fromisoformat,data['dates'])),self.now)
        self.assertFalse(result['records']['510300.SH'][data['dates'][-1]].get('nav'))

    def test_events_silent_for_history_and_reuse_read_upgrade(self):
        batch=self.batch();funds.publish_events(self.session,batch,notify=False,now=self.now)
        events=current_events(self.session,self.now.date(),'close')
        self.assertTrue(events);self.assertTrue(all(row.category=='etf' for row in events))
        self.assertTrue(all(not event_view(row,now=self.now)['unread'] for row in events))
        count=len(self.session.exec(select(ShortTermEvent)).all())
        funds.publish_events(self.session,batch,notify=True,now=self.now+timedelta(minutes=1))
        self.assertEqual(len(self.session.exec(select(ShortTermEvent)).all()),count)
        source=json.loads(events[0].snapshot_json)
        self.assertEqual(source['batch_id'],batch.id)
        self.assertIn('身份',source['rule'] if '身份' in source['rule'] else source['limitation'])

    def test_incomplete_data_does_not_resolve_existing_trigger(self):
        batch=self.batch();funds.publish_events(self.session,batch,notify=True,now=self.now)
        old=next(row for row in current_events(self.session,self.now.date(),'close') if row.kind=='broad_volume_sync')
        data=self.data()
        for code in funds.BASKET:del data['records'][code][data['dates'][-1]]['amount']
        later=self.batch(data);funds.publish_events(self.session,later,notify=True,now=self.now+timedelta(minutes=1))
        current=next(row for row in current_events(self.session,self.now.date(),'close') if row.kind=='broad_volume_sync')
        self.assertEqual(current.id,old.id);self.assertTrue(current.active)

    def test_evidence_confirmation_official_domain_dates_and_scope_validation(self):
        for values in ({'confirmed':False},{'source_url':'https://www.sse.com.cn.evil.example/a'},
            {'source_url':'https://user:secret@www.sse.com.cn/a'},{'source_url':'javascript:alert(1)'},
            {'publication_date':date(2099,1,1)},{'kind':'holding'}, {'codes':['999999.SH']}):
            with self.assertRaises(ValidationError):self.body(**values)

    def test_evidence_idempotency_withdrawal_and_restore_keep_old_history(self):
        body=self.body();first=evidence.save(self.session,body);same=evidence.save(self.session,body)
        self.assertEqual(first['id'],same['id'])
        withdrawn=evidence.withdraw(self.session,first['id'],'fixture reason')
        self.assertFalse(withdrawn['active']);self.assertEqual(evidence.listing(self.session,self.now.date())['total'],0)
        self.assertTrue(self.session.get(BroadFundEvidence,first['id']).active)
        restored=evidence.save(self.session,body)
        self.assertTrue(restored['active']);self.assertEqual(evidence.history(self.session,first['id'])['total'],3)

    def test_plan_and_holding_do_not_confirm_identity_or_leak_future_publications(self):
        evidence.save(self.session,self.body(kind='plan',codes=['510300.SH']))
        evidence.save(self.session,self.body(kind='holding',report_date=self.now.date()-timedelta(days=30)))
        self.assertEqual(evidence.listing(self.session,self.now.date()-timedelta(days=1))['total'],0)
        view=funds.summarize(self.batch(),self.now.date())
        self.assertTrue(all(row['buyer']=='未知' for row in view['members']))

    def test_evidence_scope_filtering_precedes_pagination(self):
        for index in range(12):evidence.save(self.session,self.body(title='market '+str(index)))
        evidence.save(self.session,self.body(title='specific',codes=['510300.SH']))
        selected=evidence.listing(self.session,self.now.date(),scope='510300.SH')
        self.assertEqual(selected['total'],1);self.assertEqual(selected['items'][0]['title'],'specific')
        self.assertEqual(evidence.listing(self.session,self.now.date(),scope='market')['total'],12)

    def test_read_only_views_never_call_tushare_or_model(self):
        batch=self.batch()
        with patch('app.services.tushare_client.requests.post') as post:
            funds.summarize(batch,self.now.date());funds.history(self.session,self.now.date(),'510300.SH',batch.id)
            evidence.listing(self.session,self.now.date())
        post.assert_not_called()

    def test_next_morning_waiting_is_not_overnight_failure(self):
        day=self.now.date();morning=(self.now+timedelta(days=1)).astimezone(funds.SH).replace(hour=9)
        self.assertEqual(missing_status(day,morning)[0],'waiting')
        self.assertEqual(missing_status(day,morning.replace(hour=11))[0],'overdue')

    def test_cron_preserves_other_jobs_and_is_idempotent(self):
        old='CRON_TZ=Asia/Shanghai\n0 16 * * 1-5 existing\n'
        revised=updated_crontab(old,'/project/backend','/project/venv/python')
        self.assertIn('existing',revised);self.assertIn('5 9,10 * * *',revised)
        self.assertEqual(updated_crontab(revised,'/project/backend','/project/venv/python'),revised)
        with self.assertRaises(ValueError):updated_crontab('# BEGIN stocks broad funds monitor\n','/x','/y')

    def test_new_routes_are_protected_and_future_request_rejected(self):
        from app.main import app
        from app.auth import require_auth
        from app.routers.broad_funds import dashboard
        from fastapi import HTTPException
        routes=[row for row in app.routes if row.path.startswith('/api/etfs/funds')]
        self.assertEqual(len(routes),7)
        self.assertTrue(all(any(dep.call==require_auth for dep in row.dependant.dependencies) for row in routes))
        with self.assertRaises(HTTPException) as caught:dashboard(target=date(2099,1,1),session=self.session)
        self.assertEqual(caught.exception.status_code,400)


if __name__=='__main__':unittest.main()
