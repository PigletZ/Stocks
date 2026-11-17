"""ETF 方向观察与同类比较，不推断资金流入或投资收益。"""
import math
from datetime import datetime, timedelta, timezone
from statistics import median

from .etf_service import _extract_category


def _number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def build_dashboard(service, target_date=None, min_amount=10000000):
    target = target_date or datetime.now(timezone(timedelta(hours=8))).date()
    dates = service._fetch_trade_dates(target - timedelta(days=100), target)
    effective = None
    end = None
    for day in reversed(dates[-6:]):
        frame = service._fetch_etf_daily_for_date(day)
        if not frame.empty:
            effective, end = day, frame
            break
    if effective is None:
        raise RuntimeError("近期 ETF 日线尚未发布或获取失败，请稍后重试")
    basic = service._get_etf_list_with_cache()
    if basic.empty:
        raise RuntimeError("ETF 基础资料获取失败，请稍后重试")
    position = dates.index(effective)
    bases = {}
    base_dates = {}
    for window in (2, 5, 10, 20):
        day = dates[position-window] if position >= window else None
        frame = service._fetch_etf_daily_for_date(day) if day else None
        bases[window] = {str(r["code"]): _number(r.get("close")) for r in frame.to_dict("records")} if frame is not None else {}
        base_dates[str(window)] = day.isoformat() if day else None
    return summarize(basic.to_dict("records"), end.to_dict("records"), bases,
                     target.isoformat(), effective.isoformat(), base_dates, min_amount)


def summarize(basic, daily, bases, target, effective, base_dates, min_amount):
    quotes = {str(row["code"]): row for row in daily}
    items = []
    quoted_count = 0
    for fund in basic:
        code = str(fund["code"])
        if "ETF" not in str(fund.get("name", "")).upper():
            continue
        row = quotes.get(code, {})
        close = _number(row.get("close"))
        raw_amount = _number(row.get("amount"))
        amount = raw_amount * 1000 if raw_amount is not None else None
        if close is None or close <= 0:
            continue
        quoted_count += 1
        if amount is None or amount < min_amount:
            continue
        item = {"code": code, "name": str(fund.get("name", "")),
                "category": _extract_category(str(fund.get("name", "")), str(fund.get("benchmark", ""))),
                "benchmark": str(fund.get("benchmark") or ""),
                "management": str(fund.get("management") or ""),
                "close": close, "amount": amount, "change_pct": _number(row.get("pct_chg"))}
        for window in (2, 5, 10, 20):
            base = _number(bases.get(window, {}).get(code))
            item[f"gain_{window}"] = round((close / base - 1) * 100, 2) if base is not None and base > 0 else None
        short, middle, long = item["gain_2"], item["gain_5"], item["gain_20"]
        item["state"] = "数据不足" if middle is None or long is None or short is None else (
            "短长同强" if short > 0 and middle > 0 and long > 0 else
            "短强长弱" if short > 0 and long <= 0 else
            "短弱长强" if short <= 0 and long > 0 else "其他/分化")
        items.append(item)
    items.sort(key=lambda r: (-r["amount"], r["code"]))
    groups = {}
    for item in items:
        groups.setdefault(item["category"], []).append(item)
    directions = []
    for category, members in groups.items():
        five = [r["gain_5"] for r in members if r["gain_5"] is not None]
        twenty = [r["gain_20"] for r in members if r["gain_20"] is not None]
        directions.append({"category": category, "count": len(members), "samples_5": len(five),
                           "median_5": median(five) if five else None,
                           "median_20": median(twenty) if twenty else None,
                           "positive_5": sum(v > 0 for v in five),
                           "representative": members[0]["code"], "amount": sum(r["amount"] for r in members)})
    directions.sort(key=lambda r: (r["median_5"] is None, -(r["median_5"] or 0), r["category"]))
    return {"target_date": target, "effective_date": effective, "base_dates": base_dates,
            "min_amount": min_amount, "quoted_count": quoted_count, "items": items,
            "directions": directions,
            "missing_windows": [w for w in (2, 5, 10, 20) if not bases.get(w)]}
