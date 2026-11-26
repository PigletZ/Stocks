"""人工明确选择的纠正说明；可撤回，保留来源，不冒充已核验行情事实。"""
import json
from sqlalchemy import func
from sqlmodel import select
from ..models import ReviewAudit,ReviewCorrection
from .review_records import chunks


def latest_for_audit(session,audit_id,as_of):
    rows=session.exec(select(ReviewCorrection).where(ReviewCorrection.audit_id==audit_id,ReviewCorrection.effective_date<=as_of)
        .order_by(ReviewCorrection.effective_date,ReviewCorrection.id)).all()
    return {(row.section,row.item_index):row for row in rows}


def apply_selection(session,audit,body,feedback_id):
    if body.reuse_for_audit is None:return False
    old=latest_for_audit(session,audit.id,body.date).get((body.section,body.item_index))
    active=body.reuse_for_audit
    if (not old and not active) or (old and old.active==active and (not active or old.note==body.comment)):
        return False
    session.add(ReviewCorrection(observation_id=audit.observation_id,audit_id=audit.id,feedback_id=feedback_id if active else old.feedback_id,
        section=body.section,item_index=body.item_index,effective_date=body.date,active=active,note=body.comment if active else old.note))
    return True


def attach_selection(view,record):
    active=bool(record and record.active)
    return {**view,'reuse_for_audit':active,'reused_note':record.note if active else None,
        'correction_id':record.id if record else None}


def history(session,audit_id,as_of,section,item_index,page=1):
    from .review_records import query_count
    statement=select(ReviewCorrection).where(ReviewCorrection.audit_id==audit_id,ReviewCorrection.effective_date<=as_of,
        ReviewCorrection.section==section,ReviewCorrection.item_index==item_index).order_by(ReviewCorrection.effective_date.desc(),ReviewCorrection.id.desc())
    total=query_count(session,statement);pages=max(1,(total+9)//10);page=min(page,pages)
    rows=session.exec(statement.offset((page-1)*10).limit(10)).all()
    return {'items':[{'id':row.id,'active':row.active,'note':row.note,'date':str(row.effective_date),
        'feedback_id':row.feedback_id,'created_at':row.created_at.isoformat()+'+00:00'} for row in rows],
        'total':total,'page':page,'pages':pages}


def facts_for_observations(session,ids,as_of,limit=8):
    output={}
    for batch in chunks(ids):
        ranked=select(ReviewCorrection.id.label('record_id'),func.row_number().over(
            partition_by=(ReviewCorrection.audit_id,ReviewCorrection.section,ReviewCorrection.item_index),
            order_by=(ReviewCorrection.effective_date.desc(),ReviewCorrection.id.desc())).label('position'))\
            .where(ReviewCorrection.observation_id.in_(batch),ReviewCorrection.effective_date<=as_of).subquery()
        rows=session.exec(select(ReviewCorrection,ReviewAudit).select_from(ReviewCorrection).join(ranked,ReviewCorrection.id==ranked.c.record_id)
            .join(ReviewAudit,ReviewAudit.id==ReviewCorrection.audit_id)
            .where(ranked.c.position==1,ReviewCorrection.active==True,ReviewAudit.review_date<=as_of,ReviewAudit.observation_id==ReviewCorrection.observation_id)
            .order_by(ReviewCorrection.effective_date.desc(),ReviewCorrection.id.desc())).all()
        grouped={}
        for row,audit in rows:grouped.setdefault(row.observation_id,[]).append((row,audit))
        for obs_id,records in grouped.items():
            facts=[]
            for row,audit in records[:limit]:
                opinion=json.loads(audit.result_json).get(row.section,[])
                if row.item_index>=len(opinion):continue
                facts.append({'id':f'correction-{row.id}','label':'人工确认的纠正说明（需按当前证据复核）',
                    'value':{'manual_note':row.note,'source_opinion':opinion[row.item_index]['text'],
                        'source_audit_id':row.audit_id,'source_feedback_id':row.feedback_id,'audit_date':str(audit.review_date),
                        'effective_date':str(row.effective_date),'confirmed_at':row.created_at.isoformat()+'+00:00',
                        'source_type':'人工意见，非行情事实或模型训练结果'}})
            if len(records)>limit:
                facts.append({'id':'correction-coverage','label':'纠正说明取样范围','value':{'included':limit,'total':len(records),
                    'note':'按所属日期及实际版本取最近说明，更多记录仍保留。'}})
            output[obs_id]=facts
    return output
