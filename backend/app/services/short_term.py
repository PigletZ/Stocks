"""确定性异动规则和不可变触发快照；仅使用截止时点的本地资料。"""
import hashlib
import json
import math
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from statistics import median

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func
from sqlmodel import select

from ..models import (LimitUpDaily, MarketDailyStat, ReviewObservation, SectorDaily, ShortTermEvent,
                      ShortTermEventState, ShortTermMinute, Stock, StockDailyQuote, WatchlistItem)
from .etf_service import EtfService
from .price_basis import load_stock_factors, positive_decimal, price_change
from .review_records import observation_query
from .runtime_state import RuntimeStore, utc_now

SH = timezone(timedelta(hours=8))


class ShortTermSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = True
    max_stocks: int = Field(default=100, ge=1, le=200, strict=True)
    move_5m_pct: Decimal = Field(default=Decimal('2'), gt=0, le=20)
    critical_5m_pct: Decimal = Field(default=Decimal('4'), gt=0, le=30)
    minute_amount_multiple: Decimal = Field(default=Decimal('3'), gt=1, le=20)
    minute_amount_floor: Decimal = Field(default=Decimal('10000000'), ge=0, le=1000000000)
    daily_move_pct: Decimal = Field(default=Decimal('5'), gt=0, le=50)
    daily_amount_multiple: Decimal = Field(default=Decimal('2'), gt=1, le=20)

    @model_validator(mode='after')
    def consistent(self):
        if self.critical_5m_pct <= self.move_5m_pct:
            raise ValueError('明显异动阈值须高于普通阈值')
        return self


def preferences(store=None):
    value = (store or RuntimeStore()).read('short-term-preferences')
    try:
        return ShortTermSettings.model_validate(value['values']) if value else ShortTermSettings()
    except (ValueError, KeyError, TypeError):
        return ShortTermSettings()


def iso(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def event_key(day, mode, kind, subject):
    return hashlib.sha256(f'{day}|{mode}|{kind}|{subject}'.encode()).hexdigest()


def current_events(session, day, mode):
    ids = select(func.max(ShortTermEvent.id)).where(ShortTermEvent.business_date == day,
        ShortTermEvent.mode == mode).group_by(ShortTermEvent.event_key)
    return session.exec(select(ShortTermEvent).where(ShortTermEvent.id.in_(ids))).all()


def pool(session, day):
    """自选按现有清单、关注按所属日期核对；把范围说明保存在触发快照。"""
    observations = session.exec(observation_query(day, 'pending')).all()
    refs = {}
    for row in observations:
        refs.setdefault(row.stock_code, []).append({'id': row.id, 'date': str(row.observation_date), 'reason': row.reason[:200]})
    watches = session.exec(select(WatchlistItem.stock_code).where(
        WatchlistItem.created_at < datetime.combine(day+timedelta(days=1), time.min)-timedelta(hours=8))).all()
    codes = sorted(refs) + sorted(set(watches)-set(refs))
    names = {}
    for offset in range(0, len(codes), 200):
        names.update(dict(session.exec(select(Stock.code, Stock.name).where(Stock.code.in_(codes[offset:offset+200]))).all()))
    return codes, refs, names


def candidate(day, mode, kind, subject, title, level, actual, baseline, rule, observed_at,
              category='stock', triggered=True, refs=None, unit='%', name=None):
    return {'key': event_key(day, mode, kind, subject), 'day': day, 'mode': mode, 'kind': kind,
        'subject': subject, 'category': category, 'title': title, 'level': level, 'active': triggered,
        'snapshot': {'actual': actual, 'baseline': baseline, 'unit': unit, 'rule': rule,
            'observed_at': observed_at, 'source': 'Tushare / 本地已校验缓存', 'name': name,
            'observations': refs or [], 'scope_note': '自选使用扫描时的现有清单；关注按所属日期筛选，不作历史选股回测。'}}


def persist(session, evaluations, now=None, notify=True):
    now = (now or utc_now()).astimezone(timezone.utc).replace(tzinfo=None)
    groups = {(row['day'], row['mode']) for row in evaluations}
    previous = {row.event_key: row for day, mode in groups for row in current_events(session, day, mode)}
    written = 0
    for item in evaluations:
        old = previous.get(item['key'])
        if not old and not item['active']:
            continue
        snapshot = json.dumps(item['snapshot'], ensure_ascii=False, sort_keys=True, default=str, allow_nan=False)
        if old and old.active == item['active'] and old.level == item['level']:
            if item['mode'] == 'intraday' or old.snapshot_json == snapshot:
                continue
        cycle = old.cycle + int(not old.active and item['active']) if old else 1
        due = old.notify_after if old and cycle == old.cycle else max(now, old.notify_after+timedelta(minutes=15)) if old else now
        row = ShortTermEvent(event_key=item['key'], business_date=item['day'], mode=item['mode'], category=item['category'],
            subject=item['subject'], kind=item['kind'], title=item['title'], level=item['level'], cycle=cycle,
            active=item['active'], notify=notify, notify_after=due, snapshot_json=snapshot, detected_at=now)
        session.add(row)
        previous[item['key']] = row
        written += 1
    session.commit()
    return written


def minute_phase(etf=None, now=None):
    now = (now or utc_now()).astimezone(SH)
    calendar = (etf or EtfService()).cached_trade_dates(now.date(), now.date())
    if calendar is None:
        return 'unknown', None
    if now.date() not in calendar[0]:
        return 'holiday', None
    clock = now.time().replace(tzinfo=None)
    if time(9, 31) <= clock < time(11, 31) or time(13, 1) <= clock < time(15, 1):
        return 'trading', now.replace(second=0, microsecond=0)
    if time(15,1)<=clock<time(15,2):
        return 'closing',now.replace(hour=15,minute=0,second=0,microsecond=0)
    return ('before_open' if clock < time(9, 31) else 'break' if clock < time(13, 1) else 'closed'), None


def same_session(values, end, count):
    times = [end-timedelta(minutes=i) for i in range(count)]
    local = [value.replace(tzinfo=timezone.utc).astimezone(SH).time().replace(tzinfo=None) for value in times]
    allowed = all(time(9,31) <= t <= time(11,30) for t in local) or all(time(13,1) <= t <= time(15,0) for t in local)
    return allowed and all(stamp in values for stamp in times)


def minute_signals(code, name, rows, now, config, refs=None):
    output = []
    cutoff=now.astimezone(timezone.utc).replace(tzinfo=None)
    values = {row.bar_time: row for row in rows if row.bar_time<=cutoff}
    end = max(values, default=None)
    if end is None:
        return output, {'move_ready': False, 'amount_ready': False}
    if cutoff-end>timedelta(seconds=120):
        return output, {'move_ready':False,'amount_ready':False}
    local = end.replace(tzinfo=timezone.utc).astimezone(SH)
    move_ready = same_session(values, end, 6)
    if move_ready:
        change = price_change(values[end-timedelta(minutes=5)].close, values[end].close, basis='raw')
        if change is not None:
            output.append(candidate(local.date(), 'intraday', 'move_5m', code, f'{name} 5 分钟价格异动',
                2 if abs(change) >= config.critical_5m_pct else 1, str(change), '0',
                f'连续 5 分钟价格变化绝对值 ≥ {config.move_5m_pct}%；明显异动 ≥ {config.critical_5m_pct}%', iso(end),
                triggered=abs(change) >= config.move_5m_pct, refs=refs, name=name))
    amount_ready = same_session(values, end, 21)
    if amount_ready:
        amounts = [positive_decimal(values[end-timedelta(minutes=i)].amount) for i in range(1, 21)]
        current = positive_decimal(values[end].amount)
        if all(amount is not None for amount in amounts) and current is not None:
            base = median(amounts)
            ratio = current/base
            output.append(candidate(local.date(), 'intraday', 'minute_amount', code, f'{name} 分钟成交额放大',
                2 if ratio >= config.minute_amount_multiple*2 else 1, str(ratio), '1',
                f'本分钟成交额 / 前 20 个连续分钟中位数 ≥ {config.minute_amount_multiple}，且本分钟 ≥ {config.minute_amount_floor} 元',
                iso(end), triggered=ratio >= config.minute_amount_multiple and current >= config.minute_amount_floor,
                refs=refs, name=name, unit='倍'))
        else:
            amount_ready = False
    return output, {'move_ready': move_ready, 'amount_ready': amount_ready}


def close_signals(session, day, config=None, etf=None):
    config, etf = config or preferences(), etf or EtfService()
    calendar = etf.cached_trade_dates(day-timedelta(days=100), day)
    if not calendar or day not in calendar[0] or calendar[0].index(day) == 0:
        return [], {'status': 'unknown', 'message': '官方日历不足，未检测收盘异动。'}
    dates = calendar[0]; index = dates.index(day); prior_day = dates[index-1]
    history_days = dates[max(0,index-20):index]
    observed = datetime.combine(day, time(15)).replace(tzinfo=SH).astimezone(timezone.utc).replace(tzinfo=None)
    observed_at = iso(observed)
    stats = {row.stat_date: row for row in session.exec(select(MarketDailyStat).where(MarketDailyStat.stat_date.in_(history_days+[day]))).all()}
    limits = session.exec(select(LimitUpDaily).where(LimitUpDaily.trade_date.in_(history_days+[day]))).all()
    by_day = {}
    for row in limits: by_day.setdefault(row.trade_date, []).append(row)
    def valid(d):
        stat = stats.get(d)
        return stat and stat.total > 0 and stat.total_turnover > 0 and stat.up+stat.down+stat.flat == stat.total and all(
            sum(row.limit_type == kind for row in by_day.get(d, [])) == n for kind,n in [('U',stat.limit_up),('D',stat.limit_down),('Z',stat.opened_limit)])
    output = []
    baseline = [stats[d] for d in history_days if valid(d)]
    market_ready = bool(valid(day))
    if market_ready and len(baseline) >= 10:
        current = stats[day]
        rates = [Decimal(row.opened_limit)*100/(row.limit_up+row.opened_limit) for row in baseline if row.limit_up+row.opened_limit > 0]
        if len(rates) >= 10 and current.limit_up+current.opened_limit > 0:
            rate = Decimal(current.opened_limit)*100/(current.limit_up+current.opened_limit)
            base = median(rates); delta = rate-base
            output.append(candidate(day,'close','break_rate','market','市场炸板率明显上升',2 if delta>=25 else 1,
                str(rate),str(base),f'较前 {len(rates)} 个有效交易日中位数上升 ≥ 15 个百分点；25 个百分点为明显异动',observed_at,
                category='market',triggered=delta>=15,unit='%'))
        base = Decimal(str(median([row.limit_down for row in baseline])))
        threshold = max(Decimal(10), base*2)
        output.append(candidate(day,'close','limit_down','market','市场跌停家数增加',
            2 if current.limit_down >= max(20,base*3) else 1,str(current.limit_down),str(base),
            f'跌停家数 ≥ max(10, 近期 {len(baseline)} 个有效交易日中位数 × 2)',observed_at,
            category='market',triggered=current.limit_down>=threshold,unit='家'))
        up_base=Decimal(str(median([row.limit_up for row in baseline])))
        output.append(candidate(day,'close','limit_up_drop','market','市场涨停家数收缩',2 if current.limit_up<=up_base*Decimal('.3') else 1,
            str(current.limit_up),str(up_base),'近期有效样本的涨停中位数 ≥ 20，当前家数 ≤ 其中位数的 50%',observed_at,
            category='market',triggered=up_base>=20 and current.limit_up<=up_base*Decimal('.5'),unit='家'))
    def promotion(d):
        position=dates.index(d)
        if position==0:return None
        earlier=dates[position-1]
        if not valid(d) or not valid(earlier):return None
        old_codes={row.stock_code for row in by_day.get(earlier,[]) if row.limit_type=='U'}
        new_codes={row.stock_code for row in by_day.get(d,[]) if row.limit_type=='U'}
        return Decimal(len(old_codes & new_codes))*100/len(old_codes) if len(old_codes)>=10 else None
    promote=promotion(day)
    promo_baseline=[value for value in (promotion(d) for d in history_days) if value is not None]
    if promote is not None and len(promo_baseline)>=10:
        base=median(promo_baseline);drop=base-promote
        output.append(candidate(day,'close','promotion_drop','market','涨停延续率下降',2 if drop>=30 else 1,
            str(promote),str(base),f'对比日前次涨停至少 10 家，延续率较前 {len(promo_baseline)} 个有效样本中位数下降 ≥ 20 个百分点',
            observed_at,category='market',triggered=drop>=20,unit='%'))
    if market_ready and valid(prior_day):
        def height(d):
            rows = [row for row in by_day.get(d,[]) if row.limit_type=='U']
            return max((row.limit_times for row in rows),default=0) if all(row.limit_times and row.limit_times>0 for row in rows) else None
        old,new = height(prior_day),height(day)
        if old is not None and new is not None:
            output.append(candidate(day,'close','height_drop','market','最高连板高度回落',2 if old-new>=3 else 1,
                str(new),str(old),'前一真实交易日最高连板 ≥ 4，当前高度较此前下降 ≥ 2 板',observed_at,
                category='market',triggered=old>=4 and old-new>=2,unit='板'))
    # 板块仅比较相同代码的可比排名，防止统计范围变化制造排名异动。
    sectors = session.exec(select(SectorDaily).where(SectorDaily.trade_date.in_([prior_day,day]))).all()
    sector_ready = 0
    for kind in ('industry','concept'):
        groups = {d:{r.sector_code:r for r in sectors if r.trade_date==d and r.sector_type==kind} for d in (prior_day,day)}
        if any(not math.isfinite(row.change_pct) for rows in groups.values() for row in rows.values()):continue
        common = set(groups[day]) & set(groups[prior_day])
        if len(common)<20 or len(common)<max(len(groups[day]),len(groups[prior_day]))*.85: continue
        sector_ready += 1
        ranks = {d:{code:n+1 for n,code in enumerate(sorted(common,key=lambda code:(-groups[d][code].change_pct,code)))} for d in (prior_day,day)}
        for code in common:
            row=groups[day][code];jump=ranks[prior_day][code]-ranks[day][code]
            output.append(candidate(day,'close','sector_jump',kind+':'+code,f'{row.sector_name} 排名跃升',2 if row.change_pct>=4 else 1,
                str(ranks[day][code]),str(ranks[prior_day][code]),f'{len(common)} 个可比板块中排名上升 ≥ {max(10,int(len(common)*.15))}，进入前 {max(5,int(len(common)*.05))}，涨幅 ≥ 2%',
                observed_at,category='sector',triggered=jump>=max(10,int(len(common)*.15)) and ranks[day][code]<=max(5,int(len(common)*.05)) and row.change_pct>=2,unit='名',name=row.sector_name))
    codes,refs,names = pool(session,day)
    quotes = {}
    for offset in range(0,len(codes),200):
        rows=session.exec(select(StockDailyQuote).where(StockDailyQuote.stock_code.in_(codes[offset:offset+200]),StockDailyQuote.trade_date.in_(history_days+[day]))).all()
        quotes.update({(r.stock_code,r.trade_date):r for r in rows})
    factors=load_stock_factors(session,codes,history_days[0],day,dates=[prior_day,day]) if codes else {}
    valid_prices=0
    for code in codes:
        current,old=quotes.get((code,day)),quotes.get((code,prior_day))
        change=price_change(old.close if old else None,current.close if current else None,factors.get((code,prior_day)),factors.get((code,day)))
        name=names.get(code,code)
        if change is not None:
            valid_prices+=1
            output.append(candidate(day,'close','daily_move',code,f'{name} 收盘价格异动',2 if abs(change)>=config.daily_move_pct*Decimal('1.6') else 1,
                str(change),'0',f'相邻真实交易日复权变化绝对值 ≥ {config.daily_move_pct}%',observed_at,triggered=abs(change)>=config.daily_move_pct,refs=refs.get(code),name=name))
            was_up=any(row.stock_code==code and row.limit_type=='U' for row in by_day.get(prior_day,[]))
            output.append(candidate(day,'close','after_limit_weak',code,f'{name} 前次涨停后走弱',2 if change<=-6 else 1,str(change),'0',
                '前一真实交易日涨停，当前复权变化 ≤ -3%',observed_at,triggered=was_up and change<=-3,refs=refs.get(code),name=name))
        amounts=[positive_decimal(quotes[(code,d)].amount) for d in history_days if (code,d) in quotes]
        amounts=[value for value in amounts if value is not None]
        amount=positive_decimal(current.amount) if current else None
        if len(amounts)>=10 and amount:
            base=sum(amounts)/len(amounts);ratio=amount/base
            output.append(candidate(day,'close','daily_amount',code,f'{name} 收盘成交额放大',2 if ratio>=config.daily_amount_multiple*2 else 1,
                str(ratio),'1',f'同口径成交额 / 前 {len(amounts)} 个有效交易日均值 ≥ {config.daily_amount_multiple}，且当日成交额 ≥ 1000 万元',observed_at,
                triggered=ratio>=config.daily_amount_multiple and amount>=10000000,refs=refs.get(code),name=name,unit='倍'))
    return output, {'status':'ready' if market_ready else 'partial','market_ready':market_ready,'baseline_days':len(baseline),
        'sector_types_ready':sector_ready,'stock_pool':len(codes),'price_pairs':valid_prices,'date':str(day),
        'message':'缺少所需报价、因子、日历或可比样本时不触发；已确认的历史触发快照继续保留。'}


def event_view(row, state=None, now=None):
    now=(now or utc_now()).astimezone(timezone.utc).replace(tzinfo=None)
    ignored=bool(state and state.action=='ignore')
    read=bool(state and (ignored or state.action=='read' and state.level>=row.level))
    return {'id':row.id,'key':row.event_key,'date':str(row.business_date),'mode':row.mode,'category':row.category,
        'subject':row.subject,'kind':row.kind,'title':row.title,'level':row.level,'cycle':row.cycle,'active':row.active,
        'snapshot':json.loads(row.snapshot_json),'detected_at':iso(row.detected_at),'unread':row.active and row.notify and not read and row.notify_after<=now,
        'ignored':ignored,'cooling':row.active and row.notify_after>now,'notify':row.notify}
