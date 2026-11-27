"""仅保存用户明确核对的官方链接，不抓取网站，不自动识别或推断资金身份。"""
import json
from datetime import date
from typing import Literal, Optional
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func
from sqlmodel import select

from ..models import BroadFundEvidence
from .broad_funds import BASKET, iso
from .runtime_state import utc_now
from .seat_disclosures import digest, dumps
from .short_term import SH

OFFICIAL_DOMAINS = ('huijin-inv.cn', 'csf.com.cn', 'sse.com.cn', 'szse.cn', 'csrc.gov.cn')


class EvidenceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    subject: str = Field(min_length=1, max_length=100)
    kind: Literal['bought', 'plan', 'holding']
    publication_date: date
    report_date: Optional[date] = None
    codes: list[str] = Field(default_factory=list, max_length=10)
    source_url: str = Field(max_length=2000)
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=1500)
    confirmed: Literal[True]

    @field_validator('subject', 'title', 'summary')
    @classmethod
    def meaningful(cls, value):
        if not value.strip():raise ValueError('请填写具体主体、标题和原文摘要')
        return value.strip()

    @field_validator('source_url')
    @classmethod
    def official_source(cls, value):
        parsed = urlsplit(value.strip())
        host = (parsed.hostname or '').lower()
        if parsed.scheme not in ('https', 'http') or parsed.username or parsed.password or parsed.port not in (None, 80, 443):
            raise ValueError('请提供无账号信息的官方网页链接')
        if not any(host == item or host.endswith('.'+item) for item in OFFICIAL_DOMAINS):
            raise ValueError('当前仅支持汇金、证金、沪深交易所和证监会官方域名；基金报告可使用交易所披露链接')
        return value.strip()

    @model_validator(mode='after')
    def scope_and_dates(self):
        if self.publication_date > utc_now().astimezone(SH).date():raise ValueError('公告日期不能晚于今天')
        if self.kind == 'holding' and not self.report_date:raise ValueError('持仓披露须填写报告期末或持仓截至日')
        if self.report_date and self.report_date > self.publication_date:raise ValueError('资料截至日不能晚于公告日')
        if any(code not in BASKET for code in self.codes):raise ValueError('明确基金范围只能从当前固定篮子中选择')
        self.codes = sorted(set(self.codes))
        return self


def view(row):
    return {'id': row.id, 'key': row.evidence_key, 'subject': row.subject, 'kind': row.kind,
        'publication_date': str(row.publication_date), 'report_date': str(row.report_date) if row.report_date else None,
        'codes': json.loads(row.codes_json), 'source_url': row.source_url, 'title': row.title,
        'summary': row.summary, 'active': row.active, 'withdraw_reason': row.withdraw_reason,
        'created_at': iso(row.created_at), 'verification': '人工登记并核对；系统未抓取或验证原文'}


def latest(session, key):
    return session.exec(select(BroadFundEvidence).where(BroadFundEvidence.evidence_key == key)
        .order_by(BroadFundEvidence.id.desc()).limit(1)).first()


def save(session, body):
    fields = body.model_dump(mode='json', exclude={'confirmed'})
    key = digest(fields)
    prior = latest(session, key)
    if prior and prior.active:return view(prior)
    row = BroadFundEvidence(evidence_key=key, subject=body.subject, kind=body.kind,
        publication_date=body.publication_date, report_date=body.report_date, codes_json=dumps(body.codes),
        source_url=body.source_url, title=body.title, summary=body.summary)
    session.add(row);session.commit();session.refresh(row)
    return view(row)


def listing(session, day, page=1, include_withdrawn=False, scope=''):
    ids = select(func.max(BroadFundEvidence.id)).group_by(BroadFundEvidence.evidence_key)
    statement = select(BroadFundEvidence).where(BroadFundEvidence.id.in_(ids), BroadFundEvidence.publication_date <= day)
    if not include_withdrawn:statement = statement.where(BroadFundEvidence.active == True)
    if scope == 'market':statement = statement.where(BroadFundEvidence.codes_json == '[]')
    elif scope in BASKET:statement = statement.where(BroadFundEvidence.codes_json.contains('"'+scope+'"', autoescape=True))
    elif scope:raise ValueError('披露范围不在固定篮子中')
    count = session.exec(select(func.count()).select_from(statement.subquery())).one()
    pages = max(1, (count+9)//10);page = min(page, pages)
    rows = session.exec(statement.order_by(BroadFundEvidence.publication_date.desc(), BroadFundEvidence.id.desc())
        .offset((page-1)*10).limit(10)).all()
    return {'items': [view(row) for row in rows], 'total': count, 'page': page, 'pages': pages,
        'note': '登记状态采用当前有效版本，公告按所选日筛选；实际核对、撤回时间另列，不作当时已知假设。公告和基金整体估算独立，不能将估算金额归给公告主体。'}


def withdraw(session, record_id, reason):
    row = session.get(BroadFundEvidence, record_id)
    if not row:return None
    current = latest(session, row.evidence_key)
    if not current.active:return view(current)
    values = current.model_dump(exclude={'id', 'created_at'})
    newer = BroadFundEvidence(**{**values, 'active': False, 'withdraw_reason': reason})
    session.add(newer);session.commit();session.refresh(newer)
    return view(newer)


def history(session, record_id, page=1):
    row = session.get(BroadFundEvidence, record_id)
    if not row:return None
    statement = select(BroadFundEvidence).where(BroadFundEvidence.evidence_key == row.evidence_key)
    count = session.exec(select(func.count()).select_from(statement.subquery())).one()
    pages = max(1, (count+9)//10);page = min(page,pages)
    rows = session.exec(statement.order_by(BroadFundEvidence.id.desc()).offset((page-1)*10).limit(10)).all()
    return {'items': [view(row) for row in rows], 'total': count, 'page': page, 'pages': pages}
