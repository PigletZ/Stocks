from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..database import get_session
from ..services.system_service import SystemService

router = APIRouter()


@router.get("/status")
def get_system_status(session: Session = Depends(get_session)):
    """系统状态：数据库体积、缓存表新鲜度、定时任务日志健康度"""
    service = SystemService()
    return service.get_status(session)
