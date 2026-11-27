"""游资动向：页面只读本地披露快照；关注、证据与提醒复用既有复盘流程。"""
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlmodel import select

from ..models import HotMoneyCatalog, SeatDisclosureBatch, SeatFollow, LimitUpDaily, Stock
from .etf_service import EtfService
from .runtime_state import utc_now
from .seat_disclosures import (LIMITATION, METHOD, build_payload, catalog_entries, digest, dumps,
                               seat_records, top_records)
from .short_term import SH, candidate, persist, pool


def iso(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def latest_batch(session, day):
    return session.exec(select(SeatDisclosureBatch).where(SeatDisclosureBatch.trade_date == day)
                        .order_by(SeatDisclosureBatch.id.desc()).limit(1)).first()


def load_window(session, day, size=20):
    calendar = EtfService().cached_trade_dates(day-timedelta(days=100), day)
    dates = calendar[0][-size:] if calendar else []
    start = dates[0] if dates else day-timedelta(days=60)
    ids = select(func.max(SeatDisclosureBatch.id)).where(SeatDisclosureBatch.trade_date >= start,
        SeatDisclosureBatch.trade_date <= day).group_by(SeatDisclosureBatch.trade_date)
    batches = session.exec(select(SeatDisclosureBatch).where(SeatDisclosureBatch.id.in_(ids))
        .order_by(SeatDisclosureBatch.trade_date.desc()).limit(size)).all()
    if dates:
        batches = [row for row in batches if row.trade_date in dates]
    return batches, {'calendar_known': bool(calendar), 'expected_dates': [str(d) for d in dates],
        'cached_dates': [str(row.trade_date) for row in reversed(batches)],
        'complete': len(dates) == size and set(dates) == {row.trade_date for row in batches}
            and all(json.loads(row.payload_json)['quality']['warnings'] == 0 for row in batches)}


def follows(session):
    ids = select(func.max(SeatFollow.id)).group_by(SeatFollow.kind, SeatFollow.subject)
    rows = session.exec(select(SeatFollow).where(SeatFollow.id.in_(ids), SeatFollow.active == True)).all()
    return sorted([{'kind': row.kind, 'subject': row.subject, 'created_at': iso(row.created_at)} for row in rows],
                  key=lambda row: (row['kind'], row['subject']))


def follow_match(report, following):
    keys = {(row['kind'], row['subject']) for row in following}
    return any(('seat', seat['seat']) in keys or
               (seat['association'] == 'catalog' and any(('person', name) in keys for name in seat['names']))
               for seat in report['seats'])


def save_follow(session, kind, subject, active):
    old = session.exec(select(SeatFollow).where(SeatFollow.kind == kind, SeatFollow.subject == subject)
        .order_by(SeatFollow.id.desc()).limit(1)).first()
    if old and old.active == active:
        return follows(session)
    # 只允许关注实际采集到的对象；不允许通过任意文字形成伪游资关联。
    if active:
        if kind == 'person':
            catalog = session.exec(select(HotMoneyCatalog).order_by(HotMoneyCatalog.id.desc()).limit(1)).first()
            known = catalog and any(row['name'] == subject for row in json.loads(catalog.entries_json))
        else:
            recent, _ = load_window(session, utc_now().astimezone(SH).date())
            known = any(seat['seat'] == subject and seat['type'] == 'seat' for batch in recent
                for report in json.loads(batch.payload_json)['reports'] for seat in report['seats'])
        if not known:
            raise ValueError('该对象尚无可核对的名录或近期席位记录，匿名机构不能当作单一资金关注')
    if active and len(follows(session)) >= 200:
        raise ValueError('最多关注 200 个游资或营业部，请先取消部分关注')
    session.add(SeatFollow(kind=kind, subject=subject, active=active))
    session.commit()
    return follows(session)


def sync_day(session, day, client, catalog=None, now=None):
    """任一源失败/空表都保留旧批次；校验、原始响应和汇总版本一起提交。"""
    now = (now or utc_now()).astimezone(timezone.utc).replace(tzinfo=None)
    if day > collection_cutoff(now.replace(tzinfo=timezone.utc)):
        raise ValueError('不能采集尚未收盘或未来日期的龙虎榜')
    catalog = catalog or session.exec(select(HotMoneyCatalog).order_by(HotMoneyCatalog.id.desc()).limit(1)).first()
    if catalog is None or now-catalog.created_at >= timedelta(days=7):
        entries = catalog_entries(client.hm_list())
        checksum = digest(entries)
        # 相同内容的新采集时间也追加保存，以准确表示本次名录核对时间。
        catalog = HotMoneyCatalog(digest=checksum+'-'+now.isoformat(), entries_json=dumps(entries), created_at=now)
        session.add(catalog)
        session.commit()
        session.refresh(catalog)
    raw_top, raw_seats = client.top_list(trade_date=day.strftime('%Y%m%d')), client.top_inst(trade_date=day.strftime('%Y%m%d'))
    top, seats = top_records(raw_top, day), seat_records(raw_seats, day)
    if top is None or seats is None:
        return None, False
    if not top or not seats:
        raise ValueError('未返回可核对的 A 股披露，保留旧版本')
    payload = build_payload(top, seats, json.loads(catalog.entries_json))
    checksum = digest({'top': top, 'seats': seats, 'catalog_id': catalog.id})
    old = latest_batch(session, day)
    if old and old.digest == checksum:
        return old, False
    # 源字段完整保留，详情可检查源数据；衍生口径使用 Decimal 字符串。
    raw = {'top_list': json.loads(raw_top.to_json(orient='records', force_ascii=False)),
           'top_inst': json.loads(raw_seats.to_json(orient='records', force_ascii=False))}
    batch = SeatDisclosureBatch(trade_date=day, digest=checksum, catalog_id=catalog.id,
        raw_json=dumps(raw), payload_json=dumps(payload), fetched_at=now)
    session.add(batch)
    session.commit()
    session.refresh(batch)
    return batch, True


def collection_cutoff(now=None):
    local = (now or utc_now()).astimezone(SH)
    return local.date() if local.hour >= 15 else local.date()-timedelta(days=1)


def enrich(session, batch, following=None, watch_pool=None):
    if batch is None:
        return []
    day = batch.trade_date
    codes, refs, names = watch_pool or pool(session, day)
    following = follows(session) if following is None else following
    payload = json.loads(batch.payload_json)
    heights = {row.stock_code: row.limit_times for row in session.exec(select(LimitUpDaily)
        .where(LimitUpDaily.trade_date == day, LimitUpDaily.limit_type == 'U')).all()}
    result = []
    for raw in payload['reports']:
        if not raw['selected']:
            continue
        row = {**raw, 'date': str(day), 'batch_id': batch.id, 'fetched_at': iso(batch.fetched_at),
            'watched': raw['code'] in codes, 'followed': follow_match(raw, following),
            'observations': refs.get(raw['code'], []), 'height': heights.get(raw['code']),
            'names': sorted({name for seat in raw['seats'] if seat['association'] == 'catalog' for name in seat['names']}),
            'institution_net': str(sum((Decimal(seat['net']) for seat in raw['seats'] if seat['type'] == 'institution'), Decimal(0)))
                if raw['seats'] else None,
            'tags': []}
        result.append(row)
    return result


def stock_tags(rows, history, coverage):
    previous = defaultdict(list)
    for batch in history:
        for report in json.loads(batch.payload_json)['reports']:
            if report['selected']:
                previous[(report['code'], report['period'])].append((str(batch.trade_date), report['net']))
    for row in rows:
        earlier = sorted((day, net) for day, net in previous[(row['code'], row['period'])] if day < row['date'])
        if coverage['complete'] and not earlier:
            row['tags'].append('近20交易日首次披露')
        if row['net'] is not None and Decimal(row['net']) < 0 and earlier and earlier[-1][1] is not None and Decimal(earlier[-1][1]) > 0:
            row['tags'].append('较上次披露由净买转净卖')
        if row['period'] == 'day' and row['net'] is not None and Decimal(row['net']) > 0:
            dates = coverage['expected_dates'][-3:]
            values = dict(earlier + [(row['date'], row['net'])])
            if len(dates) == 3 and all(values.get(day) is not None and Decimal(values[day]) > 0 for day in dates):
                row['tags'].append('连续3交易日披露净买')
    return rows


def dashboard(session, day, scope='all', selected_period='day', search='', page=1):
    batch = latest_batch(session, day)
    history, coverage = load_window(session, day)
    rows = stock_tags(enrich(session, batch), history, coverage)
    chosen = [row for row in rows if row['period'] == selected_period]
    focus = [row for row in chosen if row['watched'] or row['followed']]
    focus.sort(key=lambda row: (not row['watched'], not row['followed'], -abs(Decimal(row['net'] or '0'))))
    counts = {'stocks': len(chosen), 'mine': sum(row['watched'] for row in chosen),
              'followed': sum(row['followed'] for row in chosen),
              'large_sell': sum(row['net'] is not None and Decimal(row['net']) <= -50000000 for row in chosen)}
    items = [row for row in chosen if (scope == 'all' or scope == 'mine' and row['watched'] or scope == 'followed' and row['followed'])
        and (not search.strip() or search.strip() in row['code']+row['name']+' '.join(row['names'])+' '.join(seat['seat'] for seat in row['seats']))]
    items.sort(key=lambda row: (not row['watched'], not row['followed'], -abs(Decimal(row['net'] or '0')), row['code']))
    pages = max(1, (len(items)+14)//15)
    page = min(page, pages)
    catalog = session.get(HotMoneyCatalog, batch.catalog_id) if batch else None
    def compact(row):
        return {key: value for key, value in row.items() if key != 'seats'}
    return {'date': str(day), 'batch_id': batch.id if batch else None, 'fetched_at': iso(batch.fetched_at) if batch else None,
        'catalog_id': catalog.id if catalog else None, 'catalog_at': iso(catalog.created_at) if catalog else None,
        'quality': json.loads(batch.payload_json)['quality'] if batch else None,
        'coverage': coverage, 'counts': counts, 'focus': [compact(row) for row in focus[:8]],
        'items': [compact(row) for row in items[(page-1)*15:page*15]], 'total': len(items), 'page': page, 'pages': pages,
        'method': METHOD, 'limitation': LIMITATION, 'follows': follows(session),
        'scope_note': '关注优先使用当前自选及截至所选日待验证的观察记录，不作历史选股回测。'}


def stock_detail(session, code, day, batch_id=None):
    batch = session.get(SeatDisclosureBatch, batch_id) if batch_id else latest_batch(session, day)
    if not batch or batch.trade_date != day:
        return None
    reports = [row for row in json.loads(batch.payload_json)['reports'] if row['code'] == code]
    if not reports:
        return None
    catalog = session.get(HotMoneyCatalog, batch.catalog_id)
    versions = session.exec(select(SeatDisclosureBatch.id, SeatDisclosureBatch.fetched_at)
        .where(SeatDisclosureBatch.trade_date == day).order_by(SeatDisclosureBatch.id.desc()).limit(20)).all()
    raw = json.loads(batch.raw_json)
    return {'date': str(day), 'code': code, 'batch_id': batch.id, 'fetched_at': iso(batch.fetched_at),
        'reports': reports, 'catalog_id': catalog.id, 'catalog_at': iso(catalog.created_at),
        'versions': [{'id': key, 'fetched_at': iso(stamp)} for key, stamp in versions],
        'raw': {key: [row for row in values if str(row.get('ts_code', '')).split('.')[0] == code] for key, values in raw.items()},
        'method': METHOD, 'limitation': LIMITATION}


def seat_history(session, day, kind, subject, days=20):
    batches, coverage = load_window(session, day, days)
    records = []
    for batch in batches:
        for report in json.loads(batch.payload_json)['reports']:
            if not report['selected']:
                continue
            selected = [seat for seat in report['seats'] if seat['type'] == 'seat' and not seat['conflict'] and
                (seat['seat'] == subject if kind == 'seat' else seat['association'] == 'catalog' and subject in seat['names'])]
            if selected:
                records.append({'date': str(batch.trade_date), 'code': report['code'], 'name': report['name'],
                    'period': report['period'], 'reason': report['reason'], 'batch_id': batch.id,
                    'catalog_id': batch.catalog_id, 'fetched_at': iso(batch.fetched_at),
                    'buy': str(sum((Decimal(seat['buy']) for seat in selected), Decimal(0))),
                    'sell': str(sum((Decimal(seat['sell']) for seat in selected), Decimal(0))),
                    'net': str(sum((Decimal(seat['net']) for seat in selected), Decimal(0))),
                    'seats': [seat['seat'] for seat in selected]})
    return {'kind': kind, 'subject': subject, 'days': days, 'coverage': coverage, 'items': records,
            'method': METHOD, 'limitation': LIMITATION}


def publish_events(session, batch, notify=False, now=None):
    evaluations = []
    for report in enrich(session, batch):
        relevant = report['watched'] or report['followed']
        item = candidate(batch.trade_date, 'close', 'seat_flow_'+report['period'], report['code'],
            f"{report['name']} {'关注股' if report['watched'] else '关注席位'}披露交易", 
            2 if report['net'] is not None and Decimal(report['net']) <= -50000000 else 1,
            report['net'] or '未知', '0',
            ('单日' if report['period'] == 'day' else '多日累计')+'披露；关注股票或席位命中。净卖出 ≥ 5000 万元升级。'+METHOD,
            iso(batch.fetched_at), triggered=relevant, refs=report['observations'], name=report['name'], unit='元')
        item['snapshot'].update(source='Tushare top_list / top_inst / hm_list', batch_id=batch.id,
            catalog_id=batch.catalog_id, names=report['names'], reason=report['reason'], limitation=LIMITATION)
        evaluations.append(item)
    return persist(session, evaluations, now=now, notify=notify) if evaluations else 0


def facts_for_codes(session, codes, day):
    """最近五个真实交易日的本地证据，批量读取且不调用模型或行情源。"""
    if not codes:
        return {}
    batches, coverage = load_window(session, day, 5)
    facts = defaultdict(list)
    for batch in reversed(batches):
        for report in json.loads(batch.payload_json)['reports']:
            if report['code'] not in codes or not report['selected']:
                continue
            names = sorted({name for seat in report['seats'] if seat['association'] == 'catalog' for name in seat['names']})
            facts[report['code']].append({'id': f"seat-flow-{batch.id}-{report['period']}",
                'label': f"{batch.trade_date} {'单日' if report['period']=='day' else '累计'}龙虎榜披露（非持仓）",
                'value': {'date': str(batch.trade_date), 'period_label': '单日' if report['period']=='day' else '多日累计',
                    'disclosed_net_yuan': report['net'], 'associated_names': names, 'disclosure_reason': report['reason'],
                    'source_batch_id': batch.id, 'catalog_version': batch.catalog_id, 'recorded_at': iso(batch.fetched_at),
                    'method': METHOD, 'limitation': LIMITATION}})
    if batches:
        for code in codes:
            facts[code].append({'id': 'seat-flow-coverage', 'label': '龙虎榜证据覆盖（缺失不视为无交易）',
                'value': {'cached_dates': coverage['cached_dates'], 'expected_dates': coverage['expected_dates'],
                          'calendar_known': coverage['calendar_known'], 'limitation': LIMITATION}})
    return dict(facts)
