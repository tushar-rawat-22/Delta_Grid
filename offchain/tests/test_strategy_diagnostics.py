import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from db.schema import init_market_database, upsert_chain
from backtest.walk_forward_candidate_lab import ensure_schema as ensure_walk_forward_schema

from backtest.strategy_diagnostics import (
    diagnose_candidate,
    ensure_schema,
    run_strategy_diagnostics,
)


class StrategyDiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "strategy_diagnostics_test.db")

        init_market_database(self.db_path)
        ensure_walk_forward_schema(self.db_path)
        ensure_schema(self.db_path)

        upsert_chain(
            db_path=self.db_path,
            chain_id=0,
            name="Binance Spot",
            rpc_url="https://api.binance.com",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def insert_summary(
        self,
        candidate_name,
        candidate_version,
        go_splits,
        splits_tested,
        rejected_splits,
        avg_excess,
        worst_drawdown,
        avg_sharpe,
        avg_profit_factor,
        total_trades,
        final_verdict,
        stability_score,
    ):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO walk_forward_candidate_summary (
            chain_id,
            symbol,
            timeframe,
            source,
            run_label,
            candidate_name,
            candidate_version,
            splits_tested,
            go_splits,
            rejected_or_insufficient_splits,
            avg_net_return_pct,
            avg_excess_return_pct,
            worst_drawdown_pct,
            avg_sharpe_ratio,
            avg_profit_factor,
            total_trades,
            stability_score,
            final_verdict,
            assumptions_json,
            created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            0,
            "ETHUSDT",
            "1d",
            "binance_spot",
            "test_walk_forward",
            candidate_name,
            candidate_version,
            splits_tested,
            go_splits,
            rejected_splits,
            "1.0",
            str(avg_excess),
            str(worst_drawdown),
            str(avg_sharpe),
            str(avg_profit_factor),
            total_trades,
            str(stability_score),
            final_verdict,
            "{}",
            "2026-07-08T00:00:00Z",
        ))

        conn.commit()
        conn.close()

    def test_diagnose_candidate_finds_multiple_failures(self):
        row = {
            "splits_tested": 5,
            "go_splits": 0,
            "rejected_or_insufficient_splits": 5,
            "worst_drawdown_pct": "35",
            "avg_sharpe_ratio": "0.2",
            "avg_excess_return_pct": "-1",
            "avg_profit_factor": "1.1",
            "total_trades": 7,
            "final_verdict": "NO_GO_WALK_FORWARD_FAILURE",
        }

        diagnostic = diagnose_candidate(row, Decimal("0.60"))

        codes = [item["code"] for item in diagnostic["failure_reasons"]]

        self.assertIn("WEAK_WALK_FORWARD_STABILITY", codes)
        self.assertIn("DRAWDOWN_TOO_HIGH", codes)
        self.assertIn("UNDERPERFORMS_BENCHMARK", codes)
        self.assertIn("INSUFFICIENT_TRADE_SAMPLE", codes)

    def test_run_strategy_diagnostics_inserts_rows(self):
        self.insert_summary(
            candidate_name="ma_crossover",
            candidate_version="fast_20_slow_60",
            go_splits=0,
            splits_tested=5,
            rejected_splits=5,
            avg_excess="3",
            worst_drawdown="33",
            avg_sharpe="0.21",
            avg_profit_factor="599",
            total_trades=7,
            final_verdict="NO_GO_WALK_FORWARD_FAILURE",
            stability_score="100",
        )

        self.insert_summary(
            candidate_name="controlled_ma",
            candidate_version="risk_guard",
            go_splits=1,
            splits_tested=5,
            rejected_splits=4,
            avg_excess="2",
            worst_drawdown="26",
            avg_sharpe="0.4",
            avg_profit_factor="1.5",
            total_trades=12,
            final_verdict="NO_GO_WALK_FORWARD_FAILURE",
            stability_score="50",
        )

        result = run_strategy_diagnostics(
            db_path=self.db_path,
            symbol="ETHUSDT",
            timeframe="1d",
            source="binance_spot",
            source_run_label="test_walk_forward",
            diagnostic_run_label="test_diagnostics",
            min_pass_ratio=Decimal("0.60"),
        )

        self.assertEqual(result["candidates_diagnosed"], 2)
        self.assertEqual(result["global_verdict"], "DIAGNOSE_ONLY_NO_LIVE_TRADING")

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        count = cur.execute("""
        SELECT COUNT(*)
        FROM strategy_failure_diagnostics
        WHERE diagnostic_run_label = 'test_diagnostics'
        """).fetchone()[0]

        conn.close()

        self.assertEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
