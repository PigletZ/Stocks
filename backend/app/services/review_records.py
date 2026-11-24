"""关注记录按业务日期筛选；最新验证在数据库中对齐，不以最近 N 条代替待办。"""
from sqlalchemy import and_, exists, func, or_
from sqlmodel import select

from ..models import ReviewCondition, ReviewObservation, ReviewVerification, Stock

PENDING = ("待验证", "继续观察")


def observation_query(as_of, status="all", search="", reminders=False):
    latest_id = (select(ReviewVerification.id).where(
        ReviewVerification.observation_id == ReviewObservation.id,
        ReviewVerification.review_date <= as_of)
        .order_by(ReviewVerification.review_date.desc(), ReviewVerification.id.desc())
        .limit(1).correlate(ReviewObservation).scalar_subquery())
    statement = (select(ReviewObservation).outerjoin(ReviewVerification, ReviewVerification.id == latest_id)
                 .where(ReviewObservation.observation_date <= as_of))
    pending = func.coalesce(ReviewVerification.verdict, "待验证").in_(PENDING)
    if reminders:
        has_rule = exists(select(ReviewCondition.id).where(
            ReviewCondition.observation_id == ReviewObservation.id, ReviewCondition.effective_date <= as_of))
        statement = statement.where(or_(pending, and_(ReviewVerification.verdict == "符合预期", has_rule)))
    elif status in ("pending", "due"):
        statement = statement.where(pending)
        if status == "due":
            statement = statement.where(ReviewObservation.deadline <= as_of)
    elif status == "completed":
        statement = statement.where(~pending)
    if search.strip():
        keyword = search.strip()
        statement = statement.outerjoin(Stock, Stock.code == ReviewObservation.stock_code).where(or_(
            ReviewObservation.stock_code.contains(keyword, autoescape=True),
            Stock.name.contains(keyword, autoescape=True), ReviewObservation.reason.contains(keyword, autoescape=True)))
    return statement.order_by(ReviewObservation.deadline if status in ("pending", "due") or reminders
                              else ReviewObservation.observation_date.desc(), ReviewObservation.id.desc())


def query_count(session, statement):
    return session.exec(select(func.count()).select_from(statement.order_by(None).subquery())).one()


def chunks(items, size=200):
    for offset in range(0, len(items), size):
        yield items[offset:offset+size]


def latest_records(session, model, ids, date_column, as_of):
    result = {}
    for batch in chunks(ids):
        ranked = select(model.id.label("record_id"), func.row_number().over(
            partition_by=model.observation_id, order_by=(date_column.desc(), model.id.desc())).label("position"))\
            .where(model.observation_id.in_(batch), date_column <= as_of).subquery()
        rows = session.exec(select(model).join(ranked, model.id == ranked.c.record_id)
                            .where(ranked.c.position == 1)).all()
        result.update({row.observation_id: row for row in rows})
    return result
