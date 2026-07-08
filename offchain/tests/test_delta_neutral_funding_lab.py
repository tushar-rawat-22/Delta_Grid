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

from backtest.delta_neutral_funding_lab import (
    build_lab_result,
    calculate_basis_penalty_pct,
    calculate_edges,
    ensure_schema,
    funding_statistics,
    load_funding_rows,
    run_delta_neutral_funding_lab,
)


class DeltaNeutralFundingLabTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "delta_neutral_funding_lab_test.db")

        init_market_database(self.db_path)
        ensure_funding_basis_schema(self.db_path)
        ensure_schema(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def seed_funding_rows(self, source, rate, count=12):
        for index in range(count):
            timestamp = f"2026-07-{index + 1:02d}T00:00:00Z"

            upsert_funding_rate(
                db_path=self.db_path,
                exchange="Binance Futures",
                symbol="ETHUSDT",
                funding_time_utc=timestamp,
                funding_rate=Decimal(rate),
                interval_hours=Decimal("8"),
                source=source,
            )

    def seed_basis_snapshot(self, source, annualized="21.90", basis="0.20", open_interest="1000000"):
        spot_price = Decimal("3100")
        perp_mark_price = spot_price * (Decimal("1") + Decimal(basis) / Decimal("100"))

        insert_basis_snapshot(
            db_path=self.db_path,
            spot_exchange="Binance Spot",
            perp_exchange="Binance Futures",
            symbol="ETHUSDT",
            timestamp_utc="2026-07-08T00:00:00Z",
            spot_price=spot_price,
            perp_mark_price=perp_mark_price,
            annualized_funding_rate_pct=Decimal(annualized),
            open_interest=None if open_interest is None else Decimal(open_interest),
            source=source,
            assumptions={
                "research_only": True,
                "run_label": source,
            },
        )

    def test_funding_statistics(self):
        rows = [
            {
                "funding_rate": Decimal("0.0002"),
                "annualized_rate_pct": Decimal("21.90"),
            },
            {
                "funding_rate": Decimal("0.0001"),
                "annualized_rate_pct": Decimal("10.95"),
            },
        ]

        stats = funding_statistics(rows)

        self.assertEqual(stats["funding_observations"], 2)
        self.assertEqual(stats["positive_funding_ratio_pct"], Decimal("100"))
        self.assertEqual(stats["avg_annualized_rate_pct"], Decimal("16.425"))

    def test_basis_penalty_and_edges(self):
        penalty = calculate_basis_penalty_pct(
            basis_value_pct=Decimal("0.20"),
            basis_penalty_factor=Decimal("0.25"),
        )

        edges = calculate_edges(
            avg_annualized_rate_pct=Decimal("21.90"),
            min_annualized_rate_pct=Decimal("10.00"),
            basis_penalty_pct=penalty,
            execution_cost_pct=Decimal("0.20"),
        )

        self.assertEqual(penalty, Decimal("0.0500"))
        self.assertEqual(edges["expected_edge_pct"], Decimal("21.6500"))
        self.assertEqual(edges["stress_edge_pct"], Decimal("9.7500"))

    def test_build_lab_result_go(self):
        funding_rows = [
            {
                "funding_rate": Decimal("0.0002"),
                "annualized_rate_pct": Decimal("21.90"),
            }
            for _ in range(12)
        ]

        basis_snapshot = {
            "basis_pct": Decimal("0.20"),
            "open_interest": Decimal("1000000"),
        }

        result = build_lab_result(
            funding_rows=funding_rows,
            basis_snapshot=basis_snapshot,
            execution_cost_bps=Decimal("20"),
            basis_penalty_factor=Decimal("0.25"),
            min_observations=10,
            min_avg_annualized_pct=Decimal("10"),
            min_latest_annualized_pct=Decimal("8"),
            min_positive_ratio_pct=Decimal("80"),
            min_basis_pct=Decimal("-0.30"),
            max_basis_pct=Decimal("2.00"),
            min_expected_edge_pct=Decimal("7"),
            min_stress_edge_pct=Decimal("0"),
        )

        self.assertEqual(result["final_verdict"], "GO_FOR_RESEARCH")

    def test_build_lab_result_rejects_low_funding(self):
        funding_rows = [
            {
                "funding_rate": Decimal("0.00002"),
                "annualized_rate_pct": Decimal("2.19"),
            }
            for _ in range(12)
        ]

        basis_snapshot = {
            "basis_pct": Decimal("0.10"),
            "open_interest": Decimal("1000000"),
        }

        result = build_lab_result(
            funding_rows=funding_rows,
            basis_snapshot=basis_snapshot,
            execution_cost_bps=Decimal("20"),
            basis_penalty_factor=Decimal("0.25"),
            min_observations=10,
            min_avg_annualized_pct=Decimal("10"),
            min_latest_annualized_pct=Decimal("8"),
            min_positive_ratio_pct=Decimal("80"),
            min_basis_pct=Decimal("-0.30"),
            max_basis_pct=Decimal("2.00"),
            min_expected_edge_pct=Decimal("7"),
            min_stress_edge_pct=Decimal("0"),
        )

        self.assertEqual(result["final_verdict"], "NO_GO_LOW_AVG_FUNDING")

    def test_load_funding_rows(self):
        self.seed_funding_rows("test_source", "0.0002", count=3)

        rows = load_funding_rows(
            db_path=self.db_path,
            symbol="ETHUSDT",
            source_run_label="test_source",
        )

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["funding_rate"], Decimal("0.0002"))

    def test_run_delta_neutral_funding_lab_inserts_results(self):
        self.seed_funding_rows("test_source", "0.0002", count=12)
        self.seed_basis_snapshot("test_source")

        result = run_delta_neutral_funding_lab(
            db_path=self.db_path,
            symbol="ETHUSDT",
            source_run_label="test_source",
            run_label="test_lab",
            execution_cost_bps=Decimal("20"),
            basis_penalty_factor=Decimal("0.25"),
            min_observations=10,
            min_avg_annualized_pct=Decimal("10"),
            min_latest_annualized_pct=Decimal("8"),
            min_positive_ratio_pct=Decimal("80"),
            min_basis_pct=Decimal("-0.30"),
            max_basis_pct=Decimal("2.00"),
            min_expected_edge_pct=Decimal("7"),
            min_stress_edge_pct=Decimal("0"),
        )

        self.assertEqual(result["global_verdict"], "DELTA_NEUTRAL_FUNDING_CANDIDATE_FOUND_NO_LIVE_TRADING")
        self.assertEqual(result["results_created"], 1)
        self.assertEqual(result["summary_results_created"], 1)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        result_count = cur.execute("""
        SELECT COUNT(*)
        FROM delta_neutral_funding_lab_results
        WHERE run_label = 'test_lab'
        """).fetchone()[0]

        summary_count = cur.execute("""
        SELECT COUNT(*)
        FROM delta_neutral_funding_lab_summary
        WHERE run_label = 'test_lab'
        """).fetchone()[0]

        conn.close()

        self.assertEqual(result_count, 1)
        self.assertEqual(summary_count, 1)


if __name__ == "__main__":
    unittest.main()
