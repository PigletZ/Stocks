from datetime import datetime, date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel import Session

from ..database import get_session
from ..validation import parse_iso_date
from ..services.review_service import ReviewService
from ..services.review_workbench import ReviewWorkbench, today_shanghai
from ..models import ReviewAudit, ReviewCondition, ReviewObservation, ReviewReminderState, ReviewVerification, Stock
from ..services.review_assistant import ConditionInput, ConditionSpec, ReviewAssistant, audit_view, condition_view, save_condition
from ..services.review_ai import AuditBusy, AuditUnavailable, generate_audit
from ..services import review_tracking
from ..services.etf_service import EtfService
from ..services.price_basis import StockFactorService
from ..services import review_feedback

router = APIRouter()


@router.get("/workbench")
def workbench(target: Optional[date] = Query(None, alias="date"), session: Session = Depends(get_session), include_observations: bool = True):
    return ReviewWorkbench().get(session, target, include_observations)


class ObservationIn(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")
    observation_date: date
    reason: str = Field(min_length=1, max_length=2000)
    criterion: str = Field(min_length=1, max_length=2000)
    deadline: date
    condition: Optional[ConditionSpec] = None


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
        session.flush()
        if body.condition:
            save_condition(session, record, ConditionInput(**body.condition.model_dump(), effective_date=body.observation_date), commit=False)
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "该股票在这一天已有关注记录，请直接补充验证结果")
    except ValueError as error:
        session.rollback()
        raise HTTPException(400, str(error)) from None
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


def _review_date(session, target):
    result = target or ReviewWorkbench.dates(session)[0]
    if result > today_shanghai():
        raise HTTPException(400, "不能审阅未来日期")
    return result


def _observation(session, observation_id):
    record = session.get(ReviewObservation, observation_id)
    if record is None:
        raise HTTPException(404, "关注记录不存在")
    return record


@router.get("/assistant")
def review_assistant(target: Optional[date] = Query(None, alias="date"), session: Session = Depends(get_session),
                     page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=50),
                     include_hidden: bool = False, include_entries: bool = False):
    return ReviewAssistant().dashboard(session, _review_date(session, target), include_entries, page, page_size, include_hidden)


@router.get("/deadlines")
def get_deadlines(target: date = Query(..., alias="date")):
    if target > today_shanghai():
        raise HTTPException(400, "关注日期不能晚于今天")
    try:
        return review_tracking.trading_deadlines(target, EtfService()._fetch_trade_dates)
    except RuntimeError:
        raise HTTPException(503, "暂未取得完整官方日历，可稍后重试或手动选择日期") from None


@router.get("/observations")
def observation_list(target: date = Query(..., alias="date"),
                     status: Literal["pending", "due", "completed", "all"] = "pending",
                     search: str = Query("", max_length=100), page: int = Query(1, ge=1),
                     page_size: int = Query(20, ge=1, le=50), session: Session = Depends(get_session)):
    return review_tracking.list_observations(session, _review_date(session, target), status, search, page, page_size)


@router.get("/observations/{observation_id}")
def get_observation(observation_id: int, target: date = Query(..., alias="date"), session: Session = Depends(get_session)):
    observation = _observation(session, observation_id)
    try:
        return review_tracking.observation_detail(session, observation, _review_date(session, target))
    except ValueError as error:
        raise HTTPException(400, str(error)) from None


@router.get("/observations/{observation_id}/audits")
def get_audit_history(observation_id: int, target: date = Query(..., alias="date"),
                      page: int = Query(1, ge=1), page_size: int = Query(5, ge=1, le=20), session: Session = Depends(get_session)):
    observation = _observation(session, observation_id)
    if _review_date(session, target) < observation.observation_date:
        raise HTTPException(400, "审阅日期不能早于关注日期")
    return review_tracking.audit_history(session, observation, target, page, page_size)


@router.get("/observations/{observation_id}/audits/{audit_id}")
def get_saved_audit(observation_id: int, audit_id: int, target: date = Query(..., alias="date"), session: Session = Depends(get_session)):
    observation = _observation(session, observation_id)
    target = _review_date(session, target)
    record = session.get(ReviewAudit, audit_id)
    if record is None or record.observation_id != observation.id or record.review_date > target:
        raise HTTPException(404, "截至所选日期没有这份审阅记录")
    current = ReviewAssistant().context(session, observation, target)
    return review_feedback.attach_feedback(session, audit_view(record, current["context_hash"], current["context"]), target)


def _feedback_audit(session, observation_id, audit_id, target):
    _observation(session, observation_id)
    record = session.get(ReviewAudit, audit_id)
    if record is None or record.observation_id != observation_id or record.review_date > target:
        raise HTTPException(404, "截至所选日期没有这份审阅记录")
    return record


@router.post("/observations/{observation_id}/audits/{audit_id}/feedback")
def submit_audit_feedback(observation_id: int, audit_id: int, body: review_feedback.FeedbackInput, session: Session = Depends(get_session)):
    target = _review_date(session, body.date)
    audit = _feedback_audit(session, observation_id, audit_id, target)
    try:
        return review_feedback.save_feedback(session, audit, body)
    except ValueError as error:
        raise HTTPException(400, str(error)) from None


@router.get("/observations/{observation_id}/audits/{audit_id}/feedback")
def audit_feedback_history(observation_id: int, audit_id: int, target: date = Query(..., alias="date"),
                          section: review_feedback.SECTIONS = Query(...), item_index: int = Query(..., ge=0, le=3),
                          page: int = Query(1, ge=1), session: Session = Depends(get_session)):
    target = _review_date(session, target)
    audit = _feedback_audit(session, observation_id, audit_id, target)
    return review_feedback.history(session, audit, target, section, item_index, page)


@router.post("/observations/{observation_id}/factors")
def sync_observation_factors(observation_id: int, target: date = Query(..., alias="date"), session: Session = Depends(get_session)):
    observation = _observation(session, observation_id)
    target = _review_date(session, target)
    if target < observation.observation_date:
        raise HTTPException(400, "补齐日期不能早于关注日期")
    end = min(target, observation.deadline)
    try:
        source = StockFactorService()
        count = source.sync_code(session, observation.stock_code, observation.observation_date, end)
        if target > end:
            count += source.sync_code(session, observation.stock_code, target, target)
        if not count:
            raise HTTPException(503, "未取得有效复权因子，已有数据已保留")
        return {'written_rows': count}
    except ValueError as error:
        session.rollback()
        raise HTTPException(400, str(error)) from None
    except RuntimeError:
        session.rollback()
        raise HTTPException(503, "复权因子暂时无法补齐，已有数据已保留，请稍后重试") from None


@router.post("/observations/{observation_id}/conditions")
def confirm_condition(observation_id: int, body: ConditionInput, session: Session = Depends(get_session)):
    try:
        return save_condition(session, _observation(session, observation_id), body)
    except ValueError as error:
        raise HTTPException(400, str(error)) from None


@router.get("/observations/{observation_id}/conditions")
def condition_history(observation_id: int, target: date = Query(..., alias="date"), session: Session = Depends(get_session)):
    observation = _observation(session, observation_id)
    if _review_date(session, target) < observation.observation_date:
        raise HTTPException(400, "规则日期不能早于关注日期")
    rows = session.exec(select(ReviewCondition).where(ReviewCondition.observation_id == observation_id,
        ReviewCondition.effective_date <= target).order_by(ReviewCondition.effective_date.desc(), ReviewCondition.id.desc()).limit(100)).all()
    return [condition_view(row) for row in rows]


class AuditIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date
    force: bool = False


@router.post("/observations/{observation_id}/audit")
def audit_observation(observation_id: int, body: AuditIn, session: Session = Depends(get_session)):
    observation = _observation(session, observation_id)
    try:
        return generate_audit(session, observation, _review_date(session, body.date), ReviewAssistant(), body.force)
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    except AuditBusy as error:
        raise HTTPException(409, str(error)) from None
    except AuditUnavailable as error:
        raise HTTPException(503, str(error)) from None


class ReminderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date
    action: Literal["read", "snooze", "reset"]
    snooze_until: Optional[date] = None


@router.put("/reminders/{reminder_key}")
def update_reminder(reminder_key: str, body: ReminderIn, session: Session = Depends(get_session)):
    target = _review_date(session, body.date)
    reminders = ReviewAssistant().dashboard(session, target, include_entries=False)["reminders"]
    if not any(item["key"] == reminder_key for item in reminders):
        raise HTTPException(404, "提醒已变化，请刷新后查看")
    until = None
    if body.action == "snooze":
        if body.snooze_until is None or not target < body.snooze_until <= target + timedelta(days=30):
            raise HTTPException(400, "暂缓日期须在所选日期之后的 30 天内")
        until = body.snooze_until
    elif body.action == "reset":
        until = target
    session.add(ReviewReminderState(reminder_key=reminder_key, effective_date=target, snooze_until=until))
    session.commit()
    return {"saved": True}


def _parse_date(d: Optional[str]) -> Optional[date]:
    if d:
        return parse_iso_date(d)
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
    try:
        limit_count = service.sync_limit_daily(target, session, strict=True)
        dragon_count = service.sync_dragon_tiger_daily(target, session, strict=True)
    except RuntimeError:
        session.rollback()
        raise HTTPException(503, "复盘数据暂时无法同步，未能确认成功，请稍后重试")
    if limit_count == 0 or dragon_count == 0:
        raise HTTPException(503, "部分复盘数据尚未发布或未返回有效结果，已保留已有数据，请稍后重试")
    return {"trade_date": target.isoformat(), "limit_count": limit_count, "dragon_count": dragon_count}
