import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from db.schema import init_market_database

from backtest.funding_basis_model import (
    ensure_schema as ensure_funding_basis_schema,
    insert_basis_snapshot,
    upsert_funding_rate,
)

from backtest.delta_neutral_funding_backtest import ensure_schema as ensure_backtest_schema

from backtest.funding_walk_forward_validation import (
    build_walk_forward_splits,
    final_summary_verdict,
    run_funding_walk_forward_validation,
    stability_score,
    summarize_variant,
    variant_specs,
    ensure_schema,
)


class FundingWalkForwardValidationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "funding_walk_forward_test.db")

        init_market_database(self.db_path)
        ensure_funding_basis_schema(self.db_path)
        ensure_backtest_schema(self.db_path)
        ensure_schema(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def seed_funding_rows(self, source, rate="0.0002", count=30):
        for index in range(count):
            day = index + 1
            timestamp = f"2026-07-{day:02d}T00:00:00Z"

            upsert_funding_rate(
                db_path=self.db_path,
                exchange="Binance Futures",
                symbol="ETHUSDT",
                funding_time_utc=timestamp,
                funding_rate=Decimal(rate),
                interval_hours=Decimal("8"),
                source=source,
            )

    def seed_basis_snapshot(self, source, basis="0.20"):
        spot_price = Decimal("3100")
        perp_mark_price = spot_price * (Decimal("1") + Decimal(basis) / Decimal("100"))

        insert_basis_snapshot(
            db_path=self.db_path,
            spot_exchange="Binance Spot",
            perp_exchange="Binance Futures",
            symbol="ETHUSDT",
            timestamp_utc="2026-07-01T00:00:00Z",
            spot_price=spot_price,
            perp_mark_price=perp_mark_price,
            annualized_funding_rate_pct=Decimal("21.90"),
            open_interest=Decimal("1000000"),
            source=source,
            assumptions={
                "research_only": True,
                "run_label": source,
            },
        )

    def test_variant_specs_exist(self):
        specs = variant_specs()

        self.assertEqual(len(specs), 3)
        self.assertEqual(specs[0]["name"], "funding_wf")

    def test_build_walk_forward_splits(self):
        funding_rows = [
            {
                "funding_time_utc": f"2026-07-{index + 1:02d}T00:00:00Z",
                "funding_rate": Decimal("0.0002"),
                "annualized_rate_pct": Decimal("21.90"),
            }
            for index in range(20)
        ]

        splits = build_walk_forward_splits(
            funding_rows=funding_rows,
            train_size=10,
            test_size=5,
            step_size=5,
        )

        self.assertEqual(len(splits), 2)
        self.assertEqual(splits[0]["split_index"], 0)
        self.assertEqual(len(splits[0]["train"]), 10)
        self.assertEqual(len(splits[0]["test"]), 5)

    def test_final_summary_verdict_requires_splits(self):
        verdict = final_summary_verdict(
            splits_tested=1,
            go_splits=1,
            total_trades=3,
            avg_net_return_pct=Decimal("1"),
            worst_drawdown_pct=Decimal("0"),
            avg_profit_factor=Decimal("2"),
            min_splits=2,
            min_pass_ratio=Decimal("0.60"),
            min_total_trades=1,
            min_avg_net_return_pct=Decimal("0"),
            max_drawdown_limit_pct=Decimal("5"),
            min_avg_profit_factor=Decimal("1"),
        )

        self.assertEqual(verdict, "INSUFFICIENT_SPLITS")

    def test_stability_score_rewards_go_splits(self):
        rejected = stability_score(
            splits_tested=2,
            go_splits=0,
            no_go_splits=2,
            total_trades=1,
            avg_net_return_pct=Decimal("-1"),
            total_net_return_pct=Decimal("-2"),
            worst_drawdown_pct=Decimal("1"),
            avg_profit_factor=Decimal("0"),
            avg_positive_funding_ratio_pct=Decimal("50"),
            avg_annualized_funding_pct=Decimal("3"),
            final_verdict_value="NO_GO_WALK_FORWARD_STABILITY",
        )

        approved = stability_score(
            splits_tested=2,
            go_splits=2,
            no_go_splits=0,
            total_trades=4,
            avg_net_return_pct=Decimal("1"),
            total_net_return_pct=Decimal("2"),
            worst_drawdown_pct=Decimal("0"),
            avg_profit_factor=Decimal("2"),
            avg_positive_funding_ratio_pct=Decimal("100"),
            avg_annualized_funding_pct=Decimal("20"),
            final_verdict_value="GO_FOR_RESEARCH",
        )

        self.assertGreater(approved, rejected)

    def test_summarize_variant(self):
        rows = [
            {
                "final_verdict": "GO_FOR_RESEARCH",
                "trades_count": 1,
                "net_return_pct": Decimal("0.20"),
                "avg_trade_return_pct": Decimal("0.20"),
                "max_drawdown_pct": Decimal("0"),
                "profit_factor": Decimal("999"),
                "positive_funding_ratio_pct": Decimal("100"),
                "avg_annualized_funding_pct": Decimal("21.90"),
            },
            {
                "final_verdict": "GO_FOR_RESEARCH",
                "trades_count": 1,
                "net_return_pct": Decimal("0.15"),
                "avg_trade_return_pct": Decimal("0.15"),
                "max_drawdown_pct": Decimal("0"),
                "profit_factor": Decimal("999"),
                "positive_funding_ratio_pct": Decimal("100"),
                "avg_annualized_funding_pct": Decimal("21.90"),
            },
        ]

        summary = summarize_variant(
            rows=rows,
            min_splits=2,
            min_pass_ratio=Decimal("0.60"),
            min_total_trades=1,
            min_avg_net_return_pct=Decimal("0"),
            max_drawdown_limit_pct=Decimal("5"),
            min_avg_profit_factor=Decimal("1"),
        )

        self.assertEqual(summary["final_verdict"], "GO_FOR_RESEARCH")

    def test_run_funding_walk_forward_validation_inserts_results(self):
        self.seed_funding_rows("test_source", rate="0.0002", count=30)
        self.seed_basis_snapshot("test_source")

        result = run_funding_walk_forward_validation(
            db_path=self.db_path,
            symbol="ETHUSDT",
            source_run_label="test_source",
            run_label="test_funding_wf",
            train_size=10,
            test_size=5,
            step_size=5,
            min_splits=2,
            min_pass_ratio=Decimal("0.60"),
            min_total_trades=1,
            min_avg_net_return_pct=Decimal("0"),
            max_drawdown_limit_pct=Decimal("5"),
            min_avg_profit_factor=Decimal("1"),
        )

        self.assertEqual(result["symbol"], "ETHUSDT")
        self.assertEqual(result["variant_count"], len(variant_specs()))
        self.assertEqual(result["splits_tested"], 4)
        self.assertEqual(result["split_results_created"], 12)
        self.assertEqual(result["summary_results_created"], 3)
        self.assertIn("best_variant", result)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        split_count = cur.execute("""
        SELECT COUNT(*)
        FROM funding_walk_forward_split_results
        WHERE run_label = 'test_funding_wf'
        """).fetchone()[0]

        summary_count = cur.execute("""
        SELECT COUNT(*)
        FROM funding_walk_forward_summary
        WHERE run_label = 'test_funding_wf'
        """).fetchone()[0]

        conn.close()

        self.assertEqual(split_count, 12)
        self.assertEqual(summary_count, 3)


if __name__ == "__main__":
    unittest.main()
