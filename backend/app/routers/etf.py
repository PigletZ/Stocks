from datetime import datetime, date
from fastapi import APIRouter, HTTPException, Query
from threading import RLock
from ..services.etf_dashboard import build_dashboard
from typing import Optional

from ..services.etf_service import EtfService
from ..validation import parse_iso_date

router = APIRouter()
service = EtfService()
_dashboard_lock = RLock()


def _read_etf(load):
    try:
        with _dashboard_lock:
            return load()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))


@router.get("/dashboard")
def get_dashboard(target_date: Optional[date] = Query(None, alias="date"), min_amount: float = Query(10000000, ge=0)):
    return _read_etf(lambda: build_dashboard(service, target_date, min_amount))


def _parse_date(d: Optional[str]) -> date:
    if d:
        return parse_iso_date(d)
    return date.today()


@router.get("/list")
def get_etf_list(
    sort_by: str = Query("change_pct", description="排序字段: change_pct / amount / close / name / category"),
    order: str = Query("desc", description="排序方向: asc / desc"),
    offset: int = Query(0, description="分页偏移，默认 0"),
    limit: int = Query(50, description="每页条数，默认 50"),
    category: str = Query("", description="品类筛选，默认全部"),
):
    """ETF 列表，支持品类筛选、排序与分页。默认按涨幅降序。"""
    return _read_etf(lambda: service.fetch_etf_list(
        sort_by=sort_by,
        order=order,
        offset=offset,
        limit=limit,
        category=category,
    ))


@router.get("/categories")
def get_etf_categories():
    """获取 ETF 品类列表"""
    return _read_etf(service.fetch_etf_categories)


@router.get("/gainers")
def get_etf_gainers(
    date: Optional[str] = Query(None, description="日期 YYYY-MM-DD，默认今天"),
    category: str = Query("", description="品类筛选，默认全部"),
    min_amount: float = Query(1000.0, description="2日榜最低成交额（万元），用于过滤迷你基/妖基"),
):
    """ETF 2日/5日/10日/20日涨幅榜前 10。支持品类筛选，数据未更新时自动回退到最近交易日。"""
    target_date = _parse_date(date)
    return _read_etf(lambda: service.fetch_etf_gainers(target_date, category=category, min_amount=min_amount))
