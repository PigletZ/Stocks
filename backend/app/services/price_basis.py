"""统一区间计算：P1*F1/(P0*F0)-1；不取区间之外或最近日期的因子。"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re

import pandas as pd
from sqlalchemy.dialects.sqlite import insert
from sqlmodel import select

from ..config import settings
from ..models import Stock, StockAdjustmentFactor
from .runtime_state import RuntimeStore
from .tushare_client import TushareClient


def positive_decimal(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result > 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def price_change(base, current, base_factor=None, current_factor=None, basis="adjusted"):
    start, end = positive_decimal(base), positive_decimal(current)
    if start is None or end is None:
        return None
    if basis == "adjusted":
        first, last = positive_decimal(base_factor), positive_decimal(current_factor)
        if first is None or last is None:
            return None
        start, end = start*first, end*last
    elif basis != "raw":
        raise ValueError("Unknown price basis")
    return (end/start-1)*100


def normalize_factors(frame, day=None, code=None, start=None, end=None):
    if not isinstance(frame, pd.DataFrame) or frame.empty or not {"ts_code", "trade_date", "adj_factor"}.issubset(frame.columns):
        raise ValueError("No valid adjustment factors")
    rows = {}
    for item in frame.to_dict("records"):
        ts_code = str(item["ts_code"])
        if not re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", ts_code):
            raise ValueError("Invalid factor security code")
        trade_day = datetime.strptime(str(item["trade_date"]), "%Y%m%d").date()
        factor = positive_decimal(item["adj_factor"])
        if factor is None or (day is not None and trade_day != day) or (start is not None and trade_day < start) or (end is not None and trade_day > end) or (code is not None and ts_code.split('.')[0] != code):
            raise ValueError("Invalid factor date or value")
        key = (ts_code.split('.')[0], trade_day)
        if key in rows and rows[key]["adj_factor"] != str(factor):
            raise ValueError("Conflicting factor rows")
        rows[key] = {"ts_code": ts_code, "code": key[0], "trade_date": trade_day.strftime("%Y%m%d"), "adj_factor": str(factor)}
    return pd.DataFrame(list(rows.values()))


def fetch_daily_factors(client, api, day):
    frames, seen = [], set()
    for offset in range(0, 60000, 2000):
        frame = client.query(api, trade_date=day.strftime("%Y%m%d"), fields="ts_code,trade_date,adj_factor", limit=2000, offset=offset)
        if frame.empty:
            break
        normalized = normalize_factors(frame, day=day)
        keys = set(normalized["ts_code"])
        if seen.intersection(keys):
            raise RuntimeError("复权因子分页重复，本次未覆盖已有数据")
        seen.update(keys)
        frames.append(normalized)
        if len(frame) < 2000:
            break
    else:
        raise RuntimeError("复权因子分页未完整结束，本次未覆盖已有数据")
    if not frames:
        return pd.DataFrame(columns=["ts_code", "code", "trade_date", "adj_factor"])
    return pd.concat(frames, ignore_index=True)


def load_stock_factors(session, codes, start, end, dates=None):
    from .review_records import chunks
    output = {}
    for batch in chunks(list(set(codes))):
        statement = select(StockAdjustmentFactor.stock_code, StockAdjustmentFactor.trade_date, StockAdjustmentFactor.factor).where(
            StockAdjustmentFactor.stock_code.in_(batch), StockAdjustmentFactor.trade_date >= start, StockAdjustmentFactor.trade_date <= end)
        if dates is not None:
            statement = statement.where(StockAdjustmentFactor.trade_date.in_(dates))
        for code, day, factor in session.exec(statement).all():
            if positive_decimal(factor) is not None:
                output[(code, day)] = factor
    return output


class StockFactorService:
    def __init__(self, client=None, store=None):
        self.client = client or TushareClient(settings.tushare_token)
        self.store = store or RuntimeStore()
        self.last_skipped = False

    @staticmethod
    def write(session, frame):
        values = [{"stock_code": row["code"], "trade_date": datetime.strptime(row["trade_date"], "%Y%m%d").date(),
                   "factor": row["adj_factor"], "updated_at": datetime.utcnow()} for row in frame.to_dict("records")]
        for offset in range(0, len(values), 100):
            statement = insert(StockAdjustmentFactor).values(values[offset:offset+100])
            session.exec(statement.on_conflict_do_update(index_elements=["stock_code", "trade_date"],
                set_={"factor": statement.excluded.factor, "updated_at": statement.excluded.updated_at}))
        session.commit()
        return len(values)

    def sync_day(self, session, day, force=False):
        self.last_skipped = False
        from sqlalchemy import func
        count = session.exec(select(func.count()).select_from(StockAdjustmentFactor).where(StockAdjustmentFactor.trade_date == day)).one()
        cached = self.store.read("factor-stock-"+day.strftime("%Y%m%d"))
        if count and cached and not force:
            try:
                age = (datetime.now(timezone.utc)-datetime.fromisoformat(cached["fetched_at"])).total_seconds()
                if 0 <= age < 86400:
                    self.last_skipped = True
                    return count
            except (ValueError, KeyError, TypeError):
                pass
        frame = fetch_daily_factors(self.client, "adj_factor", day)
        if frame.empty:
            return 0
        if count and len(frame) < count*.95:
            raise RuntimeError("复权因子返回数量明显不足，保留已有数据")
        written = self.write(session, frame)
        try:
            self.store.write("factor-stock-"+day.strftime("%Y%m%d"), {"fetched_at": datetime.now(timezone.utc).isoformat(), "rows": written})
        except OSError:
            pass
        return written

    def sync_code(self, session, code, start, end):
        stock = session.exec(select(Stock).where(Stock.code == code)).first()
        if stock is None:
            raise ValueError("股票不存在")
        if (end-start).days > 366 or end < start:
            raise ValueError("单次补齐复权因子暂支持一年内区间")
        frame = self.client.query("adj_factor", ts_code=code+"."+stock.exchange, start_date=start.strftime("%Y%m%d"), end_date=end.strftime("%Y%m%d"))
        if frame.empty:
            return 0
        return self.write(session, normalize_factors(frame, code=code, start=start, end=end))
