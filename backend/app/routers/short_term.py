from datetime import date
from typing import Literal,Optional
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict
from sqlmodel import Session,select
from ..database import get_session
from ..models import ShortTermEvent,ShortTermEventState
from ..services.etf_service import EtfService
from ..services.runtime_state import RuntimeStore,utc_now
from ..services.short_term import SH,ShortTermSettings,current_events,event_view,minute_phase,preferences
from ..services.system_maintenance import MaintenanceBusy,start_maintenance,maintenance_status

router=APIRouter()


def checked_day(day):
    if day>utc_now().astimezone(SH).date():raise HTTPException(400,'不能读取未来日期的异动')
    return day


@router.get('/status')
def status(target:date=Query(...,alias='date'),mode:Literal['close','intraday']='close'):
    checked_day(target);store=RuntimeStore();now=utc_now();phase,_=minute_phase(now=now)
    report=store.read('short-term-intraday' if mode=='intraday' else 'short-term-close-'+target.strftime('%Y%m%d'))
    if mode=='intraday' and report and report.get('date')!=str(target):report=None
    return {'date':str(target),'mode':mode,'phase':phase,'coverage':report,'settings':preferences(store).model_dump(mode='json'),
        'job':maintenance_status('short_term',store),'capability':store.read('short-term-capability'),
        'note':'盘中仅覆盖自选/关注池，使用已闭合分钟；市场情绪和板块为收盘检测。关闭页面后后台仍扫描，事件保存在服务器。'}


@router.put('/settings')
def save_settings(body:ShortTermSettings):
    RuntimeStore().write('short-term-preferences',{'values':body.model_dump(mode='json'),'updated_at':utc_now().isoformat()})
    return body.model_dump(mode='json')


@router.post('/scan',status_code=202)
def scan():
    try:return start_maintenance('short_term')
    except MaintenanceBusy as error:raise HTTPException(409,str(error)) from None
    except OSError:raise HTTPException(503,'扫描任务提交结果尚未确认，请刷新后核对。') from None


@router.get('/events')
def events(target:date=Query(...,alias='date'),mode:Literal['close','intraday']='close',
           category:Literal['all','market','sector','stock','etf']='all',include_resolved:bool=False,
           unread_only:bool=False,include_ignored:bool=False,page:int=Query(1,ge=1),session:Session=Depends(get_session)):
    checked_day(target)
    rows=current_events(session,target,mode)
    keys={row.event_key for row in rows}
    states=session.exec(select(ShortTermEventState).where(ShortTermEventState.event_key.in_(keys),
        ShortTermEventState.effective_date<=target).order_by(ShortTermEventState.effective_date,ShortTermEventState.id)).all() if keys else []
    state_map={(row.event_key,row.cycle):row for row in states}
    items=[event_view(row,state_map.get((row.event_key,row.cycle))) for row in rows]
    counts={'active':sum(row['active'] for row in items),'unread':sum(row['unread'] for row in items),'total':len(items)}
    items=[row for row in items if (include_resolved or row['active']) and (include_ignored or not row['ignored'])
        and (not unread_only or row['unread']) and (category=='all' or row['category']==category)]
    items.sort(key=lambda row:(not row['unread'],-row['level'],-row['id']))
    total=len(items);pages=max(1,(total+14)//15);page=min(page,pages)
    return {'date':str(target),'mode':mode,'counts':counts,'items':items[(page-1)*15:page*15], 'total':total,'page':page,'pages':pages}


@router.get('/unread')
def unread(target:date=Query(...,alias='date'),mode:Literal['close','intraday']='close',session:Session=Depends(get_session)):
    return events(target,mode,'all',False,False,True,1,session)['counts']


class StateInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    date:date
    action:Literal['read','ignore','reset']


@router.put('/events/{event_id}/state')
def change_state(event_id:int,body:StateInput,session:Session=Depends(get_session)):
    checked_day(body.date);row=session.get(ShortTermEvent,event_id)
    if row is None or row.business_date!=body.date:raise HTTPException(404,'所选日期没有这条异动')
    session.add(ShortTermEventState(event_key=row.event_key,cycle=row.cycle,level=row.level,action=body.action,effective_date=body.date))
    session.commit();return {'saved':True}


@router.get('/events/{event_id}/history')
def history(event_id:int,target:date=Query(...,alias='date'),page:int=Query(1,ge=1),session:Session=Depends(get_session)):
    checked_day(target);row=session.get(ShortTermEvent,event_id)
    if row is None or row.business_date>target:raise HTTPException(404,'截至所选日期没有这条异动')
    records=session.exec(select(ShortTermEvent).where(ShortTermEvent.event_key==row.event_key,ShortTermEvent.business_date<=target)
        .order_by(ShortTermEvent.id.desc())).all()
    pages=max(1,(len(records)+9)//10);page=min(page,pages)
    return {'items':[event_view(record) for record in records[(page-1)*10:page*10]],'total':len(records),'page':page,'pages':pages}
