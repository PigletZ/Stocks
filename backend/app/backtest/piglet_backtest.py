from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from sqlmodel import Session

from ..strategies.piglet import PigletStrategy
from ..strategies.piglet_provider import TusharePigletProvider


@dataclass
class PigletBacktestParams:
    """回测参数。"""

    window_days: int = 5
    hold_days: int = 5
    max_positions: int = 5
    max_per_day: int = 2
    require_dragon: bool = False
    initial_capital: float = 100000.0
    commission_rate: float = 0.0003


@dataclass
class EquitySnapshot:
    """每日权益快照。"""

    date: date
    cash: float
    market_value: float
    total_value: float


@dataclass
class PendingBuy:
    """收盘后产生、待次日开盘买入的订单。"""

    code: str
    signal_date: date
    base_close: float
    raw_data: Dict = field(default_factory=dict)


@dataclass
class Position:
    """持仓。"""

    code: str
    quantity: int
    buy_price: float
    buy_date: date
    signal_date: date
    hold_days: int
    raw_data: Dict = field(default_factory=dict)


class PigletBacktestEngine:
    """首板不破策略回测引擎。

    规则：收盘后产生信号，下一交易日开盘买入，持有固定交易日后开盘卖出。
    """

    def __init__(self, session: Session, params: PigletBacktestParams):
        self.session = session
        self.params = params
        self.provider = TusharePigletProvider()
        self.strategy = PigletStrategy(
            window_days=params.window_days,
            provider=self.provider,
        )

    def run(
        self, start_date: date, end_date: date
    ) -> Tuple[List[EquitySnapshot], List[Dict]]:
        """执行回测，返回 (权益曲线, 交易记录字典列表)。"""
        signal_dates = self.provider.get_trade_dates_in_range(start_date, end_date)
        if not signal_dates:
            return [], []

        # 需要额外交易日来平仓最后一个买入的仓位
        extra_end = end_date + timedelta(days=self.params.hold_days * 2 + 10)
        all_dates = self.provider.get_trade_dates_in_range(start_date, extra_end)

        date_index = {d: i for i, d in enumerate(all_dates)}

        cash = self.params.initial_capital
        positions: List[Position] = []
        pending_buys: List[PendingBuy] = []
        equity_curve: List[EquitySnapshot] = []
        trades: List[Dict] = []

        for i, d in enumerate(all_dates):
            # ---------- 开盘：先卖后买 ----------
            # 卖出：持仓达到 hold_days 的仓位
            sells_today = [
                p for p in positions
                if date_index.get(d, 0) - date_index.get(p.buy_date, 0) >= p.hold_days
            ]
            for p in sells_today:
                ohlc = self.provider.get_daily_ohlc(p.code, d)
                if ohlc is None:
                    continue
                sell_price = ohlc["open"]
                amount = sell_price * p.quantity
                commission = amount * self.params.commission_rate
                proceeds = amount - commission
                cash += proceeds

                buy_amount = p.buy_price * p.quantity
                buy_commission = buy_amount * self.params.commission_rate
                pnl = (sell_price - p.buy_price) * p.quantity - commission - buy_commission

                trades.append({
                    "stock_code": p.code,
                    "direction": "sell",
                    "quantity": p.quantity,
                    "price": sell_price,
                    "amount": amount,
                    "commission": commission,
                    "trade_date": d,
                    "signal_date": p.signal_date,
                    "hold_days": p.hold_days,
                    "pnl": pnl,
                    "raw": p.raw_data,
                })
                positions.remove(p)

            # 买入：来自上一交易日收盘后的信号
            if pending_buys:
                # 当前总权益（用于目标仓位）
                current_total = cash + self._portfolio_market_value(positions, d)
                target_value = current_total / self.params.max_positions

                executed = 0
                for order in pending_buys:
                    if executed >= self.params.max_per_day:
                        break
                    if len(positions) >= self.params.max_positions:
                        break
                    if any(p.code == order.code for p in positions):
                        continue

                    ohlc = self.provider.get_daily_ohlc(order.code, d)
                    if ohlc is None:
                        continue

                    buy_price = ohlc["open"]
                    quantity = int(target_value / buy_price / 100) * 100
                    if quantity <= 0:
                        continue

                    amount = buy_price * quantity
                    commission = amount * self.params.commission_rate
                    total_cost = amount + commission

                    if total_cost > cash:
                        # 用剩余现金能买多少买多少
                        quantity = int(cash / (buy_price * (1 + self.params.commission_rate)) / 100) * 100
                        if quantity <= 0:
                            continue
                        amount = buy_price * quantity
                        commission = amount * self.params.commission_rate
                        total_cost = amount + commission

                    cash -= total_cost
                    positions.append(
                        Position(
                            code=order.code,
                            quantity=quantity,
                            buy_price=buy_price,
                            buy_date=d,
                            signal_date=order.signal_date,
                            hold_days=self.params.hold_days,
                            raw_data=order.raw_data,
                        )
                    )
                    trades.append({
                        "stock_code": order.code,
                        "direction": "buy",
                        "quantity": quantity,
                        "price": buy_price,
                        "amount": amount,
                        "commission": commission,
                        "trade_date": d,
                        "signal_date": order.signal_date,
                        "hold_days": self.params.hold_days,
                        "pnl": None,
                        "raw": order.raw_data,
                    })
                    executed += 1

                pending_buys = []

            # ---------- 收盘：记录权益曲线 ----------
            market_value = self._portfolio_market_value(positions, d)
            equity_curve.append(
                EquitySnapshot(
                    date=d,
                    cash=cash,
                    market_value=market_value,
                    total_value=cash + market_value,
                )
            )

            # ---------- 收盘后：产生新信号 ----------
            if d in signal_dates:
                picks = self.strategy.select(d, self.session)
                for pick in picks:
                    if self.params.require_dragon and not pick.raw_data.get("has_dragon"):
                        continue
                    if any(p.code == pick.code for p in positions):
                        continue
                    pending_buys.append(
                        PendingBuy(
                            code=pick.code,
                            signal_date=d,
                            base_close=pick.raw_data.get("base_close", pick.buy_price),
                            raw_data=pick.raw_data,
                        )
                    )

        # 过滤权益曲线，只保留原回测区间内的点用于展示
        equity_curve = [s for s in equity_curve if start_date <= s.date <= end_date]
        return equity_curve, trades

    def _portfolio_market_value(self, positions: List[Position], d: date) -> float:
        total = 0.0
        for p in positions:
            ohlc = self.provider.get_daily_ohlc(p.code, d)
            if ohlc is None:
                # 无数据时按买入价估算，避免权益曲线异常跳动
                total += p.buy_price * p.quantity
            else:
                total += ohlc["close"] * p.quantity
        return total
