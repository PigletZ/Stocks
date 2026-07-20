# -*- coding: utf-8 -*-
"""财务分析路由：刷新、对比、报表原文。"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from ..database import get_session
from ..models import Stock
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
