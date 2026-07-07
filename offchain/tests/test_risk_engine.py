import unittest

from risk.risk_engine import RiskLimits, TradeSimulation, evaluate_trade


class RiskEngineTest(unittest.TestCase):
    def setUp(self):
        self.limits = RiskLimits(
            min_net_profit_wei=1_000_000_000_000_000,
            max_slippage_bps=50,
            max_gas_to_gross_bps=3_000,
            min_success_bps=8_500,
            min_score=70,
        )

    def test_safe_trade_is_approved(self):
        trade = TradeSimulation(
            gross_profit_wei=5_000_000_000_000_000,
            gas_cost_wei=1_000_000_000_000_000,
            flash_fee_wei=500_000_000_000_000,
            slippage_cost_wei=500_000_000_000_000,
            slippage_bps=20,
            estimated_success_bps=9_500,
        )

        decision = evaluate_trade(trade, self.limits)

        self.assertTrue(decision.approved)
        self.assertEqual(decision.score, 100)
        self.assertEqual(decision.net_profit_wei, 3_000_000_000_000_000)
        self.assertEqual(decision.reasons, [])

    def test_trade_rejected_when_costs_exceed_profit(self):
        trade = TradeSimulation(
            gross_profit_wei=2_000_000_000_000_000,
            gas_cost_wei=1_500_000_000_000_000,
            flash_fee_wei=400_000_000_000_000,
            slippage_cost_wei=300_000_000_000_000,
            slippage_bps=30,
            estimated_success_bps=9_000,
        )

        decision = evaluate_trade(trade, self.limits)

        self.assertFalse(decision.approved)
        self.assertIn("net profit below minimum threshold", decision.reasons)
        self.assertIn("total costs exceed or equal gross profit", decision.reasons)

    def test_trade_rejected_for_high_slippage(self):
        trade = TradeSimulation(
            gross_profit_wei=6_000_000_000_000_000,
            gas_cost_wei=1_000_000_000_000_000,
            flash_fee_wei=400_000_000_000_000,
            slippage_cost_wei=2_000_000_000_000_000,
            slippage_bps=120,
            estimated_success_bps=9_200,
        )

        decision = evaluate_trade(trade, self.limits)

        self.assertFalse(decision.approved)
        self.assertIn("slippage exceeds maximum allowed bps", decision.reasons)

    def test_trade_rejected_for_low_confidence(self):
        trade = TradeSimulation(
            gross_profit_wei=8_000_000_000_000_000,
            gas_cost_wei=1_000_000_000_000_000,
            flash_fee_wei=500_000_000_000_000,
            slippage_cost_wei=500_000_000_000_000,
            slippage_bps=25,
            estimated_success_bps=6_500,
        )

        decision = evaluate_trade(trade, self.limits)

        self.assertFalse(decision.approved)
        self.assertIn("estimated success probability too low", decision.reasons)


if __name__ == "__main__":
    unittest.main()
