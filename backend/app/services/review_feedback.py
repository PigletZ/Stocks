"""人工反馈是对模型意见的标注，不是模型正确性的客观标签。"""
import json
from datetime import date
from typing import Literal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func
from sqlmodel import select

from ..models import ReviewAudit, ReviewAuditFeedback
from .review_workbench import today_shanghai

SECTIONS = Literal['supporting_evidence', 'counter_evidence', 'uncertainties', 'next_checks']


class FeedbackInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date
    section: SECTIONS
    item_index: int = Field(ge=0, le=3)
    rating: Literal['helpful', 'misunderstood', 'insufficient']
    comment: str = Field(default="", max_length=1000)
    reuse_for_audit:Optional[bool]=None

    @model_validator(mode="after")
    def require_correction_reason(self):
        self.comment = self.comment.strip()
        if self.rating != 'helpful' and not self.comment:
            raise ValueError("请说明理解错误或证据不足的具体依据")
        if self.reuse_for_audit and (self.rating=='helpful' or not self.comment):
            raise ValueError('纠错复用需要明确标注理解有误或证据不足，并填写说明')
        return self


def feedback_view(row, revisions=1):
    return {"id": row.id, "audit_id": row.audit_id, "section": row.section, "item_index": row.item_index,
            "rating": row.rating, "comment": row.comment, "date": str(row.effective_date),
            "created_at": row.created_at.isoformat()+"+00:00", "revisions": revisions,'reuse_for_audit':False,'reused_note':None,'correction_id':None}


def latest_query(as_of, audit_id=None):
    statement = select(ReviewAuditFeedback.id.label('record_id'), func.row_number().over(
        partition_by=(ReviewAuditFeedback.audit_id, ReviewAuditFeedback.section, ReviewAuditFeedback.item_index),
        order_by=(ReviewAuditFeedback.effective_date.desc(), ReviewAuditFeedback.id.desc())).label('position'),
        func.count().over(partition_by=(ReviewAuditFeedback.audit_id, ReviewAuditFeedback.section, ReviewAuditFeedback.item_index)).label('revisions'))\
        .where(ReviewAuditFeedback.effective_date <= as_of)
    if audit_id is not None:
        statement = statement.where(ReviewAuditFeedback.audit_id == audit_id)
    return statement.subquery()


def attach_feedback(session, audit_view, as_of):
    from .review_corrections import attach_selection,latest_for_audit
    ranked = latest_query(as_of, audit_view['id'])
    rows = session.exec(select(ReviewAuditFeedback, ranked.c.revisions).join(ranked, ReviewAuditFeedback.id == ranked.c.record_id)
                         .where(ranked.c.position == 1)).all()
    selections=latest_for_audit(session,audit_view['id'],as_of)
    return {**audit_view, 'feedback': [attach_selection(feedback_view(row,revisions),selections.get((row.section,row.item_index))) for row,revisions in rows]}


def save_feedback(session, audit, body):
    from .review_corrections import apply_selection,attach_selection,latest_for_audit
    if not audit.review_date <= body.date <= today_shanghai():
        raise ValueError("反馈所属日期须在原审阅日期与今天之间")
    result = json.loads(audit.result_json)
    if body.item_index >= len(result.get(body.section, [])):
        raise ValueError("这条审阅意见不存在，请刷新后核对")
    latest = attach_feedback(session, {'id': audit.id}, body.date)['feedback']
    previous = next((row for row in latest if row['section'] == body.section and row['item_index'] == body.item_index), None)
    duplicate=previous and previous['rating']==body.rating and previous['comment']==body.comment and previous['date']==str(body.date)
    if duplicate:
        row=session.get(ReviewAuditFeedback,previous['id'])
        revisions=previous['revisions']
    else:
        row = ReviewAuditFeedback(audit_id=audit.id, section=body.section, item_index=body.item_index,
            rating=body.rating, comment=body.comment, effective_date=body.date)
        session.add(row);session.flush()
        revisions=(previous['revisions'] if previous else 0)+1
    changed=apply_selection(session,audit,body,row.id)
    session.commit()
    session.refresh(row)
    selection=latest_for_audit(session,audit.id,body.date).get((body.section,body.item_index))
    return {**attach_selection(feedback_view(row,revisions),selection),'context_changed':changed}


def summary(session, as_of):
    ranked = latest_query(as_of)
    rows = session.exec(select(ReviewAuditFeedback.rating, func.count(), func.count(func.distinct(ReviewAuditFeedback.audit_id)))
        .join(ranked, ReviewAuditFeedback.id == ranked.c.record_id).where(ranked.c.position == 1)
        .group_by(ReviewAuditFeedback.rating)).all()
    counts = {rating: count for rating, count, audits in rows}
    return {'rated_count': sum(counts.values()), 'helpful': counts.get('helpful', 0),
            'misunderstood': counts.get('misunderstood', 0), 'insufficient': counts.get('insufficient', 0),
            'note': '这是已反馈意见的人工标注分布，不代表模型整体准确率。'}


def history(session, audit, as_of, section, item_index, page=1):
    from .review_records import query_count
    statement = select(ReviewAuditFeedback).where(ReviewAuditFeedback.audit_id == audit.id,
        ReviewAuditFeedback.effective_date <= as_of, ReviewAuditFeedback.section == section,
        ReviewAuditFeedback.item_index == item_index).order_by(ReviewAuditFeedback.effective_date.desc(), ReviewAuditFeedback.id.desc())
    total = query_count(session, statement)
    pages = max(1, (total+9)//10)
    page = min(page, pages)
    rows = session.exec(statement.offset((page-1)*10).limit(10)).all()
    return {'items': [feedback_view(row) for row in rows], 'total': total, 'page': page, 'pages': pages}
