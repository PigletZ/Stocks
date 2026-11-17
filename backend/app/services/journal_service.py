"""复盘日志与交易台账服务：笔记 CRUD、交易 CRUD、FIFO 持仓与盈亏统计。"""

import json
import logging
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from math import isfinite
from typing import Dict, List, Optional

from sqlmodel import Session, select, delete

from ..models import ReviewNote, Stock, StockDailyQuote, TradeJournal


logger = logging.getLogger(__name__)


class JournalService:
    """复盘日志 / 交易台账服务"""

    @staticmethod
    def _utc(value):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value

    def _validate_history(self, session, code, replaced_id=None, candidate=None):
        rows = list(session.exec(select(TradeJournal).where(TradeJournal.stock_code == code)).all())
        rows = [r for r in rows if r.id != replaced_id]
        if candidate is not None and candidate.stock_code == code:
            rows.append(candidate)
        qty = 0
        for row in sorted(rows, key=lambda r: (self._utc(r.traded_at), r.id or 2**63)):
            if row.direction not in ('buy', 'sell') or not isfinite(row.price) or row.price <= 0 or row.quantity <= 0 or not isfinite(row.fee) or row.fee < 0:
                raise ValueError("交易方向、正价格/数量和非负费用必须有效")
            qty += row.quantity if row.direction == 'buy' else -row.quantity
            if qty < 0:
                raise ValueError("该操作会使历史持仓出现超卖，请先补齐真实买入记录")

    # ==================== 复盘笔记 ====================

    def get_note(self, note_date: date, session: Session) -> dict:
        note = session.exec(
            select(ReviewNote).where(ReviewNote.note_date == note_date)
        ).first()
        if not note:
            return {"note_date": note_date.isoformat(), "content": "", "codes": []}
        return {
            "note_date": note.note_date.isoformat(),
            "content": note.content,
            "codes": json.loads(note.codes_json) if note.codes_json else [],
            "updated_at": note.updated_at.isoformat(),
        }

    def upsert_note(self, note_date: date, content: str, codes: List[str], session: Session) -> dict:
        note = session.exec(
            select(ReviewNote).where(ReviewNote.note_date == note_date)
        ).first()
        if note:
            note.content = content
            note.codes_json = json.dumps(codes, ensure_ascii=False)
            note.updated_at = datetime.utcnow()
        else:
            note = ReviewNote(
                note_date=note_date,
                content=content,
                codes_json=json.dumps(codes, ensure_ascii=False),
            )
        session.add(note)
        session.commit()
        return self.get_note(note_date, session)

    def delete_note(self, note_date: date, session: Session) -> bool:
        note = session.exec(
            select(ReviewNote).where(ReviewNote.note_date == note_date)
        ).first()
        if not note:
            return False
        session.delete(note)
        session.commit()
        return True

    def list_note_dates(self, year: int, month: int, session: Session) -> List[str]:
        """指定月份有笔记的日期列表（日历标记用）"""
        start = date(year, month, 1)
        end = date(year + (month == 12), month % 12 + 1, 1)
        rows = session.exec(
            select(ReviewNote.note_date).where(
                ReviewNote.note_date >= start,
                ReviewNote.note_date < end,
                ReviewNote.content != "",
            )
        ).all()
        return [d.isoformat() for d in rows]

    # ==================== 交易台账 ====================

    def list_trades(
        self,
        session: Session,
        code: Optional[str] = None,
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> List[dict]:
        stmt = select(TradeJournal).order_by(TradeJournal.traded_at.desc(), TradeJournal.id.desc())
        if code:
            stmt = stmt.where(TradeJournal.stock_code == code)
        if start:
            stmt = stmt.where(TradeJournal.traded_at >= datetime.combine(start, datetime.min.time()) - timedelta(hours=8))
        if end:
            stmt = stmt.where(TradeJournal.traded_at <= datetime.combine(end, datetime.max.time()) - timedelta(hours=8))
        trades = session.exec(stmt).all()
        names = self._stock_names(session, {t.stock_code for t in trades})
        return [self._trade_item(t, names.get(t.stock_code, "")) for t in trades]

    def create_trade(
        self,
        stock_code: str,
        direction: str,
        price: float,
        quantity: int,
        fee: float,
        traded_at: datetime,
        note: Optional[str],
        session: Session,
    ) -> dict:
        if direction not in ("buy", "sell"):
            raise ValueError("direction 必须是 buy 或 sell")
        if price <= 0 or quantity <= 0:
            raise ValueError("价格和数量必须大于 0")
        trade = TradeJournal(
            stock_code=stock_code,
            direction=direction,
            price=price,
            quantity=quantity,
            fee=fee,
            traded_at=self._utc(traded_at),
            note=note,
        )
        self._validate_history(session, stock_code, candidate=trade)
        session.add(trade)
        session.commit()
        session.refresh(trade)
        names = self._stock_names(session, {stock_code})
        return self._trade_item(trade, names.get(stock_code, ""))

    def update_trade(self, trade_id: int, session: Session, **fields) -> Optional[dict]:
        trade = session.get(TradeJournal, trade_id)
        if not trade:
            return None
        candidate = TradeJournal(**trade.model_dump())
        for k in ("stock_code", "direction", "price", "quantity", "fee", "traded_at", "note"):
            if k in fields and fields[k] is not None:
                setattr(candidate, k, fields[k])
        candidate.traded_at = self._utc(candidate.traded_at)
        for code in {trade.stock_code, candidate.stock_code}:
            self._validate_history(session, code, trade_id, candidate)
        for k in ("stock_code", "direction", "price", "quantity", "fee", "traded_at", "note"):
            setattr(trade, k, getattr(candidate, k))
        session.add(trade)
        session.commit()
        session.refresh(trade)
        names = self._stock_names(session, {trade.stock_code})
        return self._trade_item(trade, names.get(trade.stock_code, ""))

    def delete_trade(self, trade_id: int, session: Session) -> bool:
        trade = session.get(TradeJournal, trade_id)
        if not trade:
            return False
        self._validate_history(session, trade.stock_code, trade_id)
        session.delete(trade)
        session.commit()
        return True

    def list_trade_dates(self, year: int, month: int, session: Session) -> List[str]:
        """指定月份有交易的日期列表（日历标记用）"""
        start = datetime(year, month, 1) - timedelta(hours=8)
        end = datetime(year + (month == 12), month % 12 + 1, 1) - timedelta(hours=8)
        rows = session.exec(
            select(TradeJournal.traded_at).where(
                TradeJournal.traded_at >= start,
                TradeJournal.traded_at < end,
            )
        ).all()
        return sorted({(d + timedelta(hours=8)).date().isoformat() for d in rows})

    # ==================== 持仓与盈亏（FIFO） ====================

    def _fifo_compute(self, trades: List[TradeJournal]):
        """FIFO 计算：返回 (各代码剩余持仓, 各代码已实现盈亏, 逐笔卖出盈亏列表)。

        剩余持仓成本含买入费用摊薄；卖出盈亏 = 卖价-成本 乘数量 - 卖出费用。
        """
        lots: Dict[str, deque] = defaultdict(deque)
        realized: Dict[str, float] = defaultdict(float)
        sell_pnls: List[float] = []

        for t in sorted(trades, key=lambda x: (x.traded_at, x.id)):
            if t.direction == "buy":
                # 每手成本 = 价格 + 费用摊薄到每股
                per_share_cost = t.price + (t.fee / t.quantity if t.quantity else 0)
                lots[t.stock_code].append([t.quantity, per_share_cost])
            else:
                remain = t.quantity
                pnl = -t.fee
                while remain > 0 and lots[t.stock_code]:
                    lot = lots[t.stock_code][0]
                    take = min(remain, lot[0])
                    pnl += (t.price - lot[1]) * take
                    lot[0] -= take
                    remain -= take
                    if lot[0] == 0:
                        lots[t.stock_code].popleft()
                if remain > 0:
                    # 数据不完整（历史买入未录入），超出部分按 0 成本计
                    realized[t.stock_code] = None
                    pnl = None
                    logger.warning("交易台账 %s 卖出超出已记录持仓 %d 股", t.stock_code, remain)
                if realized[t.stock_code] is not None and pnl is not None:
                    realized[t.stock_code] += pnl
                sell_pnls.append(pnl)
        return lots, realized, sell_pnls

    def _position_before(self, session: Session, code: str, before: datetime) -> int:
        trades = session.exec(
            select(TradeJournal).where(
                TradeJournal.stock_code == code,
                TradeJournal.traded_at < before,
            )
        ).all()
        qty = 0
        for t in trades:
            qty += t.quantity if t.direction == "buy" else -t.quantity
        return max(qty, 0)

    def get_position_map(self, session: Session) -> Dict[str, dict]:
        """各代码当前持仓（FIFO 成本），供自选股等模块合并展示"""
        trades = session.exec(select(TradeJournal)).all()
        lots, realized, _ = self._fifo_compute(trades)
        result = {}
        for code, q in lots.items():
            qty = sum(l[0] for l in q)
            if qty > 0:
                cost = sum(l[0] * l[1] for l in q) / qty
                result[code] = {
                    "quantity": qty,
                    "cost_price": round(cost, 3),
                    "realized_pnl": round(realized.get(code, 0.0), 2) if realized.get(code, 0.0) is not None else None,
                }
        return result

    def get_positions(self, session: Session) -> List[dict]:
        """当前持仓（FIFO 成本）+ 最新收盘浮动盈亏"""
        pos_map = self.get_position_map(session)
        codes = set(pos_map.keys())
        names = self._stock_names(session, codes)
        closes = self._latest_closes(session, codes)

        result = []
        for code, pos in pos_map.items():
            qty = pos["quantity"]
            cost = pos["cost_price"]
            close = closes.get(code)
            unrealized = (close - cost) * qty if close is not None else None
            result.append({
                "code": code,
                "name": names.get(code, ""),
                "quantity": qty,
                "cost_price": cost,
                "close": close,
                "unrealized_pnl": round(unrealized, 2) if unrealized is not None else None,
                "unrealized_pct": round((close / cost - 1) * 100, 2) if close is not None and cost > 0 else None,
                "realized_pnl": pos["realized_pnl"],
            })
        result.sort(key=lambda x: -(x["unrealized_pnl"] or 0))
        return result

    def get_stats(self, session: Session) -> dict:
        """整体盈亏统计"""
        trades = session.exec(select(TradeJournal)).all()
        _, realized, sell_pnls = self._fifo_compute(trades)
        total_realized = sum(realized.values()) if all(v is not None for v in realized.values()) else None
        valid = [p for p in sell_pnls if p is not None]
        wins = sum(1 for p in valid if p > 0)
        losses = sum(1 for p in valid if p <= 0)
        total_fee = sum(t.fee for t in trades)
        return {
            "total_realized": round(total_realized, 2) if total_realized is not None else None,
            "incomplete_sell_count": len(sell_pnls) - len(valid),
            "win_count": wins,
            "loss_count": losses,
            "win_rate": round(wins / len(valid) * 100, 1) if valid else None,
            "sell_count": len(sell_pnls),
            "buy_count": sum(1 for t in trades if t.direction == "buy"),
            "total_fee": round(total_fee, 2),
        }

    # ==================== 内部工具 ====================

    @staticmethod
    def _stock_names(session: Session, codes) -> Dict[str, str]:
        if not codes:
            return {}
        stocks = session.exec(select(Stock).where(Stock.code.in_(list(codes)))).all()
        return {s.code: s.name for s in stocks}

    @staticmethod
    def _latest_closes(session: Session, codes) -> Dict[str, float]:
        result = {}
        for code in codes:
            row = session.exec(
                select(StockDailyQuote.close)
                .where(StockDailyQuote.stock_code == code)
                .order_by(StockDailyQuote.trade_date.desc())
                .limit(1)
            ).first()
            if row is not None:
                result[code] = row
        return result

    @staticmethod
    def _trade_item(t: TradeJournal, name: str) -> dict:
        return {
            "id": t.id,
            "code": t.stock_code,
            "name": name,
            "direction": t.direction,
            "price": t.price,
            "quantity": t.quantity,
            "amount": round(t.price * t.quantity, 2),
            "fee": t.fee,
            "traded_at": t.traded_at.replace(tzinfo=timezone.utc).isoformat(),
            "note": t.note,
        }
