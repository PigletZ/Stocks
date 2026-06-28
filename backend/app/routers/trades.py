from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from datetime import datetime
from typing import List

from ..database import get_session
from ..models import Trade
from ..services.trade_service import TradeService

router = APIRouter()


@router.get("/session/{session_id}", response_model=List[Trade])
def list_trades(session_id: str, session: Session = Depends(get_session)):
    service = TradeService(session)
    return service.list_trades(session_id)


@router.post("/session/{session_id}")
def create_trade(
    session_id: str,
    stock_code: str,
    direction: str,
    price: float,
    quantity: int,
    timestamp: datetime,
    session: Session = Depends(get_session),
):
    service = TradeService(session)
    try:
        trade = service.record_trade(
            session_id=session_id,
            stock_code=stock_code,
            direction=direction,
            price=price,
            quantity=quantity,
            timestamp=timestamp,
        )
        return trade
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/session/{session_id}/position")
def get_position(
    session_id: str,
    current_price: Optional[float] = None,
    session: Session = Depends(get_session),
):
    service = TradeService(session)
    return service.get_position(session_id, current_price)


@router.post("/session/{session_id}/init")
def init_session(
    session_id: str,
    stock_code: str,
    start_date: datetime,
    end_date: datetime,
    initial_capital: float = 100000.0,
    session: Session = Depends(get_session),
):
    service = TradeService(session)
    return service.get_or_create_session(
        session_id=session_id,
        stock_code=stock_code,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
    )
