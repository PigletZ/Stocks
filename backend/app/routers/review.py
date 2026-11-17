from datetime import datetime, date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel import Session

from ..database import get_session
from ..services.review_service import ReviewService
from ..services.review_workbench import ReviewWorkbench, today_shanghai
from ..models import ReviewObservation, ReviewVerification, Stock

router = APIRouter()


@router.get("/workbench")
def workbench(target: Optional[date] = Query(None, alias="date"), session: Session = Depends(get_session)):
    return ReviewWorkbench().get(session, target)


class ObservationIn(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")
    observation_date: date
    reason: str = Field(min_length=1, max_length=2000)
    criterion: str = Field(min_length=1, max_length=2000)
    deadline: date


@router.post("/observations")
def create_observation(body: ObservationIn, session: Session = Depends(get_session)):
    if body.observation_date > today_shanghai() or body.deadline < body.observation_date:
        raise HTTPException(400, "关注日期不能晚于今天，验证期限不能早于关注日期")
    if not body.reason.strip() or not body.criterion.strip():
        raise HTTPException(400, "请填写关注理由及待验证条件")
    if session.exec(select(Stock).where(Stock.code == body.code)).first() is None:
        raise HTTPException(400, "请输入本地股票列表中的 A 股代码")
    record = ReviewObservation(stock_code=body.code, observation_date=body.observation_date,
        reason=body.reason.strip(), criterion=body.criterion.strip(), deadline=body.deadline)
    session.add(record)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "该股票在这一天已有关注记录，请直接补充验证结果")
    return {"id": record.id}


class VerificationIn(BaseModel):
    verdict: Literal['符合预期', '不符合预期', '继续观察']
    explanation: str = Field(min_length=1, max_length=2000)


@router.put("/observations/{observation_id}/verification")
def verify_observation(observation_id: int, body: VerificationIn,
                       target: date = Query(..., alias="date"), session: Session = Depends(get_session)):
    observation = session.get(ReviewObservation, observation_id)
    if observation is None:
        raise HTTPException(404, "关注记录不存在")
    if target < observation.observation_date or target > today_shanghai():
        raise HTTPException(400, "验证日期必须在关注日期与今天之间")
    if not body.explanation.strip():
        raise HTTPException(400, "请填写判断依据，价格上涨不等于符合原始预期")
    row = session.exec(select(ReviewVerification).where(ReviewVerification.observation_id == observation_id,
        ReviewVerification.review_date == target)).first()
    if row is None:
        row = ReviewVerification(observation_id=observation_id, review_date=target, verdict=body.verdict)
    row.verdict, row.explanation, row.updated_at = body.verdict, body.explanation.strip(), datetime.utcnow()
    session.add(row)
    session.commit()
    return {"saved": True}


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
