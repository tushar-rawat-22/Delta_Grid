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

from backtest.strategy_candidate_lab import benchmark_return

from backtest.compression_breakout_lab import (
    result_verdict,
    run_compression_breakout_lab,
    run_compression_breakout_strategy,
    variant_specs,
)


class CompressionBreakoutLabTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "compression_breakout_test.db")

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
                price += Decimal("0.06")
            elif index < 220:
                price += Decimal("0.02")
            elif index < 300:
                price += Decimal("0.40")
            elif index < 420:
                price -= Decimal("0.10")
            elif index < 500:
                price += Decimal("0.04")
            else:
                price += Decimal("0.30")

            timestamp = start + timedelta(days=index)

            volume = Decimal("1000")
            if index % 90 == 0:
                volume = Decimal("1600")

            candles.append({
                "timestamp_utc": timestamp.isoformat(),
                "open": price - Decimal("0.25"),
                "high": price + Decimal("0.75"),
                "low": price - Decimal("0.75"),
                "close": price,
                "volume": volume,
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

        self.assertEqual(len(specs), 3)
        self.assertEqual(specs[0]["name"], "compression_breakout")

    def test_result_verdict_rejects_insufficient_trades(self):
        verdict = result_verdict(
            net_return_pct=Decimal("10"),
            excess_return_pct=Decimal("5"),
            max_drawdown=Decimal("10"),
            sharpe=Decimal("1"),
            pf=Decimal("2"),
            trades_count=1,
        )

        self.assertEqual(verdict, "INSUFFICIENT_TRADES")

    def test_strategy_runner_returns_required_metrics(self):
        candles = self.make_candles(260)

        result = run_compression_breakout_strategy(
            candles=candles,
            initial_capital=Decimal("10000"),
            entry_window=40,
            exit_window=15,
            bb_period=20,
            bb_std=Decimal("2"),
            bb_percentile_window=120,
            bb_max_percentile=Decimal("0.30"),
            atr_period=14,
            atr_percentile_window=120,
            atr_max_percentile=Decimal("0.65"),
            volume_sma=20,
            volume_mult=Decimal("1.05"),
            ema_filter=50,
            stop_atr_mult=Decimal("2.5"),
            trail_atr_mult=Decimal("3.0"),
            false_break_bars=5,
            max_hold=50,
            fee_bps=10,
            slippage_bps=10,
            benchmark=benchmark_return(candles, Decimal("10000"), 10, 10),
        )

        self.assertIn("net_return_pct", result)
        self.assertIn("benchmark_return_pct", result)
        self.assertIn("excess_return_pct", result)
        self.assertIn("max_drawdown_pct", result)
        self.assertIn("sharpe_ratio", result)
        self.assertIn("profit_factor", result)
        self.assertIn("win_rate_pct", result)
        self.assertIn("trades_count", result)
        self.assertIn("compression_signals", result)
        self.assertIn("verdict", result)

    def test_compression_breakout_lab_inserts_results(self):
        candles = self.make_candles()
        self.seed_candles(candles)

        result = run_compression_breakout_lab(
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
            run_label="test_compression_breakout_lab",
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
        FROM compression_breakout_split_results
        WHERE run_label = 'test_compression_breakout_lab'
        """).fetchone()[0]

        summary_count = cur.execute("""
        SELECT COUNT(*)
        FROM compression_breakout_summary
        WHERE run_label = 'test_compression_breakout_lab'
        """).fetchone()[0]

        conn.close()

        self.assertEqual(split_count, result["split_results_created"])
        self.assertEqual(summary_count, result["summary_results_created"])


if __name__ == "__main__":
    unittest.main()
