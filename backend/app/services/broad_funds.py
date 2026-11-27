"""固定宽基篮子的成交/份额观察：金额用 Decimal，买方身份始终独立于市场数据。"""
import json
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from statistics import median

from sqlalchemy import func
from sqlmodel import select

from ..models import BroadFundBatch
from .runtime_state import utc_now
from .seat_disclosures import digest, dumps
from .short_term import SH, candidate, persist, preferences

BASKET = {
    '510300.SH': '沪深300', '510310.SH': '沪深300', '510330.SH': '沪深300', '159919.SZ': '沪深300',
    '510050.SH': '上证50', '510500.SH': '中证500', '159922.SZ': '中证500',
    '512100.SH': '中证1000', '159845.SZ': '中证1000', '560010.SH': '中证1000',
}
BASKET_VERSION = 'broad-v1-10'
METHOD = '份额净变动对应金额估算 =（当日份额 − 前一真实交易日份额）× 当日单位净值；份额统一为份，金额统一为元。'
LIMITATION = '固定观察篮子，不代表全部宽基 ETF。成交额不是净流入；份额变化可能包含实物申赎及套利，估算不是实测现金流，也不能识别买方身份。'


def dec(value, positive=False):
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and (number > 0 if positive else number >= 0) else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def text(value):
    return format(value, 'f') if value is not None else None


def iso(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def source_day(value):
    if not isinstance(value, str) or len(value) != 8 or not value.isdigit():
        raise ValueError('基金源日期格式异常')
    return date(int(value[:4]), int(value[4:6]), int(value[6:]))


def members_from(frame, end):
    required = {'ts_code', 'name', 'list_date', 'benchmark', 'status'}
    if frame is None or not required.issubset(frame.columns):
        raise ValueError('ETF 基础资料字段异常')
    members = []
    for code, group in BASKET.items():
        rows = frame[frame.ts_code == code].to_dict('records')
        if len(rows) != 1:
            raise ValueError('固定篮子基金身份缺失或重复：'+code)
        row = rows[0]
        if not isinstance(row['name'], str) or 'ETF' not in row['name'].upper() or row['status'] != 'L':
            raise ValueError('固定篮子基金状态异常：'+code)
        listed = source_day(row['list_date'])
        if listed > end:
            raise ValueError('观察日期早于基金上市，不推测历史篮子')
        members.append({'ts_code': code, 'code': code.split('.')[0], 'name': row['name'], 'group': group,
                        'benchmark': str(row.get('benchmark') or ''), 'listed': str(listed)})
    return members


def source_rows(frame, api, codes, first, last):
    fields = {'fund_daily': {'ts_code', 'trade_date', 'close', 'amount'},
              'fund_share': {'ts_code', 'trade_date', 'fd_share'},
              'fund_nav': {'ts_code', 'nav_date', 'ann_date', 'unit_nav'},
              'fund_adj': {'ts_code', 'trade_date', 'adj_factor'}}[api]
    if frame is None or (frame.empty and not len(frame.columns)):
        return []
    if not fields.issubset(frame.columns) or len(frame) >= 2000:
        raise ValueError(api+' 字段异常或达到截断上限，保留旧快照')
    output = []
    for row in frame.to_dict('records'):
        if row['ts_code'] not in codes:
            raise ValueError(api+' 返回了未请求的基金')
        day = source_day(row['nav_date'] if api == 'fund_nav' else row['trade_date'])
        if not first <= day <= last:
            raise ValueError(api+' 返回了区间外日期')
        output.append((row['ts_code'], str(day), row))
    return output


def collect(client, dates, now=None):
    """按基金区间取数，避免全市场单次截断；任一实际请求故障不发布半轮快照。"""
    now = now or utc_now()
    first, last = dates[0], dates[-1]
    members = members_from(client.fund_basic(market='E', fields='ts_code,name,benchmark,list_date,status'), last)
    records = {code: {} for code in BASKET}
    raw = {}; issues = []
    def accept(api, frame, codes):
        raw[api+'|'+','.join(codes)] = json.loads(frame.to_json(orient='records', force_ascii=False)) if frame is not None else []
        seen = defaultdict(list)
        for code, day, row in source_rows(frame, api, codes, first, last):
            if date.fromisoformat(day) not in dates:
                # 净值可以披露非交易日，不能据此拼接成交易日；交易日源则须严格匹配。
                if api == 'fund_nav':continue
                raise ValueError(api+' 返回非官方交易日')
            seen[(code, day)].append(row)
        for (code, day), values in seen.items():
            point = records[code].setdefault(day, {})
            if api == 'fund_nav':
                for row in values:source_day(row['ann_date'])
                values = [row for row in values if source_day(row['ann_date']) <= now.astimezone(SH).date()]
                if not values:
                    issues.append(code+' '+day+' 净值公告日期尚未到达');continue
                newest = max(row['ann_date'] for row in values)
                values = [row for row in values if row['ann_date'] == newest]
            normalized = []
            for row in values:
                if api == 'fund_daily':
                    item = {'close': text(dec(row['close'], True)), 'amount': text((dec(row['amount'])*1000) if dec(row['amount']) is not None else None)}
                elif api == 'fund_share':
                    share = dec(row['fd_share'], True)
                    item = {'shares': text(share*10000 if share is not None else None)}
                elif api == 'fund_adj':
                    item = {'factor': text(dec(row['adj_factor'], True))}
                else:
                    item = {'nav': text(dec(row['unit_nav'], True)), 'nav_ann_date': str(source_day(row['ann_date']))}
                normalized.append(item)
            variants = {dumps(item) for item in normalized}
            if len(variants) > 1:
                issues.append(code+' '+day+' '+api+' 重复记录有冲突，相关字段未知')
                point.update({key: None for key in normalized[0]})
            else:
                point.update(normalized[0])
                if any(value is None for value in normalized[0].values()):
                    issues.append(code+' '+day+' '+api+' 数值异常，相关字段未知')
    params = {'start_date': first.strftime('%Y%m%d'), 'end_date': last.strftime('%Y%m%d')}
    accept('fund_share', client.fund_share(ts_code=','.join(BASKET), **params), list(BASKET))
    for code in BASKET:
        for api in ('fund_daily', 'fund_nav', 'fund_adj'):
            fields = 'ts_code,nav_date,ann_date,unit_nav' if api == 'fund_nav' else ''
            frame = client.query(api, ts_code=code, fields=fields, **params)
            accept(api, frame, [code])
    return {'basket_version': BASKET_VERSION, 'members': members, 'dates': [str(day) for day in dates],
            'records': records, 'issues': issues}, raw


def save_batch(session, data, raw, now=None):
    now = (now or utc_now()).astimezone(timezone.utc).replace(tzinfo=None)
    if not any(point.get('close') for values in data['records'].values() for point in values.values()):
        return None, False
    checksum = digest(data)
    end = date.fromisoformat(data['dates'][-1])
    old = session.exec(select(BroadFundBatch).where(BroadFundBatch.end_date == end)
                       .order_by(BroadFundBatch.id.desc()).limit(1)).first()
    if old and old.digest == checksum:return old, False
    row = BroadFundBatch(start_date=date.fromisoformat(data['dates'][0]), end_date=end, digest=checksum,
        data_json=dumps(data), raw_json=dumps(raw), fetched_at=now)
    session.add(row);session.commit();session.refresh(row)
    return row, True


def point_view(data, code, day):
    dates, records = data['dates'], data['records'].get(code, {})
    current = records.get(day, {})
    position = dates.index(day)
    prior = records.get(dates[position-1], {}) if position else {}
    missing = []
    change = estimate = delta = ratio = None
    close, old_close = dec(current.get('close'), True), dec(prior.get('close'), True)
    factor, old_factor = dec(current.get('factor'), True), dec(prior.get('factor'), True)
    if all(value is not None for value in (close, old_close, factor, old_factor)):
        change = (close*factor/(old_close*old_factor)-1)*100
    amount = dec(current.get('amount'))
    earlier = [dec(records.get(value, {}).get('amount')) for value in dates[max(0,position-20):position]]
    baseline = median(earlier) if len(earlier) == 20 and all(value is not None for value in earlier) else None
    if amount is not None and baseline is not None and baseline > 0:ratio = amount/baseline
    shares, old_shares, nav = dec(current.get('shares'), True), dec(prior.get('shares'), True), dec(current.get('nav'), True)
    if shares is None or old_shares is None:missing.append('相邻真实交易日份额缺失或异常')
    else:delta = shares-old_shares
    if nav is None:missing.append('同日单位净值缺失或异常，不能用成交价代替')
    if factor is None or old_factor is None:missing.append('相邻复权因子缺失，不能排除折算口径变化')
    elif factor != old_factor:missing.append('复权因子发生变化，分红或折算期间暂不估算申赎')
    if not missing:estimate = delta*nav
    return {'date': day, 'close': current.get('close'), 'amount': text(amount), 'change_pct': text(change),
        'amount_baseline': text(baseline), 'amount_multiple': text(ratio),
        'amount_spike': bool(ratio is not None and ratio >= 2 and amount >= 100000000),
        'shares': current.get('shares'), 'share_delta': text(delta), 'nav': current.get('nav'),
        'prior_date': dates[position-1] if position else None, 'prior_shares': prior.get('shares'),
        'factor': current.get('factor'), 'prior_factor': prior.get('factor'),
        'nav_ann_date': current.get('nav_ann_date'), 'estimate': text(estimate), 'missing': missing}


def summarize(batch, target):
    data = json.loads(batch.data_json)
    dates = [value for value in data['dates'] if value <= str(target)]
    if not dates:return None
    # 每个渠道各选最新有真实样本的交易日，整列固定同一天，不逐基金拼接不同日期。
    market_day = next((day for day in reversed(dates) if any(data['records'].get(code, {}).get(day, {}).get('close') for code in BASKET)), None)
    flow_day = next((day for day in reversed(dates) if any(point_view(data, code, day)['estimate'] is not None for code in BASKET)), None)
    rows = []
    for member in data['members']:
        market = point_view(data, member['ts_code'], market_day) if market_day else None
        flow = point_view(data, member['ts_code'], flow_day) if flow_day else None
        rows.append({**member, 'market': market, 'flow': flow, 'buyer': '未知'})
    groups = []
    for group in dict.fromkeys(BASKET.values()):
        selected = [row for row in rows if row['group'] == group]
        estimates = [Decimal(row['flow']['estimate']) for row in selected if row['flow'] and row['flow']['estimate'] is not None]
        streak = 0; streak_ready = False
        if flow_day:
            end = dates.index(flow_day)
            last_three = dates[max(0,end-2):end+1]
            streak_ready = len(last_three)==3 and all(point_view(data,row['ts_code'],day)['estimate'] is not None
                for day in last_three for row in selected)
            for day in reversed(dates[max(0,end-4):end+1]):
                amounts = [point_view(data, row['ts_code'], day)['estimate'] for row in selected]
                if any(value is None for value in amounts) or sum(map(Decimal, amounts)) <= 0:break
                streak += 1
        groups.append({'name': group, 'funds': len(selected), 'flow_valid': len(estimates),
            'estimate': text(sum(estimates, Decimal(0))) if len(estimates) == len(selected) else None,
            'positive_days': streak, 'streak_ready': streak_ready,
            'spikes': sum(bool(row['market'] and row['market']['amount_spike']) for row in selected)})
    covered = sum(bool(row['flow'] and row['flow']['estimate'] is not None) for row in rows)
    market_covered = sum(bool(row['market'] and row['market']['close']) for row in rows)
    total = sum((Decimal(row['flow']['estimate']) for row in rows if row['flow'] and row['flow']['estimate'] is not None), Decimal(0)) if covered == len(rows) else None
    latest = dates[-1]
    # 份额/净值可晚于行情，不能把行情就绪当作申赎资料已齐备。
    source_ready = all(all(data['records'].get(code, {}).get(latest, {}).get(key) is not None for key in ('close','amount','shares','nav','factor'))
        and len(dates)>1 and all(data['records'].get(code, {}).get(dates[-2], {}).get(key) is not None for key in ('shares','factor')) for code in BASKET)
    return {'requested_date': str(target), 'calendar_end': latest, 'market_date': market_day, 'flow_date': flow_day,
        'batch_id': batch.id, 'fetched_at': iso(batch.fetched_at), 'basket_version': data['basket_version'],
        'members': rows, 'groups': groups, 'market_valid': market_covered, 'flow_valid': covered, 'total': len(rows),
        'estimate': text(total), 'spikes': sum(bool(row['market'] and row['market']['amount_spike']) for row in rows),
        'spike_groups': sum(row['spikes']>0 for row in groups), 'source_ready': source_ready,
        'issues': data['issues'], 'method': METHOD, 'limitation': LIMITATION,
        'note': '份额及净值常在收盘后或次日补齐。历史数据按所选日截断，采集时间另列；固定篮子与后补资料不作当时已知的回测依据。'}


def find_batch(session, target):
    return session.exec(select(BroadFundBatch).where(BroadFundBatch.start_date <= target)
        .order_by(BroadFundBatch.end_date.desc(), BroadFundBatch.id.desc()).limit(1)).first()


def history(session, target, code, batch_id=None):
    batch = session.get(BroadFundBatch, batch_id) if batch_id else find_batch(session, target)
    if not batch or batch.start_date > target or code not in BASKET:return None
    data = json.loads(batch.data_json)
    dates = [day for day in data['dates'] if day <= str(target)][-20:]
    return {'code': code, 'batch_id': batch.id, 'fetched_at': iso(batch.fetched_at),
        'items': [point_view(data, code, day) for day in reversed(dates)], 'method': METHOD, 'limitation': LIMITATION}


def publish_events(session, batch, notify=False, now=None):
    view = summarize(batch, batch.end_date)
    evaluations = []
    if view['market_date'] == str(batch.end_date) and all(row['market'] and row['market']['amount_multiple'] is not None for row in view['members']):
        hit = view['spikes'] >= 3 and view['spike_groups'] >= 2
        item = candidate(batch.end_date, 'close', 'broad_volume_sync', 'broad-basket', '宽基 ETF 多方向同步放量',
            2 if view['spikes']>=5 else 1, str(view['spikes']), '3',
            '固定篮子至少 3 只、跨 2 个指数方向：成交额 ≥ 前20真实交易日中位数的2倍且 ≥ 1亿元；不识别买方身份。',
            iso(batch.fetched_at), category='etf', triggered=hit, unit='只')
        item['snapshot'].update(batch_id=batch.id, limitation=LIMITATION)
        evaluations.append(item)
    if view['flow_date'] == str(batch.end_date):
        for group in view['groups']:
            if group['estimate'] is None or not group['streak_ready']:continue
            item = candidate(batch.end_date, 'close', 'broad_flow_streak', group['name'], group['name']+'观察篮子连续份额净增加',
                2 if Decimal(group['estimate'])>=1000000000 else 1, group['estimate'], '0',
                '该方向固定篮子连续3个真实交易日估算净增加，且本日 ≥ 5000万元；份额、净值及因子齐备，不代表国家队买入。',
                iso(batch.fetched_at), category='etf', triggered=group['positive_days']>=3 and Decimal(group['estimate'])>=50000000, unit='元')
            item['snapshot'].update(batch_id=batch.id, limitation=LIMITATION)
            evaluations.append(item)
    return persist(session, evaluations, now=now, notify=notify and preferences().enabled) if evaluations else 0
