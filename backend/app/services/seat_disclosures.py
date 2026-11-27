"""龙虎榜原始披露单校验、选单与名录关联；单日与累计披露永不相加。"""
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

ANONYMOUS = {'机构专用', '机构专用席位'}
NORTH = {'沪股通专用', '深股通专用'}
METHOD = '同股同口径选择一份披露单汇总，多上榜原因和买卖榜不重复相加；单日、累计分开。'
LIMITATION = '仅为公开披露交易，不代表全部交易或持仓。游资名称为采集时名录关联，不能证明实际交易人或历史归属。'


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()


def number(value, nonnegative=False):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or (nonnegative and result < 0):
            raise ValueError('披露金额或行情值异常')
        return format(result.normalize(), 'f')
    except (InvalidOperation, TypeError):
        raise ValueError('披露金额或行情值缺失') from None


def period(reason):
    return 'multi' if re.search(r'连续|累计|三个交易日|3个交易日', reason) else 'day'


def is_stock(code):
    return bool(re.fullmatch(r'(6\d{5}\.SH|[03]\d{5}\.SZ|(?:[48]\d{5}|92\d{4})\.BJ)', code))


def normalize_seat(name):
    value = unicodedata.normalize('NFKC', name)
    value = re.sub(r'\s+', '', value)
    for word in ('股份有限公司', '有限责任公司', '有限公司', '证券营业部', '营业部'):
        value = value.replace(word, '')
    return value


def catalog_entries(frame):
    if frame is None or frame.empty or len(frame) >= 1000 or not {'name', 'orgs'}.issubset(frame.columns):
        raise ValueError('游资名录为空、格式异常或达到截断上限')
    entries = []
    for row in frame.to_dict('records'):
        name, orgs = row['name'], row['orgs']
        if isinstance(orgs, str):
            try:
                orgs = json.loads(orgs)
            except ValueError:
                orgs = re.split(r'[、，;；\n]', orgs)
        if not isinstance(name, str) or not name.strip() or len(name) > 120 or not isinstance(orgs, list):
            raise ValueError('游资名录项目异常')
        if any(not isinstance(org, str) or not org.strip() or len(org) > 200 for org in orgs):
            raise ValueError('关联营业部名称异常')
        entries.append({'name': name.strip(), 'orgs': sorted(set(org.strip() for org in orgs))})
    return sorted(entries, key=lambda row: dumps(row))


def association_index(entries):
    index = defaultdict(set)
    for row in entries:
        for org in row['orgs']:
            index[normalize_seat(org)].add(row['name'])
    return index


def associate(seat, index):
    if seat in ANONYMOUS:
        return {'type': 'institution', 'names': [], 'association': 'anonymous'}
    if seat in NORTH:
        return {'type': 'connect', 'names': [], 'association': 'collective'}
    names = sorted(index.get(normalize_seat(seat), []))
    return {'type': 'seat', 'names': names,
            'association': 'catalog' if len(names) == 1 else 'ambiguous' if names else 'unmapped'}


def validate_frame(frame, day, fields):
    if frame is None or frame.empty:
        return None
    if len(frame) >= 10000 or not set(fields).issubset(frame.columns):
        raise ValueError('龙虎榜字段异常或达到截断上限，保留旧版本')
    if not frame.trade_date.astype(str).eq(day.strftime('%Y%m%d')).all():
        raise ValueError('龙虎榜返回日期不符，保留旧版本')
    result = []
    for raw in frame.to_dict('records'):
        if not isinstance(raw['ts_code'], str) or not isinstance(raw['reason'], str) or not raw['reason'].strip():
            raise ValueError('龙虎榜代码或披露原因异常')
        if not is_stock(raw['ts_code']):
            continue
        row = {key: raw[key] for key in fields}
        row['reason'] = raw['reason'].strip()
        result.append(row)
    return result


TOP_FIELDS = ('trade_date', 'ts_code', 'name', 'reason', 'close', 'pct_change', 'l_buy', 'l_sell', 'net_amount')
SEAT_FIELDS = ('trade_date', 'ts_code', 'reason', 'exalter', 'side', 'buy', 'sell', 'net_buy')


def top_records(frame, day):
    rows = validate_frame(frame, day, TOP_FIELDS)
    if rows is None:
        return None
    for row in rows:
        for key in ('close', 'l_buy', 'l_sell'):
            row[key] = number(row[key], True)
        for key in ('pct_change', 'net_amount'):
            row[key] = number(row[key])
        if abs(Decimal(row['l_buy'])-Decimal(row['l_sell'])-Decimal(row['net_amount'])) > Decimal('1'):
            raise ValueError('龙虎榜买卖总额不能对齐，保留旧版本')
        if not isinstance(row['name'], str) or not row['name'].strip():
            raise ValueError('龙虎榜股票名称缺失')
    # 数据商重复返回完全相同的披露单只保留一份；原始接口响应仍由批次存档。
    return sorted({dumps(row): row for row in rows}.values(), key=dumps)


def seat_records(frame, day):
    rows = validate_frame(frame, day, SEAT_FIELDS)
    if rows is None:
        return None
    for row in rows:
        seat = row['exalter']
        if not isinstance(seat, str) or not seat.strip() or len(seat) > 200:
            raise ValueError('营业部名称异常')
        row['exalter'] = seat.strip()
        row['side'] = str(row['side'])
        if row['side'] not in ('0', '1'):
            raise ValueError('买卖榜方向异常')
        row['amount_issue'] = None
        try:
            row['buy'], row['sell'] = number(row['buy'], True), number(row['sell'], True)
            row['net_buy'] = number(row['net_buy'])
            if abs(Decimal(row['buy'])-Decimal(row['sell'])-Decimal(row['net_buy'])) > Decimal('1'):
                raise ValueError('席位净额不能对齐')
        except ValueError:
            # 某些交易所披露缺少另一侧金额，或数据商给出异常值，绝不填成 0。
            # 原值保存在批次 raw_json；该席位本次金额保留未知，不影响其他有效披露单。
            row['buy'] = row['sell'] = row['net_buy'] = None
            row['amount_issue'] = '源金额缺失、为负或买卖净额不符，本笔金额未知，未计入席位汇总'
    return sorted(rows, key=dumps)


def unique_seats(rows, index):
    """同一实名营业部跨买卖榜合并。匿名机构保留同侧多笔，不能当成同一家机构。"""
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row['exalter'], row['buy'], row['sell'], row['net_buy'])].append(row)
    result = []
    for (seat, buy, sell, net), group in sorted(grouped.items(), key=lambda item: dumps(item[0])):
        sides = Counter(row['side'] for row in group)
        count = max(sides.values()) if seat in ANONYMOUS else 1
        for ordinal in range(count):
            result.append({'seat': seat, 'buy': buy, 'sell': sell, 'net': net, 'ordinal': ordinal,
                           'sides': sorted(sides), 'amount_issue': group[0].get('amount_issue'), **associate(seat, index)})
    # 同一具名席位在一份单据出现不同金额时不猜测合并，保留所有明细并标注冲突。
    counts = Counter(row['seat'] for row in result if row['type'] == 'seat')
    for row in result:
        row['conflict'] = counts[row['seat']] > 1 if row['type'] == 'seat' else False
    return result


def build_payload(top, seats, entries):
    index = association_index(entries)
    reports = defaultdict(lambda: {'tops': [], 'seats': []})
    for row in top:
        reports[(row['ts_code'], row['reason'])]['tops'].append(row)
    for row in seats:
        reports[(row['ts_code'], row['reason'])]['seats'].append(row)
    stocks = []
    for (ts_code, reason), report in sorted(reports.items()):
        totals = report['tops']
        amounts = {(row['l_buy'], row['l_sell'], row['net_amount']) for row in totals}
        top_row = totals[0] if len(amounts) == 1 else None
        resolved = unique_seats(report['seats'], index)
        warnings = []
        if not top_row:
            warnings.append('该披露原因缺少可对齐的个股总额，汇总金额保留未知')
        if not resolved:
            warnings.append('该披露原因尚未取得席位明细')
        if any(row['conflict'] for row in resolved):
            warnings.append('同一营业部有金额冲突，保留原记录，不推断净额')
        if any(row['amount_issue'] for row in resolved):
            warnings.append('部分席位源金额异常或缺失，已标为未知；不补零、不计入席位金额汇总')
        stocks.append({'code': ts_code.split('.')[0], 'ts_code': ts_code,
                       'name': totals[0]['name'] if totals else ts_code.split('.')[0],
                       'period': period(reason), 'reason': reason,
                       'buy': top_row['l_buy'] if top_row else None,
                       'sell': top_row['l_sell'] if top_row else None,
                       'net': top_row['net_amount'] if top_row else None,
                       'close': top_row['close'] if top_row else None,
                       'change_pct': top_row['pct_change'] if top_row else None,
                       'seats': resolved, 'warnings': warnings})
    # 日汇总每股每种口径只选一份，优先字段对齐且席位齐备，再按原因排序稳定选单。
    choices = {}
    for item in sorted(stocks, key=lambda row: (bool(row['warnings']), row['reason'])):
        choices.setdefault((item['code'], item['period']), item['reason'])
    for item in stocks:
        item['selected'] = choices[(item['code'], item['period'])] == item['reason']
    return {'reports': stocks, 'method': METHOD, 'limitation': LIMITATION,
            'quality': {'reports': len(stocks), 'stocks': len({row['code'] for row in stocks}),
                        'warnings': sum(bool(row['warnings']) for row in stocks),
                        'mapped_records': sum(row['association'] == 'catalog' for item in stocks for row in item['seats']),
                        'seat_records': sum(len(item['seats']) for item in stocks)}}


def canonical_top_frame(frame):
    """旧缓存兼容：每股选一份单日榜，缺单日时选一份累计榜，绝不按原因求和。"""
    if frame is None or frame.empty:
        return frame
    result = frame.copy()
    result['_period'] = result.reason.astype(str).map(period)
    result = result.sort_values(['ts_code', '_period', 'reason']).drop_duplicates('ts_code', keep='first')
    return result.drop(columns=['_period'])
