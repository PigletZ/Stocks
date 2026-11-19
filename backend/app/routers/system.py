from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..database import get_session
from ..services.system_service import SystemService
from ..services.system_diagnostics import SystemDiagnostics, DiagnosticBusy
from ..services.runtime_state import SystemPreferences, save_preferences

router = APIRouter()


@router.get("/status")
def get_system_status(session: Session = Depends(get_session)):
    """只读本地运行状态，不主动请求 Tushare。"""
    service = SystemService()
    return service.get_status(session)


@router.post("/diagnostics")
def check_data_source():
    try:
        return SystemDiagnostics().run()
    except DiagnosticBusy as error:
        raise HTTPException(status_code=409, detail=str(error))
    except OSError:
        raise HTTPException(status_code=503, detail="诊断结果无法保存，请检查服务端存储空间和目录权限")


@router.put("/preferences")
def update_preferences(preferences: SystemPreferences):
    try:
        return save_preferences(preferences)
    except OSError:
        raise HTTPException(status_code=503, detail="配置保存失败，请检查服务端存储空间和目录权限")
