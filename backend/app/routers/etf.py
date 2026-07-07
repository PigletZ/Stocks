from datetime import datetime, date
from fastapi import APIRouter, Query
from typing import Optional

from ..services.etf_service import EtfService

router = APIRouter()


def _parse_date(d: Optional[str]) -> date:
    if d:
        return datetime.strptime(d, "%Y-%m-%d").date()
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
    service = EtfService()
    return service.fetch_etf_list(
        sort_by=sort_by,
        order=order,
        offset=offset,
        limit=limit,
        category=category,
    )


@router.get("/categories")
def get_etf_categories():
    """获取 ETF 品类列表"""
    service = EtfService()
    return service.fetch_etf_categories()


@router.get("/gainers")
def get_etf_gainers(
    date: Optional[str] = Query(None, description="日期 YYYY-MM-DD，默认今天"),
    category: str = Query("", description="品类筛选，默认全部"),
):
    """ETF 5日/10日/20日涨幅榜前 10。支持品类筛选，数据未更新时自动回退到最近交易日。"""
    target_date = _parse_date(date)
    service = EtfService()
    return service.fetch_etf_gainers(target_date, category=category)
