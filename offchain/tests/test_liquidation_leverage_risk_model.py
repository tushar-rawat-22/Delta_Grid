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

from backtest.liquidation_leverage_risk_model import (
    calculate_buffer_after_stress_pct,
    calculate_funding_reversal_loss_pct,
    calculate_max_safe_leverage,
    calculate_short_liquidation_price,
    calculate_stressed_mark_price,
    ensure_schema,
    evaluate_liquidation_scenario,
    risk_verdict,
    run_liquidation_leverage_risk_model,
)


class LiquidationLeverageRiskModelTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "liquidation_risk_test.db")

        init_market_database(self.db_path)
        ensure_funding_basis_schema(self.db_path)
        ensure_schema(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def seed_basis_snapshot(self, source="test_source"):
        insert_basis_snapshot(
            db_path=self.db_path,
            spot_exchange="Binance Spot",
            perp_exchange="Binance Futures",
            symbol="ETHUSDT",
            timestamp_utc="2026-07-08T00:00:00Z",
            spot_price=Decimal("3100"),
            perp_mark_price=Decimal("3106.20"),
            annualized_funding_rate_pct=Decimal("21.90"),
            open_interest=Decimal("1000000"),
            source=source,
            assumptions={
                "research_only": True,
                "run_label": source,
            },
        )

    def test_short_liquidation_price(self):
        price, buffer = calculate_short_liquidation_price(
            entry_mark_price=Decimal("100"),
            leverage=Decimal("2"),
            maintenance_margin_rate_pct=Decimal("0.50"),
        )

        self.assertEqual(price, Decimal("149.500"))
        self.assertEqual(buffer, Decimal("49.50"))

    def test_stressed_mark_and_buffer(self):
        stressed, move = calculate_stressed_mark_price(
            entry_mark_price=Decimal("100"),
            adverse_spot_shock_pct=Decimal("20"),
            adverse_basis_shock_pct=Decimal("2"),
        )

        buffer = calculate_buffer_after_stress_pct(
            short_liquidation_price=Decimal("149.50"),
            stressed_mark_price=stressed,
        )

        self.assertEqual(stressed, Decimal("122.00"))
        self.assertEqual(move, Decimal("22"))
        self.assertTrue(buffer > Decimal("20"))

    def test_funding_reversal_loss(self):
        loss = calculate_funding_reversal_loss_pct(
            funding_reversal_annualized_pct=Decimal("12"),
            holding_days=30,
        )

        self.assertEqual(loss, Decimal("0.9863013698630136986301369863013698630137"))

    def test_max_safe_leverage(self):
        safe = calculate_max_safe_leverage(
            maintenance_margin_rate_pct=Decimal("0.50"),
            adverse_spot_shock_pct=Decimal("25"),
            adverse_basis_shock_pct=Decimal("1.50"),
            required_buffer_after_stress_pct=Decimal("5"),
        )

        self.assertTrue(safe > Decimal("2"))
        self.assertTrue(safe < Decimal("4"))

    def test_risk_verdict_rejects_liquidation_hit(self):
        verdict = risk_verdict(
            liquidation_hit=True,
            leverage=Decimal("2"),
            max_safe_leverage=Decimal("3"),
            buffer_after_stress_pct=Decimal("-1"),
            min_buffer_after_stress_pct=Decimal("5"),
            total_stress_loss_pct=Decimal("2"),
            max_total_stress_loss_pct=Decimal("5"),
        )

        self.assertEqual(verdict, "NO_GO_LIQUIDATION_HIT")

    def test_evaluate_liquidation_scenario(self):
        context = {
            "spot_price": Decimal("3100"),
            "perp_mark_price": Decimal("3106.20"),
            "basis_pct": Decimal("0.20"),
        }

        spec = {
            "leverage": Decimal("2"),
            "maintenance_margin_rate_pct": Decimal("0.50"),
            "adverse_spot_shock_pct": Decimal("25"),
            "adverse_basis_shock_pct": Decimal("1.50"),
            "funding_reversal_annualized_pct": Decimal("15"),
            "holding_days": 30,
            "execution_cost_bps": Decimal("20"),
            "min_buffer_after_stress_pct": Decimal("5"),
            "max_total_stress_loss_pct": Decimal("7"),
        }

        result = evaluate_liquidation_scenario(
            context=context,
            spec=spec,
        )

        self.assertEqual(result["final_verdict"], "GO_FOR_RESEARCH")
        self.assertTrue(result["buffer_after_stress_pct"] > Decimal("5"))

    def test_run_liquidation_leverage_risk_model_inserts_results(self):
        self.seed_basis_snapshot("test_source")

        result = run_liquidation_leverage_risk_model(
            db_path=self.db_path,
            symbol="ETHUSDT",
            source_run_label="test_source",
            run_label="test_liq_model",
        )

        self.assertEqual(result["symbol"], "ETHUSDT")
        self.assertEqual(result["scenarios_tested"], 3)
        self.assertEqual(result["results_created"], 3)
        self.assertEqual(result["summary_results_created"], 1)
        self.assertIn("best_variant", result)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        result_count = cur.execute("""
        SELECT COUNT(*)
        FROM liquidation_leverage_risk_results
        WHERE run_label = 'test_liq_model'
        """).fetchone()[0]

        summary_count = cur.execute("""
        SELECT COUNT(*)
        FROM liquidation_leverage_risk_summary
        WHERE run_label = 'test_liq_model'
        """).fetchone()[0]

        conn.close()

        self.assertEqual(result_count, 3)
        self.assertEqual(summary_count, 1)


if __name__ == "__main__":
    unittest.main()
