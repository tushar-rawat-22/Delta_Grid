import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from db.schema import (
    init_market_database,
    insert_historical_candle,
    upsert_chain,
)

from backtest.stability_rework_lab import (
    final_verdict,
    run_stability_rework_lab,
    variant_specs,
)


class StabilityReworkLabTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "stability_rework_test.db")

        init_market_database(self.db_path)

        upsert_chain(
            db_path=self.db_path,
            chain_id=0,
            name="Binance Spot",
            rpc_url="https://api.binance.com",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def make_candles(self, count=620):
        candles = []
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        price = Decimal("100")

        for index in range(count):
            if index < 160:
                price += Decimal("0.35")
            elif index < 300:
                price -= Decimal("0.20")
            elif index < 460:
                price += Decimal("0.25")
            else:
                price -= Decimal("0.08")

            timestamp = start + timedelta(days=index)

            candles.append({
                "timestamp_utc": timestamp.isoformat(),
                "open": price - Decimal("0.5"),
                "high": price + Decimal("1"),
                "low": price - Decimal("1"),
                "close": price,
                "volume": Decimal("1000"),
            })

        return candles

    def seed_candles(self, candles):
        for candle in candles:
            insert_historical_candle(
                db_path=self.db_path,
                chain_id=0,
                symbol="ETHUSDT",
                timeframe="1d",
                timestamp_utc=candle["timestamp_utc"],
                open_price=str(candle["open"]),
                high_price=str(candle["high"]),
                low_price=str(candle["low"]),
                close_price=str(candle["close"]),
                volume=str(candle["volume"]),
                source="binance_spot",
            )

    def test_variant_specs_exist(self):
        specs = variant_specs()

        self.assertEqual(len(specs), 5)

    def test_final_verdict_requires_stability(self):
        verdict = final_verdict(
            splits_tested=5,
            go_splits=1,
            avg_excess=Decimal("10"),
            worst_drawdown=Decimal("20"),
            avg_sharpe=Decimal("1"),
            avg_profit_factor=Decimal("2"),
            total_trades=30,
            min_pass_ratio=Decimal("0.60"),
        )

        self.assertEqual(verdict, "NO_GO_STABILITY_FAILURE")

    def test_stability_rework_lab_inserts_results(self):
        candles = self.make_candles()
        self.seed_candles(candles)

        result = run_stability_rework_lab(
            db_path=self.db_path,
            chain_id=0,
            symbol="ETHUSDT",
            timeframe="1d",
            source="binance_spot",
            initial_capital=Decimal("10000"),
            fee_bps=10,
            slippage_bps=10,
            train_size=120,
            test_size=180,
            step_size=150,
            min_pass_ratio=Decimal("0.60"),
            run_label="test_stability_rework_lab",
        )

        self.assertEqual(result["symbol"], "ETHUSDT")
        self.assertEqual(result["variant_count"], len(variant_specs()))
        self.assertEqual(result["summary_results_created"], len(variant_specs()))
        self.assertEqual(
            result["split_results_created"],
            result["variant_count"] * result["splits_tested"],
        )
        self.assertIn("best_variant", result)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        split_count = cur.execute("""
        SELECT COUNT(*)
        FROM stability_rework_split_results
        WHERE run_label = 'test_stability_rework_lab'
        """).fetchone()[0]

        summary_count = cur.execute("""
        SELECT COUNT(*)
        FROM stability_rework_summary
        WHERE run_label = 'test_stability_rework_lab'
        """).fetchone()[0]

        conn.close()

        self.assertEqual(split_count, result["split_results_created"])
        self.assertEqual(summary_count, result["summary_results_created"])


if __name__ == "__main__":
    unittest.main()
