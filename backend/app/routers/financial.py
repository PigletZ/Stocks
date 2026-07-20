# -*- coding: utf-8 -*-
"""财务分析路由：刷新、对比、报表原文、亮点榜。"""
import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from ..database import get_session
from ..models import FinHighlight, Stock
from ..services.financial_service import FinancialService

router = APIRouter()

MAX_CODES = 10
VALID_STMT_TYPES = ("income", "balance", "cashflow")


class CodesRequest(BaseModel):
    codes: List[str]


def _validate_codes(codes: List[str], session: Session) -> List[str]:
    """校验股票代码：存在、非银行股、数量上限。返回规范化后的代码列表。"""
    codes = [c.strip() for c in codes if c and c.strip()]
    # 去重保持顺序
    codes = list(dict.fromkeys(codes))
    if not codes:
        raise HTTPException(status_code=400, detail="请至少选择 1 只股票")
    if len(codes) > MAX_CODES:
        raise HTTPException(status_code=400, detail=f"最多支持 {MAX_CODES} 只股票对比")
    for code in codes:
        stock = session.exec(select(Stock).where(Stock.code == code)).first()
        if stock is None:
            raise HTTPException(status_code=400, detail=f"股票 {code} 不存在")
        if stock.industry and "银行" in stock.industry:
            raise HTTPException(status_code=400, detail=f"暂不支持银行股：{stock.name}({code})")
    return codes


@router.post("/refresh")
def refresh_financial(req: CodesRequest, session: Session = Depends(get_session)):
    """对指定股票执行轻量校验，有新公告则三表全量回源"""
    codes = _validate_codes(req.codes, session)
    service = FinancialService()
    refreshed = service.ensure_fresh(codes, session)
    return {"refreshed": refreshed, "codes": codes}


@router.post("/compare")
def compare_financial(req: CodesRequest, session: Session = Depends(get_session)):
    """多股对比主接口：派生指标 + 体检卡 + 亮点/风险标签 + 雷达图数据"""
    codes = _validate_codes(req.codes, session)
    service = FinancialService()
    return service.get_compare(codes, session)


@router.get("/statements")
def get_statements(
    code: str = Query(..., description="股票代码"),
    type: str = Query("income", description="报表类型: income / balance / cashflow"),
    session: Session = Depends(get_session),
):
    """单股报表原文（全科目 × 展示期，含同比）"""
    if type not in VALID_STMT_TYPES:
        raise HTTPException(status_code=400, detail=f"报表类型仅支持: {', '.join(VALID_STMT_TYPES)}")
    _validate_codes([code], session)
    service = FinancialService()
    # 报表查看前同样做一次轻量校验，保证披露当天可见
    service.ensure_fresh([code], session)
    return service.get_statements(code, type, session)


@router.get("/highlight-rank")
def get_highlight_rank(
    date: Optional[str] = Query(None, description="榜单日期 YYYY-MM-DD，默认最新"),
    limit: int = Query(100, description="返回前 N 名（榜单落库前 300 名）"),
    session: Session = Depends(get_session),
):
    """亮点 Top 榜（由每日增量任务重算，见 scripts/sync_fin_daily.py）"""
    if date:
        try:
            stat_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式应为 YYYY-MM-DD")
    else:
        latest = session.exec(
            select(FinHighlight).order_by(FinHighlight.stat_date.desc()).limit(1)
        ).first()
        if latest is None:
            return {"date": None, "items": []}
        stat_date = latest.stat_date

    limit = max(1, min(limit, 300))
    rows = session.exec(
        select(FinHighlight)
        .where(FinHighlight.stat_date == stat_date)
        .order_by(FinHighlight.rank)
        .limit(limit)
    ).all()
    codes = [r.code for r in rows]
    stocks = session.exec(select(Stock).where(Stock.code.in_(codes))).all() if codes else []
    smap = {s.code: s for s in stocks}
    items = []
    for r in rows:
        s = smap.get(r.code)
        items.append({
            "rank": r.rank,
            "code": r.code,
            "name": s.name if s else r.code,
            "industry": s.industry if s else None,
            "good_count": r.good_count,
            "risk_count": r.risk_count,
            "tags": json.loads(r.tags_json or "[]"),
            "metrics": json.loads(r.metrics_json or "{}"),
        })
    return {"date": stat_date.isoformat(), "items": items}
