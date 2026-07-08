import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from db.schema import init_market_database

from backtest.funding_basis_model import (
    annualize_funding_rate_pct,
    basis_pct,
    ensure_schema,
    evaluate_delta_neutral_candidate,
    insert_basis_snapshot,
    run_demo_seed,
    upsert_funding_rate,
    upsert_perp_mark_price,
)


class FundingBasisModelTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "funding_basis_test.db")

        init_market_database(self.db_path)
        ensure_schema(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_annualize_funding_and_basis(self):
        annualized = annualize_funding_rate_pct(
            funding_rate=Decimal("0.0002"),
            interval_hours=Decimal("8"),
        )

        basis = basis_pct(
            spot_price=Decimal("100"),
            perp_mark_price=Decimal("101"),
        )

        self.assertEqual(annualized, Decimal("21.9000"))
        self.assertEqual(basis, Decimal("1.00"))

    def test_upsert_funding_rate_is_idempotent(self):
        first_id = upsert_funding_rate(
            db_path=self.db_path,
            exchange="Binance Futures",
            symbol="ETHUSDT",
            funding_time_utc="2026-07-08T00:00:00Z",
            funding_rate=Decimal("0.0002"),
            interval_hours=Decimal("8"),
            source="test",
        )

        second_id = upsert_funding_rate(
            db_path=self.db_path,
            exchange="Binance Futures",
            symbol="ETHUSDT",
            funding_time_utc="2026-07-08T00:00:00Z",
            funding_rate=Decimal("0.0003"),
            interval_hours=Decimal("8"),
            source="test",
        )

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        count = cur.execute("""
        SELECT COUNT(*)
        FROM funding_rates
        WHERE source = 'test'
        """).fetchone()[0]

        latest_rate = cur.execute("""
        SELECT funding_rate
        FROM funding_rates
        WHERE source = 'test'
        """).fetchone()[0]

        conn.close()

        self.assertEqual(first_id, second_id)
        self.assertEqual(count, 1)
        self.assertEqual(latest_rate, "0.0003")

    def test_upsert_perp_mark_price_is_idempotent(self):
        first_id = upsert_perp_mark_price(
            db_path=self.db_path,
            exchange="Binance Futures",
            symbol="ETHUSDT",
            timestamp_utc="2026-07-08T00:00:00Z",
            mark_price=Decimal("3106.20"),
            index_price=Decimal("3100"),
            open_interest=Decimal("100000"),
            source="test",
        )

        second_id = upsert_perp_mark_price(
            db_path=self.db_path,
            exchange="Binance Futures",
            symbol="ETHUSDT",
            timestamp_utc="2026-07-08T00:00:00Z",
            mark_price=Decimal("3110.00"),
            index_price=Decimal("3100"),
            open_interest=Decimal("100000"),
            source="test",
        )

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        count = cur.execute("""
        SELECT COUNT(*)
        FROM perp_mark_prices
        WHERE source = 'test'
        """).fetchone()[0]

        latest_mark = cur.execute("""
        SELECT mark_price
        FROM perp_mark_prices
        WHERE source = 'test'
        """).fetchone()[0]

        conn.close()

        self.assertEqual(first_id, second_id)
        self.assertEqual(count, 1)
        self.assertEqual(latest_mark, "3110.00")

    def test_insert_basis_snapshot(self):
        row_id = insert_basis_snapshot(
            db_path=self.db_path,
            spot_exchange="Binance Spot",
            perp_exchange="Binance Futures",
            symbol="ETHUSDT",
            timestamp_utc="2026-07-08T00:00:00Z",
            spot_price=Decimal("3100"),
            perp_mark_price=Decimal("3106.20"),
            annualized_funding_rate_pct=Decimal("21.90"),
            open_interest=Decimal("100000"),
            source="test",
            assumptions={"research_only": True},
        )

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        verdict = cur.execute("""
        SELECT verdict
        FROM spot_perp_basis_snapshots
        WHERE id = ?
        """, (row_id,)).fetchone()[0]

        conn.close()

        self.assertEqual(verdict, "DELTA_NEUTRAL_CANDIDATE")

    def test_candidate_evaluation(self):
        go = evaluate_delta_neutral_candidate(
            funding_rate=Decimal("0.0002"),
            annualized_funding_rate_pct=Decimal("21.90"),
            basis_value_pct=Decimal("0.20"),
            open_interest=Decimal("100000"),
        )

        no_go = evaluate_delta_neutral_candidate(
            funding_rate=Decimal("0.00001"),
            annualized_funding_rate_pct=Decimal("1.095"),
            basis_value_pct=Decimal("0.10"),
            open_interest=Decimal("100000"),
        )

        self.assertEqual(go["verdict"], "GO_FOR_RESEARCH")
        self.assertEqual(no_go["verdict"], "NO_GO_LOW_FUNDING")

    def test_run_demo_seed_creates_rows(self):
        result = run_demo_seed(
            db_path=self.db_path,
            run_label="test_demo_seed",
        )

        self.assertEqual(result["global_verdict"], "DATA_MODEL_READY_NO_LIVE_TRADING")
        self.assertEqual(result["funding_rates"], 1)
        self.assertEqual(result["perp_mark_prices"], 1)
        self.assertEqual(result["spot_perp_basis_snapshots"], 1)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        candidate_count = cur.execute("""
        SELECT COUNT(*)
        FROM delta_neutral_research_candidates
        """).fetchone()[0]

        conn.close()

        self.assertEqual(candidate_count, 1)


if __name__ == "__main__":
    unittest.main()
