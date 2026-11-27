from datetime import date
from typing import Literal, Optional
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from ..database import get_session
from ..models import HotMoneyCatalog
from ..services import hot_money as service
from ..services.runtime_state import RuntimeStore, utc_now
from ..services.short_term import SH
from ..services.system_maintenance import MaintenanceBusy, maintenance_status, start_maintenance

router = APIRouter()


def checked(day):
    if day > utc_now().astimezone(SH).date():
        raise HTTPException(400, '不能读取未来日期的披露')
    return day


@router.get('/dashboard')
def dashboard(target: date = Query(..., alias='date'), scope: Literal['all', 'mine', 'followed'] = 'all',
              period: Literal['day', 'multi'] = 'day', search: str = Query('', max_length=100),
              page: int = Query(1, ge=1), session: Session = Depends(get_session)):
    checked(target)
    result = service.dashboard(session, target, scope, period, search, page)
    result['job'] = maintenance_status('hot_money')
    result['check'] = RuntimeStore().read('seat-checked-'+target.strftime('%Y%m%d'))
    return result


@router.get('/catalog')
def catalog(session: Session = Depends(get_session)):
    row = session.exec(select(HotMoneyCatalog).order_by(HotMoneyCatalog.id.desc()).limit(1)).first()
    return {'id': row.id if row else None, 'created_at': service.iso(row.created_at) if row else None,
            'items': json.loads(row.entries_json) if row else [], 'follows': service.follows(session)}


class FollowIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['person', 'seat']
    subject: str = Field(min_length=1, max_length=200)
    active: bool


@router.put('/follow')
def follow(body: FollowIn, session: Session = Depends(get_session)):
    try:
        return {'items': service.save_follow(session, body.kind, body.subject.strip(), body.active)}
    except ValueError as error:
        raise HTTPException(400, str(error)) from None


@router.get('/stocks/{code}')
def stock_detail(code: str, target: date = Query(..., alias='date'), batch_id: Optional[int] = Query(None, ge=1),
                 session: Session = Depends(get_session)):
    checked(target)
    result = service.stock_detail(session, code, target, batch_id)
    if result is None:
        raise HTTPException(404, '所选日期或版本没有该股票的披露记录')
    return result


@router.get('/history')
def history(target: date = Query(..., alias='date'), kind: Literal['person', 'seat'] = 'person',
            subject: str = Query(..., min_length=1, max_length=200), days: int = Query(20, ge=5, le=20),
            session: Session = Depends(get_session)):
    if days not in (5, 10, 20):
        raise HTTPException(422, '窗口仅支持 5、10、20 个交易日')
    return service.seat_history(session, checked(target), kind, subject, days)


@router.post('/sync', status_code=202)
def sync():
    try:
        return start_maintenance('hot_money')
    except MaintenanceBusy as error:
        raise HTTPException(409, str(error)) from None
    except OSError:
        raise HTTPException(503, '提交结果尚未确认，请刷新任务状态核对。') from None
