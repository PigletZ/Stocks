from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select
from typing import List, Optional

from ..database import get_session
from ..models import IndexDaily, MarketDailyStat, RecentView, Stock, WatchlistItem
from ..services.overview_service import OverviewService

router = APIRouter()


def _parse_date(d: Optional[str]) -> date:
    if d:
        return datetime.strptime(d, "%Y-%m-%d").date()
    return date.today()


@router.get("/indices")
def get_indices():
    """主要指数实时行情"""
    service = OverviewService()
    return service.fetch_index_spot()


@router.get("/market-summary")
def get_market_summary():
    """市场概览汇总：上涨、下跌、涨停、跌停、炸板数量"""
    service = OverviewService()
    return service.fetch_today_market_stats()


@router.get("/market-history")
def get_market_history(
    start: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD，默认 7 天前"),
    end: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD，默认今天"),
    session: Session = Depends(get_session),
):
    """指定日期范围的市场统计折线图数据"""
    end_date = _parse_date(end)
    start_date = _parse_date(start) if start else end_date - timedelta(days=6)
    service = OverviewService()
    return service.fetch_market_history(start_date, end_date, session)


@router.get("/daily-overview")
def get_daily_overview(
    date: Optional[str] = Query(None, description="日期 YYYY-MM-DD，默认今天"),
    session: Session = Depends(get_session),
):
    """指定日期的日概览数据（指数 + 市场统计）"""
    target_date = _parse_date(date)
    service = OverviewService()
    return service.fetch_daily_overview(target_date, session)


@router.post("/sync-daily")
def sync_daily_overview(
    date: Optional[str] = Query(None, description="日期 YYYY-MM-DD，默认今天"),
    session: Session = Depends(get_session),
):
    """手动同步指定日期的日概览数据（指数 + 市场统计），会覆盖已有缓存"""
    target_date = _parse_date(date)

    cached_indices = session.exec(
        select(IndexDaily).where(IndexDaily.trade_date == target_date)
    ).all()
    for row in cached_indices:
        session.delete(row)

    cached_stat = session.exec(
        select(MarketDailyStat).where(MarketDailyStat.stat_date == target_date)
    ).first()
    if cached_stat:
        session.delete(cached_stat)

    session.commit()

    service = OverviewService()
    result = service.fetch_daily_overview(target_date, session)
    return {
        "date": target_date.isoformat(),
        "indices_count": len(result.get("indices", [])),
        "market_stats": result.get("market_stats", {}),
    }


@router.get("/trade-dates")
def get_trade_dates(
    start: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
):
    """获取指定日期范围内的 A 股交易日列表"""
    end_date = _parse_date(end)
    start_date = _parse_date(start) if start else end_date - timedelta(days=30)
    service = OverviewService()
    dates = service.fetch_trade_dates(start_date, end_date)
    return [d.isoformat() for d in dates]


@router.get("/realtime")
def get_realtime_overview():
    """实时概览：指数、市场统计、领涨领跌"""
    service = OverviewService()
    return service.fetch_realtime_overview()


@router.get("/limit-up")
def get_limit_up_stocks(
    date: Optional[str] = Query(None, description="日期 YYYY-MM-DD，默认今天"),
    sort_by: str = Query("pct_chg", description="排序字段: pct_chg / amount / turnover_ratio / fd_ratio / first_time / open_times / limit_times"),
    order: str = Query("desc", description="排序方向: asc / desc"),
    offset: int = Query(0, description="分页偏移，默认 0"),
    limit: int = Query(20, description="每页条数，默认 20"),
):
    """涨停股票列表，支持日期、排序与分页"""
    target_date = _parse_date(date)
    service = OverviewService()
    return service.fetch_limit_up_stocks(
        target_date,
        sort_by=sort_by,
        order=order,
        offset=offset,
        limit=limit,
    )


@router.get("/limit-down")
def get_limit_down_stocks(
    date: Optional[str] = Query(None, description="日期 YYYY-MM-DD，默认今天"),
    sort_by: str = Query("pct_chg", description="排序字段: pct_chg / amount / turnover_ratio / fd_ratio / first_time / open_times / limit_times"),
    order: str = Query("asc", description="排序方向: asc / desc"),
    offset: int = Query(0, description="分页偏移，默认 0"),
    limit: int = Query(20, description="每页条数，默认 20"),
):
    """跌停股票列表，支持日期、排序与分页"""
    target_date = _parse_date(date)
    service = OverviewService()
    return service.fetch_limit_down_stocks(
        target_date,
        sort_by=sort_by,
        order=order,
        offset=offset,
        limit=limit,
    )


@router.get("/opened-limit")
def get_opened_limit_stocks(
    date: Optional[str] = Query(None, description="日期 YYYY-MM-DD，默认今天"),
    sort_by: str = Query("pct_chg", description="排序字段: pct_chg / amount / turnover_ratio / fd_ratio / first_time / open_times / limit_times"),
    order: str = Query("desc", description="排序方向: asc / desc"),
    offset: int = Query(0, description="分页偏移，默认 0"),
    limit: int = Query(20, description="每页条数，默认 20"),
):
    """炸板股票列表，支持日期、排序与分页"""
    target_date = _parse_date(date)
    service = OverviewService()
    return service.fetch_opened_limit_stocks(
        target_date,
        sort_by=sort_by,
        order=order,
        offset=offset,
        limit=limit,
    )


@router.get("/dragon-tiger")
def get_dragon_tiger(
    date: Optional[str] = Query(None, description="日期 YYYY-MM-DD，默认今天"),
    sort_by: str = Query("net_amount", description="排序字段: change_pct / net_amount / trade_date"),
    order: str = Query("desc", description="排序方向: asc / desc"),
    offset: int = Query(0, description="分页偏移，默认 0"),
    limit: int = Query(20, description="每页条数，默认 20"),
):
    """龙虎榜数据，支持排序与分页"""
    target_date = _parse_date(date)
    service = OverviewService()
    return service.fetch_dragon_tiger(
        target_date,
        sort_by=sort_by,
        order=order,
        offset=offset,
        limit=limit,
    )


@router.get("/top-movers")
def get_top_movers(direction: str = "up", limit: int = 10):
    """领涨/领跌股票"""
    service = OverviewService()
    return service.fetch_top_movers(direction=direction, limit=limit)


@router.get("/sectors")
def get_sector_ranking(
    type: str = Query("industry", description="板块类型: industry / concept"),
    limit: int = 20,
):
    """板块涨幅排行（基于最新可用收盘日线数据）"""
    sector_type = type if type in ("industry", "concept") else "industry"
    service = OverviewService()
    return service.fetch_sector_ranking(sector_type=sector_type, limit=limit)


@router.get("/speed-ranking")
def get_speed_ranking(
    interval: str = Query("5min", description="时间窗口: 5min / 15min"),
    direction: str = Query("up", description="方向: up / down"),
    limit: int = 20,
):
    """涨速榜"""
    service = OverviewService()
    return service.fetch_speed_ranking(
        interval=interval, direction=direction, limit=limit
    )


@router.get("/recent-views")
def get_recent_views(limit: int = 10, session: Session = Depends(get_session)):
    """最近浏览的股票"""
    items = session.exec(
        select(RecentView, Stock)
        .join(Stock, RecentView.stock_code == Stock.code)
        .order_by(RecentView.viewed_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "code": stock.code,
            "name": stock.name,
            "exchange": stock.exchange,
            "viewed_at": rv.viewed_at.isoformat(),
        }
        for rv, stock in items
    ]


@router.post("/recent-views/{code}")
def record_recent_view(code: str, session: Session = Depends(get_session)):
    """记录最近浏览"""
    existing = session.exec(
        select(RecentView).where(RecentView.stock_code == code)
    ).first()
    if existing:
        existing.viewed_at = datetime.utcnow()
        session.add(existing)
    else:
        session.add(RecentView(stock_code=code))
    session.commit()
    return {"message": "已记录"}


@router.get("/sectors-daily")
def get_sectors_daily(
    date: Optional[str] = Query(None, description="日期 YYYY-MM-DD，默认今天"),
    type: Optional[str] = Query("all", description="类型: all / industry / concept"),
    sort_by: str = Query("change_pct", description="排序字段: change_pct / volume"),
    limit: int = Query(50, description="返回条数，默认 50"),
    session: Session = Depends(get_session),
):
    """获取指定日期的板块排行（行业 + 概念），数据优先从数据库读取"""
    target_date = _parse_date(date)
    service = OverviewService()
    result: dict = {}

    types_to_fetch = []
    if type in ("all", "industry"):
        types_to_fetch.append("industry")
    if type in ("all", "concept"):
        types_to_fetch.append("concept")

    for st in types_to_fetch:
        result[st] = service.fetch_sector_ranking_for_date(
            target_date, st, sort_by=sort_by, limit=limit, session=session
        )

    return result


@router.post("/sync-sectors")
def sync_sectors_daily(
    date: Optional[str] = Query(None, description="日期 YYYY-MM-DD，默认今天"),
    type: Optional[str] = Query("all", description="类型: all / industry / concept"),
    session: Session = Depends(get_session),
):
    """手动同步指定日期的板块排行数据到数据库"""
    target_date = _parse_date(date)
    service = OverviewService()

    types_to_sync = []
    if type in ("all", "industry"):
        types_to_sync.append("industry")
    if type in ("all", "concept"):
        types_to_sync.append("concept")

    counts = {}
    for st in types_to_sync:
        counts[st] = service.sync_sector_ranking_for_date(target_date, st, session=session)

    return {"date": target_date.isoformat(), "counts": counts}


@router.get("/index-bars/{code}")
def get_index_bars(
    code: str,
    start: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD，默认 30 个交易日前"),
    end: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD，默认今天"),
    session: Session = Depends(get_session),
):
    """获取指定指数的历史 K 线数据（OHLCV）"""
    end_date = _parse_date(end)
    start_date = _parse_date(start) if start else end_date - timedelta(days=90)

    statement = (
        select(IndexDaily)
        .where(IndexDaily.code == code)
        .where(IndexDaily.trade_date >= start_date)
        .where(IndexDaily.trade_date <= end_date)
        .order_by(IndexDaily.trade_date.asc())
    )
    rows = session.exec(statement).all()

    return [
        {
            "stock_code": row.code,
            "timestamp": datetime.combine(row.trade_date, datetime.min.time()).isoformat(),
            "interval": "1d",
            "open": row.open,
            "high": row.high,
            "low": row.low,
            "close": row.close,
            "volume": row.volume,
            "adjusted": False,
        }
        for row in rows
    ]
