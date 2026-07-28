from datetime import datetime, date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session

from ..database import get_session
from ..services.screener_service import ScreenerService

router = APIRouter()


class Condition(BaseModel):
    field: str
    op: str
    value: float


class RunRequest(BaseModel):
    conditions: List[Condition]
    trade_date: Optional[str] = None
    apply_filters: bool = True


class PresetIn(BaseModel):
    name: str
    conditions: List[Condition]


@router.post("/run")
def run_screener(req: RunRequest, session: Session = Depends(get_session)):
    """执行条件筛选（AND 组合）"""
    service = ScreenerService()
    d = datetime.strptime(req.trade_date, "%Y-%m-%d").date() if req.trade_date else None
    try:
        return service.run(
            [c.model_dump() for c in req.conditions],
            d,
            session,
            apply_filters=req.apply_filters,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/presets")
def list_presets(session: Session = Depends(get_session)):
    """列出保存的筛选预设"""
    service = ScreenerService()
    return service.list_presets(session)


@router.post("/presets")
def create_preset(req: PresetIn, session: Session = Depends(get_session)):
    """保存筛选预设（保存后可在策略选股页作为自定义策略使用）"""
    service = ScreenerService()
    try:
        return service.create_preset(
            req.name, [c.model_dump() for c in req.conditions], session
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/presets/{preset_id}")
def delete_preset(preset_id: int, session: Session = Depends(get_session)):
    service = ScreenerService()
    if not service.delete_preset(preset_id, session):
        raise HTTPException(status_code=404, detail="预设不存在")
    return {"message": "已删除"}
