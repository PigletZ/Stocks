"""分页关注清单、独立详情及跨日审阅历史。"""
from datetime import date, timedelta

from sqlmodel import select

from ..models import ReviewAudit
from .review_ai import ai_status
from .review_assistant import ReviewAssistant, audit_view
from .review_records import latest_records, observation_query, query_count
from .review_workbench import ReviewWorkbench
from .review_feedback import attach_feedback


def page_records(session, statement, page, page_size):
    total = query_count(session, statement)
    pages = max(1, (total+page_size-1)//page_size)
    page = min(page, pages)
    return session.exec(statement.offset((page-1)*page_size).limit(page_size)).all(), {
        "total": total, "page": page, "page_size": page_size, "pages": pages}


def audit_summary(audit):
    return {key: audit[key] for key in ("id", "date", "created_at", "model", "stale", "historical", "changes")}


def list_observations(session, as_of, status="pending", search="", page=1, page_size=20, assistant=None):
    records, paging = page_records(session, observation_query(as_of, status, search), page, page_size)
    assistant = assistant or ReviewAssistant()
    contexts = assistant.contexts(session, records, as_of)
    items = ReviewWorkbench.observations(session, as_of, records=records)
    for item in items:
        current = contexts[item["id"]]
        audit = current["audit_record"]
        item["evaluation"] = current["evaluation"]
        item["rule_description"] = current["rule"]["description"] if current["rule"] else None
        item["last_audit"] = audit_summary(audit_view(audit, current["context_hash"], current["context"])) if audit else None
    return {"date": str(as_of), "items": items, **paging}


def observation_detail(session, observation, as_of, assistant=None):
    assistant = assistant or ReviewAssistant()
    current = assistant.context(session, observation, as_of)
    latest = latest_records(session, ReviewAudit, [observation.id], ReviewAudit.review_date, as_of).get(observation.id)
    return {"observation": ReviewWorkbench.observations(session, as_of, records=[observation])[0],
            "entry": {"observation_id": observation.id, "code": observation.stock_code, "rule": current["rule"],
                      "evaluation": current["evaluation"],
                      "audit": attach_feedback(session, audit_view(latest, current["context_hash"], current["context"]), as_of) if latest else None},
            "ai": ai_status()}


def audit_history(session, observation, as_of, page=1, page_size=5):
    records, paging = page_records(session, select(ReviewAudit).where(
        ReviewAudit.observation_id == observation.id, ReviewAudit.review_date <= as_of)
        .order_by(ReviewAudit.review_date.desc(), ReviewAudit.id.desc()), page, page_size)
    return {"items": [{"id": row.id, "date": str(row.review_date), "created_at": row.created_at.isoformat()+"+00:00",
                       "model": row.model} for row in records], **paging}


def trading_deadlines(base, calendar):
    end = base+timedelta(days=90)
    cursor, following = base, []
    while cursor <= end and len(following) < 10:
        until = min(end, date(cursor.year, 12, 31))
        following.extend(day for day in calendar(cursor, until) if base < day <= until)
        following = sorted(set(following))
        cursor = until+timedelta(days=1)
    if len(following) < 10:
        raise RuntimeError("官方日历不足以确认后续十个交易日，请稍后重试或手动选择日期")
    return {"date": str(base), "options": [{"days": n, "date": str(following[n-1])} for n in (3, 5, 10)]}
