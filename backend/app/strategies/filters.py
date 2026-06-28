from datetime import date
from typing import List, Optional

from sqlmodel import Session, select

from ..models import Stock


def is_st_stock(name: Optional[str]) -> bool:
    """判断是否为 ST 股票。"""
    if not name:
        return False
    return "ST" in name.upper()


def is_kcb(code: str) -> bool:
    """科创板：688。"""
    return code.startswith("688")


def is_cyb(code: str) -> bool:
    """创业板：300/301。"""
    return code.startswith("300") or code.startswith("301")


def is_bse(code: str) -> bool:
    """北交所：8/43/82/83/87/88/89/920。"""
    return (
        code.startswith("8")
        or code.startswith("43")
        or code.startswith("82")
        or code.startswith("83")
        or code.startswith("87")
        or code.startswith("88")
        or code.startswith("89")
        or code.startswith("920")
    )


def is_new_stock(list_date: Optional[date], trade_date: date, days: int = 365) -> bool:
    """次新股：上市不满指定天数。上市日期为空时视为次新股，保守过滤。"""
    if not list_date:
        return True
    return (trade_date - list_date).days < days


def is_main_board(code: str) -> bool:
    """主板：60/00/000，且排除科创板、创业板、北交所。"""
    if is_kcb(code) or is_cyb(code) or is_bse(code):
        return False
    return code.startswith("60") or code.startswith("00")


def apply_base_filters(
    codes: List[str],
    trade_date: date,
    session: Session,
    exclude_st: bool = True,
    exclude_kcb: bool = True,
    exclude_cyb: bool = True,
    exclude_bse: bool = True,
    exclude_new_stock_days: int = 365,
) -> List[str]:
    """应用基础过滤条件，返回合法股票代码列表。"""
    if not codes:
        return []

    stocks = session.exec(select(Stock).where(Stock.code.in_(codes))).all()
    stock_map = {s.code: s for s in stocks}

    filtered: List[str] = []
    for code in codes:
        stock = stock_map.get(code)
        if not stock:
            continue
        if exclude_st and is_st_stock(stock.name):
            continue
        if exclude_kcb and is_kcb(code):
            continue
        if exclude_cyb and is_cyb(code):
            continue
        if exclude_bse and is_bse(code):
            continue
        if exclude_new_stock_days > 0 and is_new_stock(stock.list_date, trade_date, exclude_new_stock_days):
            continue
        filtered.append(code)

    return filtered


def normalize_scores(picks: List["StockPick"]) -> List["StockPick"]:
    """将 score 归一化到 0-100。"""
    if not picks:
        return picks

    scores = [p.score for p in picks]
    min_score = min(scores)
    max_score = max(scores)

    if max_score == min_score:
        for p in picks:
            p.score = 50.0
        return picks

    for p in picks:
        p.score = round((p.score - min_score) / (max_score - min_score) * 100, 2)
    return picks


def sort_and_top(picks: List["StockPick"], top_n: int = 10) -> List["StockPick"]:
    """按评分降序排序并取前 N。"""
    picks.sort(key=lambda x: x.score, reverse=True)
    return picks[:top_n]
