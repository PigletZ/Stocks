import os
import unittest
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

with patch.dict(os.environ, {
    "AUTH_USERNAME": "test-user", "AUTH_PASSWORD": "test-password-only",
    "AUTH_SECRET": "test-signing-key-only-" * 3,
}):
    from app.backtest.piglet_backtest import PigletBacktestEngine, PigletBacktestParams
    from app.backtest.metrics import compute_backtest_metrics


class FakeProvider:
    def __init__(self, third_close=10):
        self.days = [date(2026, 1, 5) + timedelta(days=i) for i in range(5)]
        self.third_close = third_close
        self.requests = []

    def get_trade_dates_in_range(self, start, end):
        self.requests.append((start, end))
        return [d for d in self.days if start <= d <= end]

    def get_daily_ohlc(self, code, day):
        return {"open": 10, "close": self.third_close if day == self.days[2] and code == "A" else 10}


class BacktestTests(unittest.TestCase):
    def run_engine(self, third_close=10, hold_days=5):
        provider = FakeProvider(third_close)
        params = PigletBacktestParams(initial_capital=100000, commission_rate=0,
                                      max_positions=3, max_per_day=1, hold_days=hold_days)
        engine = PigletBacktestEngine(None, params, provider=provider)

        def select(day, session):
            codes = {provider.days[0]: "A", provider.days[1]: "B"}
            code = codes.get(day)
            return [SimpleNamespace(code=code, buy_price=10, raw_data={})] if code else []

        engine.strategy = SimpleNamespace(select=select)
        curve, trades = engine.run(provider.days[0], provider.days[2])
        return provider, curve, trades

    def test_opening_order_size_does_not_use_same_day_close(self):
        _, _, baseline = self.run_engine(third_close=10)
        _, _, changed = self.run_engine(third_close=100)
        self.assertEqual([t["quantity"] for t in baseline], [t["quantity"] for t in changed])
        self.assertEqual(changed[-1]["quantity"], 3300)

    def test_end_date_marks_open_positions_without_future_trades(self):
        provider, curve, trades = self.run_engine(third_close=12)
        self.assertEqual(provider.requests, [(provider.days[0], provider.days[2])])
        self.assertEqual([s.date for s in curve], provider.days[:3])
        self.assertEqual([t["direction"] for t in trades], ["buy", "buy"])
        self.assertEqual(curve[-1].cash, 34000)
        self.assertEqual(curve[-1].total_value, 106600)
        metrics = compute_backtest_metrics(curve, trades)
        self.assertEqual(metrics["num_sell_trades"], 0)
        self.assertEqual(metrics["total_return_pct"], 6.6)

    def test_sell_before_buy_and_equity_reconcile(self):
        _, curve, trades = self.run_engine(hold_days=1)
        self.assertEqual([t["direction"] for t in trades], ["buy", "sell", "buy"])
        self.assertEqual(curve[-1].total_value, 100000)
        self.assertEqual(sum(t["pnl"] or 0 for t in trades), 0)

    def test_empty_calendar_returns_no_trades(self):
        provider = FakeProvider()
        engine = PigletBacktestEngine(None, PigletBacktestParams(), provider=provider)
        self.assertEqual(engine.run(date(2025, 1, 1), date(2025, 1, 2)), ([], []))


if __name__ == "__main__":
    unittest.main()
