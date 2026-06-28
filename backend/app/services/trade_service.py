from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from sqlmodel import Session, select

from ..models import Trade, ReplaySession, Bar


class TradeService:
    def __init__(self, session: Session):
        self.session = session

    def record_trade(
        self,
        session_id: str,
        stock_code: str,
        direction: str,
        price: float,
        quantity: int,
        timestamp: datetime,
    ) -> Trade:
        if direction not in ("buy", "sell"):
            raise ValueError("direction must be 'buy' or 'sell'")
        if price <= 0 or quantity <= 0:
            raise ValueError("price and quantity must be positive")

        trade = Trade(
            session_id=session_id,
            stock_code=stock_code,
            direction=direction,
            price=price,
            quantity=quantity,
            timestamp=timestamp,
        )
        self.session.add(trade)
        self.session.commit()
        self.session.refresh(trade)
        return trade

    def list_trades(self, session_id: str) -> List[Trade]:
        return self.session.exec(
            select(Trade)
            .where(Trade.session_id == session_id)
            .order_by(Trade.timestamp)
        ).all()

    def get_position(self, session_id: str, current_price: Optional[float] = None) -> dict:
        """计算指定复盘会话的当前持仓与盈亏"""
        trades = self.list_trades(session_id)
        if not trades:
            return {
                "session_id": session_id,
                "stock_code": "",
                "quantity": 0,
                "avg_cost": 0.0,
                "total_cost": 0.0,
                "market_value": 0.0,
                "unrealized_pnl": 0.0,
                "unrealized_pnl_pct": 0.0,
                "realized_pnl": 0.0,
                "total_pnl": 0.0,
            }

        stock_code = trades[0].stock_code
        quantity = 0
        total_cost = Decimal("0")
        realized_pnl = Decimal("0")

        for trade in trades:
            amount = Decimal(str(trade.price)) * Decimal(str(trade.quantity))
            if trade.direction == "buy":
                quantity += trade.quantity
                total_cost += amount
            else:
                # 卖出：按先进先出计算已实现盈亏
                if quantity > 0:
                    avg_cost = total_cost / Decimal(str(quantity)) if quantity > 0 else Decimal("0")
                    sell_cost = avg_cost * Decimal(str(trade.quantity))
                    realized_pnl += amount - sell_cost
                    quantity -= trade.quantity
                    total_cost -= sell_cost
                else:
                    # 卖出超过持仓，简单处理为全部实现亏损/盈利
                    realized_pnl += amount
                    quantity -= trade.quantity

        avg_cost = total_cost / Decimal(str(quantity)) if quantity > 0 else Decimal("0")
        market_value = Decimal(str(current_price)) * Decimal(str(quantity)) if current_price and quantity > 0 else Decimal("0")
        unrealized_pnl = market_value - total_cost
        unrealized_pnl_pct = (
            (unrealized_pnl / total_cost * 100) if total_cost > 0 else Decimal("0")
        )
        total_pnl = realized_pnl + unrealized_pnl

        return {
            "session_id": session_id,
            "stock_code": stock_code,
            "quantity": quantity,
            "avg_cost": float(avg_cost),
            "total_cost": float(total_cost),
            "market_value": float(market_value),
            "unrealized_pnl": float(unrealized_pnl),
            "unrealized_pnl_pct": float(unrealized_pnl_pct),
            "realized_pnl": float(realized_pnl),
            "total_pnl": float(total_pnl),
        }

    def get_or_create_session(
        self,
        session_id: str,
        stock_code: str,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float = 100000.0,
    ) -> ReplaySession:
        session = self.session.exec(
            select(ReplaySession).where(ReplaySession.session_id == session_id)
        ).first()
        if session:
            return session
        new_session = ReplaySession(
            session_id=session_id,
            stock_code=stock_code,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
        )
        self.session.add(new_session)
        self.session.commit()
        self.session.refresh(new_session)
        return new_session
