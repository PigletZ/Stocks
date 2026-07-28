from datetime import datetime, date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from ..database import get_session
from ..services.review_service import ReviewService

router = APIRouter()


def _parse_date(d: Optional[str]) -> Optional[date]:
    if d:
        return datetime.strptime(d, "%Y-%m-%d").date()
    return None


@router.get("/limit-ladder")
def get_limit_ladder(
    date: Optional[str] = Query(None, description="交易日 YYYY-MM-DD，默认最新缓存日期"),
    session: Session = Depends(get_session),
):
    """连板梯队：涨停股按连板数分组"""
    service = ReviewService()
    return service.get_limit_ladder(_parse_date(date), session)


@router.get("/limit-performance")
def get_limit_performance(
    date: Optional[str] = Query(None, description="交易日 YYYY-MM-DD，默认最新缓存日期"),
    session: Session = Depends(get_session),
):
    """昨日涨停今日表现：晋级率、平均涨幅与个股明细"""
    service = ReviewService()
    return service.get_limit_performance(_parse_date(date), session)


@router.get("/emotion")
def get_emotion_series(
    start: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD，默认 90 天前"),
    end: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD，默认今天"),
    session: Session = Depends(get_session),
):
    """情绪周期时间序列：涨停/跌停/炸板数、炸板率、晋级率、最高板"""
    service = ReviewService()
    end_date = _parse_date(end) or date.today()
    start_date = _parse_date(start) or (end_date - timedelta(days=90))
    return service.get_emotion_series(start_date, end_date, session)


@router.post("/sync")
def sync_review_data(
    date: Optional[str] = Query(None, description="交易日 YYYY-MM-DD，默认今天"),
    session: Session = Depends(get_session),
):
    """手动触发指定日期的涨停/龙虎榜数据落库"""
    service = ReviewService()
    target = _parse_date(date) or date.today()
    limit_count = service.sync_limit_daily(target, session)
    dragon_count = service.sync_dragon_tiger_daily(target, session)
    return {"trade_date": target.isoformat(), "limit_count": limit_count, "dragon_count": dragon_count}
