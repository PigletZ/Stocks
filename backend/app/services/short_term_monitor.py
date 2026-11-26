"""后台分钟采样与收盘扫描。无实时日线权限时只监测自选/关注池。"""
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation

import pandas as pd
from sqlalchemy import delete, func
from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session, select

from ..config import settings
from ..database import engine
from ..models import MarketDailyStat, ShortTermMinute, Stock
from .etf_service import EtfService
from .job_monitor import record_progress, tracked_job
from .runtime_state import RuntimeStore, redact, utc_now
from .short_term import (SH, close_signals, iso, minute_phase, minute_signals, persist,
                         pool, preferences, same_session)
from .tushare_client import TushareClient


def normalize_minutes(frame, requested, now):
    if not isinstance(frame,pd.DataFrame) or frame.empty:
        return []
    if not {'ts_code','time','close','amount'}.issubset(frame.columns):
        raise ValueError('分钟行情字段不完整')
    current=now.astimezone(SH)
    result={}
    for row in frame.to_dict('records'):
        code=str(row['ts_code'])
        if code not in requested or ('freq' in row and str(row['freq']).upper()!='1MIN'):
            raise ValueError('分钟行情证券或周期不匹配')
        stamp=datetime.fromisoformat(str(row['time']))
        stamp=stamp.replace(tzinfo=SH) if stamp.tzinfo is None else stamp.astimezone(SH)
        if stamp.date()!=current.date() or stamp.second or stamp.microsecond or stamp>current.replace(second=0,microsecond=0):
            raise ValueError('分钟行情日期错误或尚未闭合')
        if not (time(9,31)<=stamp.time().replace(tzinfo=None)<=time(11,30) or time(13,1)<=stamp.time().replace(tzinfo=None)<=time(15)):
            raise ValueError('分钟行情不在连续交易时段')
        utc=stamp.astimezone(timezone.utc).replace(tzinfo=None)
        try:
            close,amount=Decimal(str(row['close'])),Decimal(str(row['amount']))
            if not close.is_finite() or close<=0 or not amount.is_finite() or amount<0:
                raise ValueError('分钟价格或成交额无效')
        except InvalidOperation:
            raise ValueError('分钟数值无效') from None
        key=(code.split('.')[0],utc)
        value={'stock_code':key[0],'bar_time':utc,'close':str(close),'amount':str(amount)}
        if key in result and result[key]!=value:
            raise ValueError('分钟行情重复且冲突')
        result[key]=value
    return list(result.values())


def scan_intraday(session, client=None, etf=None, store=None, now=None):
    store,etf,now=store or RuntimeStore(),etf or EtfService(),now or utc_now()
    phase,expected=minute_phase(etf,now)
    config=preferences(store)
    if not config.enabled or phase not in ('trading','closing'):
        return {'status':'skipped','phase':phase,'message':'监控已关闭或当前不在连续交易时段。','written':0}
    day=now.astimezone(SH).date()
    codes,refs,names=pool(session,day)
    selected=codes[:config.max_stocks]
    identities={row.code:row.exchange for row in session.exec(select(Stock).where(Stock.code.in_(selected))).all()}
    client=client or TushareClient(settings.tushare_token)
    valid_codes=set();errors=[];written=0;latest=None
    for offset in range(0,len(selected),50):
        batch=selected[offset:offset+50]
        requested={code+'.'+identities[code] for code in batch if code in identities}
        if not requested:continue
        try:
            frame=client.query('rt_min',ts_code=','.join(sorted(requested)),freq='1MIN')
            rows=normalize_minutes(frame,requested,now)
            fresh=[row for row in rows if timedelta(0)<=now.astimezone(timezone.utc).replace(tzinfo=None)-row['bar_time']<=timedelta(seconds=120)]
            if fresh:
                statement=insert(ShortTermMinute).values(fresh)
                session.exec(statement.on_conflict_do_update(index_elements=['stock_code','bar_time'],
                    set_={'close':statement.excluded.close,'amount':statement.excluded.amount}))
                session.commit()
            for row in fresh:
                valid_codes.add(row['stock_code'])
                latest=max(latest,row['bar_time']) if latest else row['bar_time']
            if len(fresh)<len(requested):errors.append('部分分钟样本缺失或超过两分钟，未使用旧行情触发新事件。')
        except (RuntimeError,ValueError,TypeError) as error:
            session.rollback();errors.append(redact(str(error)))
            break  # 权限、限流或故障时不继续压测接口。
    evaluations=[];move_ready=0;amount_ready=0
    start=datetime.combine(day,time.min)-timedelta(hours=8)
    rows=session.exec(select(ShortTermMinute).where(ShortTermMinute.stock_code.in_(selected),ShortTermMinute.bar_time>=start,
        ShortTermMinute.bar_time<=now.astimezone(timezone.utc).replace(tzinfo=None))).all()
    grouped={}
    for row in rows:grouped.setdefault(row.stock_code,[]).append(row)
    for code in sorted(valid_codes):
        items,coverage=minute_signals(code,names.get(code,code),grouped.get(code,[]),now,config,refs.get(code))
        evaluations.extend(items);move_ready+=int(coverage['move_ready']);amount_ready+=int(coverage['amount_ready'])
    if evaluations:written=persist(session,evaluations,now)
    session.exec(delete(ShortTermMinute).where(ShortTermMinute.bar_time<start-timedelta(days=14)))
    session.commit()
    report={'status':'ready' if not errors and len(valid_codes)==len(selected) else 'partial', 'date':str(day),'phase':phase,
        'checked_at':now.isoformat(),'latest_bar_time':iso(latest),'pool':len(codes),'monitored':len(selected),
        'fresh':len(valid_codes),'move_ready':move_ready,'amount_ready':amount_ready,'limited':len(codes)-len(selected),
        'errors':errors[:3],'written':written,'message':'5 分钟变化需连续 6 条分钟；放量需连续 21 条分钟。午休和缺失不拼接，不自动回补无权限的历史分钟。'}
    store.write('short-term-intraday',report)
    return report


def scan_close(session, day=None, store=None, now=None, notify=True):
    store,now=store or RuntimeStore(),now or utc_now()
    local=now.astimezone(SH)
    # 收盘扫描不使用盘中当天未闭合的资料。
    cutoff=local.date() if local.hour>=15 else local.date()-timedelta(days=1)
    latest=session.exec(select(func.max(MarketDailyStat.stat_date)).where(MarketDailyStat.stat_date<=cutoff)).one()
    target=day or latest
    if target is None or target>cutoff:return {'status':'unknown','written':0,'message':'尚无所需收盘资料。'}
    evaluations,coverage=close_signals(session,target,preferences(store))
    written=persist(session,evaluations,now,notify=notify and target==latest) if evaluations else 0
    report={**coverage,'checked_at':now.isoformat(),'written':written}
    store.write('short-term-close-'+target.strftime('%Y%m%d'),report)
    return report


@tracked_job('short-term')
def run(mode='auto', history_days=1):
    config=preferences()
    if not config.enabled:
        record_progress(skipped=1,confirmed_skip=True,message='短线异动监控已关闭');return
    with Session(engine) as session:
        if mode in ('auto','intraday'):
            report=scan_intraday(session)
            record_progress(succeeded=int(report.get('status')=='ready'),deferred=int(report.get('status')=='partial'),
                skipped=int(report.get('status')=='skipped'),confirmed_skip=report.get('status')=='skipped',
                written_rows=report.get('written',0),message=report.get('message','分钟扫描已结束'))
        if mode in ('auto','close'):
            now=utc_now().astimezone(SH);cutoff=now.date() if now.hour>=15 else now.date()-timedelta(days=1)
            days=session.exec(select(MarketDailyStat.stat_date).where(MarketDailyStat.stat_date<=cutoff)
                .order_by(MarketDailyStat.stat_date.desc()).limit(history_days)).all()
            for day in sorted(days):
                report=scan_close(session,day,notify=day==days[0])
                record_progress(succeeded=int(report.get('status')=='ready'),deferred=int(report.get('status')!='ready'),
                    written_rows=report.get('written',0),message=report.get('message','收盘扫描已结束'))
