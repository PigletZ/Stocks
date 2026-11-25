"""只读检查区间报价与同日因子；不为了检查状态访问行情源。"""
import re
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlmodel import select

from ..models import StockDailyQuote
from .price_basis import load_stock_factors, normalize_factors, positive_decimal


def _quotes(cache, day):
    saved = cache.get('daily-' + day.strftime('%Y%m%d'))
    if not saved or not {'code', 'close'}.issubset(saved[1].columns):
        return {}
    result = {}
    for row in saved[1].to_dict('records'):
        code, price = str(row['code']), positive_decimal(row['close'])
        if 'trade_date' in row and str(row['trade_date']) != day.strftime('%Y%m%d'):
            return {}
        if re.fullmatch(r'\d{6}', code) and price is not None:
            if code in result and result[code] != price:
                return {}
            result[code] = price
    return result


def _fund_factors(cache, day):
    saved = cache.get('factor-' + day.strftime('%Y%m%d'))
    if not saved:
        return {}
    try:
        return {row['code']: row['adj_factor'] for row in normalize_factors(saved[1], day=day).to_dict('records')}
    except (ValueError, KeyError, TypeError):
        return {}


def _report(key, label, end, expected, dates, windows, quote_map, factors):
    position = dates.index(end) if end in dates else None
    results = []
    for window in windows:
        base = dates[position-window] if position is not None and position >= window else None
        samples = set(quote_map.get(end, {})) & set(quote_map.get(base, {}))
        valid = sum((code, base) in factors and (code, end) in factors for code in samples)
        results.append({'days': window, 'base_date': str(base) if base else None,
            'valid': valid, 'total': len(samples), 'missing_factors': len(samples)-valid,
            'coverage_pct': round(valid/len(samples)*100, 2) if samples else None})
    status, message = 'unknown', '官方日历或区间报价未齐全，暂不能确认复权覆盖。'
    if expected and end and end < expected:
        status, message = 'stale', f'应有 {expected} 的报价，当前只核对到 {end}。'
    elif position is not None and all(row['total'] for row in results):
        missing = sum(row['missing_factors'] for row in results)
        status = ('partial' if missing else 'ok') if expected else 'unknown'
        message = ('部分报价对缺少同日因子，不计算其复权变化。' if missing else
                   '各区间有报价的样本均有对应因子。') if expected else '已核对可用报价对；应有日期待确认。'
    return {'key': key, 'label': label, 'status': status, 'message': message,
            'effective_date': str(end) if end else None, 'expected_date': str(expected) if expected else None,
            'windows': results, 'note': '分母为起止日均有有效报价的样本；停牌、上市时间及缺报价会影响分母，不代表全市场覆盖或账户收益。'}


def price_coverage(session, etf, expected, local_day):
    cutoff = expected or local_day
    calendar = etf.cached_trade_dates(cutoff-timedelta(days=100), cutoff)
    dates = calendar[0] if calendar else []
    stock_end = session.exec(select(func.max(StockDailyQuote.trade_date)).where(StockDailyQuote.trade_date <= cutoff)).one()
    needed = set()
    if stock_end in dates:
        index = dates.index(stock_end)
        needed = {stock_end} | {dates[index-n] for n in (5, 10, 20) if index >= n}
    quote_map = {}
    for code, day, close in session.exec(select(StockDailyQuote.stock_code, StockDailyQuote.trade_date, StockDailyQuote.close)
            .where(StockDailyQuote.trade_date >= cutoff-timedelta(days=100), StockDailyQuote.trade_date <= cutoff,
                   StockDailyQuote.trade_date.in_(needed))).all():
        if positive_decimal(close) is not None:
            quote_map.setdefault(day, {})[code] = close
    codes = {code for prices in quote_map.values() for code in prices}
    factors = load_stock_factors(session, codes, cutoff-timedelta(days=100), cutoff, dates=needed) if needed else {}
    stock = _report('stock', '股票区间复权', stock_end, expected, dates, (5, 10, 20), quote_map, factors)
    cache = etf._frame_cache
    available = []
    try:
        for path in cache.directory.glob('daily-*.json'):
            try:
                day = datetime.strptime(path.stem[6:], '%Y%m%d').date()
                if cutoff-timedelta(days=100) <= day <= cutoff:
                    available.append(day)
            except ValueError:
                continue
    except OSError:
        pass
    fund_end = max(available, default=None)
    fund_quotes, fund_factors = {}, {}
    basic = cache.get('basic')
    universe = {str(row['code']) for row in basic[1].to_dict('records')
                if 'ETF' in str(row.get('name', '')).upper() and row.get('status', 'L') == 'L'} if basic and 'code' in basic[1] else set()
    if fund_end in dates and universe:
        index = dates.index(fund_end)
        needed = {fund_end} | {dates[index-n] for n in (2, 5, 10, 20) if index >= n}
        for day in needed:
            fund_quotes[day] = {code: price for code, price in _quotes(cache, day).items() if code in universe}
            fund_factors.update({(code, day): value for code, value in _fund_factors(cache, day).items()})
    fund = _report('etf', 'ETF 区间复权', fund_end, expected, dates, (2, 5, 10, 20), fund_quotes, fund_factors)
    return [stock, fund]
