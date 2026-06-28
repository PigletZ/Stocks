from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, or_, func
from typing import List, Optional
from datetime import date, datetime

from ..database import get_session
from ..models import Stock, StockDailyQuote
from ..services.tushare_stock_service import TushareStockService

router = APIRouter()


def _parse_date(d: Optional[str]) -> Optional[date]:
    if d:
        return datetime.strptime(d, "%Y-%m-%d").date()
    return None


STOCK_SORTABLE_FIELDS = {"code", "name", "industry", "list_date", "exchange"}
QUOTE_SORTABLE_FIELDS = {
    "close",
    "change_pct",
    "amount",
    "turnover_rate",
    "turnover_rate_f",
    "float_mv",
    "total_mv",
    "pe",
    "pe_ttm",
    "pb",
    "ps",
    "ps_ttm",
}


def _get_latest_trade_date(session: Session) -> Optional[date]:
    # 只取最新交易日：必须显式 limit(1)，否则 SQLAlchemy 的 .first() 会先把
    # 全表(17 万+行)行情都实例化成 ORM 对象再取首行，造成数秒延迟与内存飙升。
    latest = session.exec(
        select(StockDailyQuote.trade_date)
        .order_by(StockDailyQuote.trade_date.desc())
        .limit(1)
    ).first()
    return latest


@router.get("")
def list_stocks(
    search: str = "",
    industry: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: str = Query("code", description="排序字段"),
    sort_order: str = Query("asc", description="asc / desc"),
    session: Session = Depends(get_session),
):
    """分页股票列表，关联最新交易日行情"""
    latest_date = _get_latest_trade_date(session)

    # 1. 统计总数（仅按 Stock 过滤）
    count_query = select(func.count(Stock.id))
    if search:
        keyword = f"%{search}%"
        count_query = count_query.where(
            or_(Stock.code.like(keyword), Stock.name.like(keyword))
        )
    if industry:
        count_query = count_query.where(Stock.industry == industry)
    total = session.exec(count_query).one() or 0

    # 2. 构造分页查询
    query = (
        select(Stock, StockDailyQuote)
        .outerjoin(
            StockDailyQuote,
            (Stock.code == StockDailyQuote.stock_code)
            & (StockDailyQuote.trade_date == latest_date),
        )
    )

    if search:
        keyword = f"%{search}%"
        query = query.where(or_(Stock.code.like(keyword), Stock.name.like(keyword)))
    if industry:
        query = query.where(Stock.industry == industry)

    # 排序
    sort_by = sort_by if sort_by in STOCK_SORTABLE_FIELDS or sort_by in QUOTE_SORTABLE_FIELDS else "code"
    if sort_by in STOCK_SORTABLE_FIELDS:
        sort_column = getattr(Stock, sort_by)
    else:
        sort_column = getattr(StockDailyQuote, sort_by, StockDailyQuote.close)

    if sort_order.lower() == "desc":
        query = query.order_by(sort_column.desc().nullslast(), Stock.code.asc())
    else:
        query = query.order_by(sort_column.asc().nullsfirst(), Stock.code.asc())

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    rows = session.exec(query).all()

    items = []
    for row in rows:
        stock = row[0]
        quote = row[1] if len(row) > 1 else None
        items.append(_stock_with_quote(stock, quote))

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/industries")
def list_industries(session: Session = Depends(get_session)):
    """返回所有行业列表"""
    rows = session.exec(
        select(Stock.industry)
        .where(Stock.industry.isnot(None))
        .where(Stock.industry != "")
        .where(Stock.industry != "None")
        .distinct()
        .order_by(Stock.industry)
    ).all()
    return [r for r in rows if r]


@router.get("/{code}")
def get_stock(code: str, session: Session = Depends(get_session)):
    """股票详情：基本信息 + 最新行情"""
    stock = session.exec(select(Stock).where(Stock.code == code)).first()
    if not stock:
        raise HTTPException(status_code=404, detail="股票不存在")

    quote = session.exec(
        select(StockDailyQuote)
        .where(StockDailyQuote.stock_code == code)
        .order_by(StockDailyQuote.trade_date.desc())
        .limit(1)
    ).first()

    return _stock_with_quote(stock, quote, include_detail=True)


@router.post("/sync")
def sync_stocks(session: Session = Depends(get_session)):
    """从 Tushare 同步 A 股基础信息"""
    service = TushareStockService()
    stocks = service.fetch_stock_list()

    existing = {s.code: s for s in session.exec(select(Stock)).all()}
    created = 0
    updated = 0

    for stock in stocks:
        if stock.code in existing:
            old = existing[stock.code]
            old.name = stock.name
            old.exchange = stock.exchange
            old.industry = stock.industry
            old.list_date = stock.list_date
            old.updated_at = datetime.utcnow()
            session.add(old)
            updated += 1
        else:
            session.add(stock)
            created += 1

    session.commit()
    return {"created": created, "updated": updated, "total": len(stocks)}


@router.post("/quotes/sync")
def sync_daily_quotes(
    trade_date: Optional[str] = Query(None, description="日期 YYYY-MM-DD，默认今天"),
    session: Session = Depends(get_session),
):
    """从 Tushare 同步指定日期全市场行情"""
    target_date = _parse_date(trade_date) or date.today()
    service = TushareStockService()
    quotes = service.fetch_daily_quotes(target_date)

    for quote in quotes:
        existing = session.exec(
            select(StockDailyQuote)
            .where(StockDailyQuote.stock_code == quote.stock_code)
            .where(StockDailyQuote.trade_date == quote.trade_date)
        ).first()
        if existing:
            for field in [
                "close",
                "change_pct",
                "amount",
                "turnover_rate",
                "turnover_rate_f",
                "float_mv",
                "total_mv",
                "pe",
                "pe_ttm",
                "pb",
                "ps",
                "ps_ttm",
                "dv_ratio",
                "dv_ttm",
            ]:
                setattr(existing, field, getattr(quote, field))
            existing.updated_at = datetime.utcnow()
            session.add(existing)
        else:
            session.add(quote)

    session.commit()
    return {"date": target_date.isoformat(), "count": len(quotes)}


def _stock_with_quote(
    stock: Stock,
    quote: Optional[StockDailyQuote],
    include_detail: bool = False,
) -> dict:
    data = {
        "code": stock.code,
        "name": stock.name,
        "exchange": stock.exchange,
        "industry": stock.industry,
        "list_date": stock.list_date.isoformat() if stock.list_date else None,
    }

    if include_detail:
        data.update(
            {
                "market": stock.market,
                "created_at": stock.created_at.isoformat() if stock.created_at else None,
                "updated_at": stock.updated_at.isoformat() if stock.updated_at else None,
            }
        )

    if quote:
        data.update(
            {
                "quote_date": quote.trade_date.isoformat(),
                "close": quote.close,
                "change_pct": quote.change_pct,
                "amount": quote.amount,
                "turnover_rate": quote.turnover_rate,
                "turnover_rate_f": quote.turnover_rate_f,
                "float_mv": quote.float_mv,
                "total_mv": quote.total_mv,
                "pe": quote.pe,
                "pe_ttm": quote.pe_ttm,
                "pb": quote.pb,
                "ps": quote.ps,
                "ps_ttm": quote.ps_ttm,
                "dv_ratio": quote.dv_ratio,
                "dv_ttm": quote.dv_ttm,
            }
        )
    else:
        data.update(
            {
                "quote_date": None,
                "close": None,
                "change_pct": None,
                "amount": None,
                "turnover_rate": None,
                "turnover_rate_f": None,
                "float_mv": None,
                "total_mv": None,
                "pe": None,
                "pe_ttm": None,
                "pb": None,
                "ps": None,
                "ps_ttm": None,
                "dv_ratio": None,
                "dv_ttm": None,
            }
        )

    return data
