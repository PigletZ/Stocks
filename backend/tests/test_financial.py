import os
import unittest
from datetime import date
from unittest.mock import patch

with patch.dict(os.environ, {
    "AUTH_USERNAME": "test-user", "AUTH_PASSWORD": "test-password-only",
    "AUTH_SECRET": "test-signing-key-only-" * 3,
}):
    from app.services.financial_service import FinancialService
    from app.models import FinIncome, FinCashflow


class FinancialTests(unittest.TestCase):
    def test_loss_transition_states(self):
        cases = [(10, -20, "扭亏为盈"), (-10, -20, "亏损收窄"),
                 (-30, -20, "亏损扩大"), (-10, 20, "由盈转亏"),
                 (10, None, "缺少同期数据"), (None, 20, "数据缺失")]
        for current, base, expected in cases:
            with self.subTest(current=current, base=base):
                self.assertEqual(FinancialService._profit_state(current, base), expected)

    def test_nonpositive_profit_does_not_make_negative_cashflow_look_good(self):
        d = date(2026, 9, 30)
        inc = FinIncome(stock_code="000001", end_date=d, n_income_attr_p=-10)
        cash = FinCashflow(stock_code="000001", end_date=d, n_cashflow_act=-20)
        metric = FinancialService()._build_metrics({d: inc}, {}, {d: cash}, [d])[d.isoformat()]
        self.assertIsNone(metric["ncf_ratio"])

    def test_turnaround_retains_uncomparable_percentage_and_explains_state(self):
        now, before = date(2026, 9, 30), date(2025, 9, 30)
        income = {now: FinIncome(stock_code="000001", end_date=now, n_income_attr_p=10),
                  before: FinIncome(stock_code="000001", end_date=before, n_income_attr_p=-20)}
        metric = FinancialService()._build_metrics(income, {}, {}, [now])[now.isoformat()]
        self.assertIsNone(metric["net_profit_yoy"])
        self.assertEqual(metric["net_profit_state"], "扭亏为盈")

    def test_missing_radar_dimensions_are_not_zero_scores(self):
        result = FinancialService._build_radar([("000001", "Example", {})])
        self.assertTrue(all(v is None for v in result["series"][0]["values"]))


if __name__ == "__main__":
    unittest.main()
