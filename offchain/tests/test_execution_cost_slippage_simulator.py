import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from db.schema import init_market_database

from backtest.funding_basis_model import (
    ensure_schema as ensure_funding_basis_schema,
    insert_basis_snapshot,
)

from backtest.execution_cost_slippage_simulator import (
    bps_to_pct,
    calculate_expected_funding_edge_pct,
    calculate_leg_execution_cost_pct,
    calculate_participation_rate_pct,
    ensure_schema,
    estimate_slippage_bps,
    evaluate_execution_scenario,
    run_execution_cost_slippage_simulator,
)


class ExecutionCostSlippageSimulatorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "execution_cost_slippage_test.db")

        init_market_database(self.db_path)
        ensure_funding_basis_schema(self.db_path)
        ensure_schema(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def seed_basis_snapshot(self, source="test_source", annualized="50"):
        insert_basis_snapshot(
            db_path=self.db_path,
            spot_exchange="Binance Spot",
            perp_exchange="Binance Futures",
            symbol="ETHUSDT",
            timestamp_utc="2026-07-08T00:00:00Z",
            spot_price=Decimal("3000"),
            perp_mark_price=Decimal("3003"),
            annualized_funding_rate_pct=Decimal(annualized),
            open_interest=Decimal("1000000"),
            source=source,
            assumptions={
                "research_only": True,
                "run_label": source,
            },
        )

    def test_bps_to_pct(self):
        self.assertEqual(bps_to_pct(Decimal("10")), Decimal("0.1"))
        self.assertEqual(bps_to_pct(Decimal("1")), Decimal("0.01"))

    def test_participation_rate(self):
        participation = calculate_participation_rate_pct(
            order_notional_usd=Decimal("10000"),
            liquidity_notional_usd=Decimal("5000000"),
        )

        self.assertEqual(participation, Decimal("0.200"))

    def test_slippage_estimation(self):
        slippage = estimate_slippage_bps(
            participation_rate_pct=Decimal("0.20"),
            base_slippage_bps=Decimal("1"),
            impact_slope_bps=Decimal("2"),
            max_participation_rate_pct=Decimal("2"),
        )

        self.assertEqual(slippage, Decimal("1.20"))

    def test_leg_execution_cost(self):
        cost, penalty = calculate_leg_execution_cost_pct(
            fee_bps=Decimal("2"),
            spread_bps=Decimal("1"),
            slippage_bps=Decimal("1.2"),
            participation_rate_pct=Decimal("0.20"),
            max_participation_rate_pct=Decimal("2"),
            liquidity_penalty_multiplier=Decimal("1.5"),
        )

        self.assertEqual(cost, Decimal("0.074"))
        self.assertEqual(penalty, Decimal("0"))

    def test_expected_funding_edge(self):
        edge = calculate_expected_funding_edge_pct(
            annualized_funding_rate_pct=Decimal("50"),
            holding_days=30,
            perp_order_notional_usd=Decimal("10000"),
            gross_notional_usd=Decimal("20000"),
        )

        self.assertEqual(edge, Decimal("2.054794520547945205479452054794520547945"))

    def test_evaluate_execution_scenario_go(self):
        context = {
            "spot_price": Decimal("3000"),
            "perp_mark_price": Decimal("3003"),
            "basis_pct": Decimal("0.10"),
            "annualized_funding_rate_pct": Decimal("50"),
        }

        spec = {
            "spot_order_notional_usd": Decimal("10000"),
            "perp_order_notional_usd": Decimal("10000"),
            "spot_liquidity_notional_usd": Decimal("10000000"),
            "perp_liquidity_notional_usd": Decimal("10000000"),
            "spot_fee_bps": Decimal("1"),
            "perp_fee_bps": Decimal("1"),
            "spot_spread_bps": Decimal("1"),
            "perp_spread_bps": Decimal("1"),
            "base_slippage_bps": Decimal("0.5"),
            "impact_slope_bps": Decimal("1"),
            "max_participation_rate_pct": Decimal("2"),
            "liquidity_penalty_multiplier": Decimal("1.5"),
            "holding_days": 30,
            "max_combined_cost_pct": Decimal("0.25"),
            "min_edge_to_cost_ratio": Decimal("2"),
            "min_net_expected_edge_pct": Decimal("0.50"),
        }

        result = evaluate_execution_scenario(
            context=context,
            spec=spec,
        )

        self.assertEqual(result["final_verdict"], "GO_FOR_RESEARCH")
        self.assertTrue(result["net_expected_edge_pct"] > Decimal("1"))

    def test_run_execution_cost_slippage_simulator_inserts_results(self):
        self.seed_basis_snapshot("test_source", annualized="50")

        result = run_execution_cost_slippage_simulator(
            db_path=self.db_path,
            symbol="ETHUSDT",
            source_run_label="test_source",
            run_label="test_execution_cost",
        )

        self.assertEqual(result["symbol"], "ETHUSDT")
        self.assertEqual(result["scenarios_tested"], 3)
        self.assertEqual(result["results_created"], 3)
        self.assertEqual(result["summary_results_created"], 1)
        self.assertIn("best_scenario", result)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        result_count = cur.execute("""
        SELECT COUNT(*)
        FROM execution_cost_slippage_results
        WHERE run_label = 'test_execution_cost'
        """).fetchone()[0]

        summary_count = cur.execute("""
        SELECT COUNT(*)
        FROM execution_cost_slippage_summary
        WHERE run_label = 'test_execution_cost'
        """).fetchone()[0]

        conn.close()

        self.assertEqual(result_count, 3)
        self.assertEqual(summary_count, 1)


if __name__ == "__main__":
    unittest.main()
