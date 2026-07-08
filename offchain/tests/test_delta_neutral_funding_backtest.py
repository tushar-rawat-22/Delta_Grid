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

from backtest.delta_neutral_funding_backtest import (
    basis_for_time,
    ensure_schema,
    funding_path_statistics,
    run_delta_neutral_funding_backtest,
    simulate_delta_neutral_backtest,
    summarize_backtest,
)


class DeltaNeutralFundingBacktestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "delta_neutral_funding_backtest_test.db")

        init_market_database(self.db_path)
        ensure_funding_basis_schema(self.db_path)
        ensure_schema(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def seed_funding_rows(self, source, rate="0.0002", count=12):
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

    def seed_basis_snapshot(self, source, timestamp="2026-07-01T00:00:00Z", basis="0.20"):
        spot_price = Decimal("3100")
        perp_mark_price = spot_price * (Decimal("1") + Decimal(basis) / Decimal("100"))

        insert_basis_snapshot(
            db_path=self.db_path,
            spot_exchange="Binance Spot",
            perp_exchange="Binance Futures",
            symbol="ETHUSDT",
            timestamp_utc=timestamp,
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

    def test_basis_for_time_uses_latest_available_snapshot(self):
        basis_rows = [
            {
                "timestamp_utc": "2026-07-01T00:00:00Z",
                "basis_pct": Decimal("0.10"),
            },
            {
                "timestamp_utc": "2026-07-03T00:00:00Z",
                "basis_pct": Decimal("0.20"),
            },
        ]

        selected = basis_for_time(
            basis_rows,
            "2026-07-04T00:00:00Z",
        )

        self.assertEqual(selected["basis_pct"], Decimal("0.20"))

    def test_funding_path_statistics(self):
        rows = [
            {
                "funding_rate": Decimal("0.0002"),
                "annualized_rate_pct": Decimal("21.90"),
            },
            {
                "funding_rate": Decimal("-0.0001"),
                "annualized_rate_pct": Decimal("-10.95"),
            },
        ]

        stats = funding_path_statistics(rows)

        self.assertEqual(stats["funding_observations"], 2)
        self.assertEqual(stats["positive_funding_ratio_pct"], Decimal("50"))
        self.assertEqual(stats["avg_annualized_funding_pct"], Decimal("5.475"))

    def test_simulate_delta_neutral_backtest_creates_trade(self):
        funding_rows = [
            {
                "funding_time_utc": f"2026-07-{index + 1:02d}T00:00:00Z",
                "funding_rate": Decimal("0.0002"),
                "annualized_rate_pct": Decimal("21.90"),
            }
            for index in range(5)
        ]

        basis_rows = [
            {
                "timestamp_utc": "2026-07-01T00:00:00Z",
                "basis_pct": Decimal("0.20"),
                "open_interest": Decimal("1000000"),
            }
        ]

        trades = simulate_delta_neutral_backtest(
            funding_rows=funding_rows,
            basis_rows=basis_rows,
            entry_annualized_pct=Decimal("8"),
            exit_annualized_pct=Decimal("4"),
            min_basis_pct=Decimal("-0.30"),
            max_basis_pct=Decimal("2.00"),
            max_holding_windows=3,
            execution_cost_bps=Decimal("20"),
        )

        self.assertEqual(len(trades), 2)
        self.assertEqual(trades[0]["funding_windows"], 3)
        self.assertEqual(trades[0]["exit_reason"], "MAX_HOLDING_WINDOWS_EXIT")
        self.assertEqual(trades[1]["funding_windows"], 2)
        self.assertEqual(trades[1]["exit_reason"], "END_OF_SAMPLE_EXIT")

    def test_summarize_backtest_go(self):
        funding_rows = [
            {
                "funding_rate": Decimal("0.0002"),
                "annualized_rate_pct": Decimal("21.90"),
            }
            for _ in range(12)
        ]

        trades = [
            {
                "gross_funding_return_pct": Decimal("0.50"),
                "basis_pnl_pct": Decimal("0.10"),
                "execution_cost_pct": Decimal("0.20"),
                "net_return_pct": Decimal("0.40"),
            }
        ]

        result = summarize_backtest(
            funding_rows=funding_rows,
            trades=trades,
            min_observations=10,
            min_trades=1,
            min_avg_annualized_pct=Decimal("8"),
            min_net_return_pct=Decimal("0.10"),
            max_drawdown_limit_pct=Decimal("5"),
            min_profit_factor=Decimal("1.10"),
        )

        self.assertEqual(result["final_verdict"], "GO_FOR_RESEARCH")

    def test_summarize_backtest_rejects_low_average_funding(self):
        funding_rows = [
            {
                "funding_rate": Decimal("0.00002"),
                "annualized_rate_pct": Decimal("2.19"),
            }
            for _ in range(12)
        ]

        result = summarize_backtest(
            funding_rows=funding_rows,
            trades=[],
            min_observations=10,
            min_trades=1,
            min_avg_annualized_pct=Decimal("8"),
            min_net_return_pct=Decimal("0.10"),
            max_drawdown_limit_pct=Decimal("5"),
            min_profit_factor=Decimal("1.10"),
        )

        self.assertEqual(result["final_verdict"], "NO_GO_LOW_AVG_FUNDING")

    def test_run_delta_neutral_funding_backtest_inserts_results(self):
        self.seed_funding_rows("test_source", rate="0.0002", count=12)
        self.seed_basis_snapshot("test_source")

        result = run_delta_neutral_funding_backtest(
            db_path=self.db_path,
            symbol="ETHUSDT",
            source_run_label="test_source",
            run_label="test_backtest",
            entry_annualized_pct=Decimal("8"),
            exit_annualized_pct=Decimal("4"),
            min_basis_pct=Decimal("-0.30"),
            max_basis_pct=Decimal("2.00"),
            max_holding_windows=6,
            execution_cost_bps=Decimal("20"),
            min_observations=10,
            min_trades=1,
            min_avg_annualized_pct=Decimal("8"),
            min_net_return_pct=Decimal("0.10"),
            max_drawdown_limit_pct=Decimal("5"),
            min_profit_factor=Decimal("1.10"),
        )

        self.assertEqual(result["results_created"], 1)
        self.assertEqual(result["summary_results_created"], 1)
        self.assertGreaterEqual(result["trades_created"], 1)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        trade_count = cur.execute("""
        SELECT COUNT(*)
        FROM delta_neutral_funding_backtest_trades
        WHERE run_label = 'test_backtest'
        """).fetchone()[0]

        result_count = cur.execute("""
        SELECT COUNT(*)
        FROM delta_neutral_funding_backtest_results
        WHERE run_label = 'test_backtest'
        """).fetchone()[0]

        summary_count = cur.execute("""
        SELECT COUNT(*)
        FROM delta_neutral_funding_backtest_summary
        WHERE run_label = 'test_backtest'
        """).fetchone()[0]

        conn.close()

        self.assertEqual(trade_count, result["trades_created"])
        self.assertEqual(result_count, 1)
        self.assertEqual(summary_count, 1)


if __name__ == "__main__":
    unittest.main()
