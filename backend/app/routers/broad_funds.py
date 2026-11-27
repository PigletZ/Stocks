from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlmodel import Session

from ..database import get_session
from ..models import BroadFundBatch
from ..services import broad_funds as service, broad_fund_evidence as evidence
from ..services.runtime_state import RuntimeStore, utc_now
from ..services.short_term import SH
from ..services.system_maintenance import MaintenanceBusy, maintenance_status, start_maintenance

router = APIRouter()


def checked(day):
    day = day or utc_now().astimezone(SH).date()
    if day > utc_now().astimezone(SH).date():raise HTTPException(400,'不能读取未来日期')
    return day


@router.get('')
def dashboard(target: Optional[date] = Query(None,alias='date'), batch_id:Optional[int]=Query(None,ge=1), session: Session = Depends(get_session)):
    target = checked(target)
    batch = session.get(BroadFundBatch,batch_id) if isinstance(batch_id,int) else service.find_batch(session,target)
    if isinstance(batch_id,int) and (not batch or batch.start_date>target):raise HTTPException(404,'该日期没有所选快照')
    return {'data': service.summarize(batch,target) if batch else None, 'requested_date': str(target),
        'job': maintenance_status('broad_funds'), 'check': RuntimeStore().read('broad-funds-check'),
        'evidence_count': evidence.listing(session,target)['total'],
        'basket': [{'ts_code': code, 'group': group} for code,group in service.BASKET.items()]}


@router.get('/history/{code}')
def history(code:str,target:date=Query(...,alias='date'),batch_id:Optional[int]=Query(None,ge=1),session:Session=Depends(get_session)):
    result = service.history(session,checked(target),code,batch_id)
    if result is None:raise HTTPException(404,'所选日期或快照没有该基金记录')
    return result


@router.post('/sync',status_code=202)
def sync():
    try:return start_maintenance('broad_funds')
    except MaintenanceBusy as error:raise HTTPException(409,str(error)) from None
    except OSError:raise HTTPException(503,'提交结果尚未确认，请刷新状态核对。') from None


@router.get('/evidence')
def list_evidence(target:date=Query(...,alias='date'),page:int=Query(1,ge=1),include_withdrawn:bool=False,
                  scope:str=Query('',max_length=30),session:Session=Depends(get_session)):
    try:return evidence.listing(session,checked(target),page,include_withdrawn,scope)
    except ValueError as error:raise HTTPException(400,str(error)) from None


@router.post('/evidence')
def create_evidence(body:evidence.EvidenceInput,session:Session=Depends(get_session)):
    return evidence.save(session,body)


class WithdrawIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    reason:str=Field(min_length=1,max_length=500)

    @field_validator('reason')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('请说明撤回原因')
        return value.strip()


@router.post('/evidence/{record_id}/withdraw')
def withdraw(record_id:int,body:WithdrawIn,session:Session=Depends(get_session)):
    result=evidence.withdraw(session,record_id,body.reason)
    if result is None:raise HTTPException(404,'披露登记不存在')
    return result


@router.get('/evidence/{record_id}/history')
def evidence_history(record_id:int,page:int=Query(1,ge=1),session:Session=Depends(get_session)):
    result=evidence.history(session,record_id,page)
    if result is None:raise HTTPException(404,'披露登记不存在')
    return result
