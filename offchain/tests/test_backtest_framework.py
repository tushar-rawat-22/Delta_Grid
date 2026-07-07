import sqlite3
import tempfile
import unittest
from pathlib import Path

from backtest.backtest_engine import run_ma_crossover_backtest
from backtest.historical_data import seed_synthetic_history


class BacktestFrameworkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "backtest_test.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_seed_synthetic_history_and_run_backtest(self):
        candles = seed_synthetic_history(
            db_path=self.db_path,
            chain_id=84532,
            symbol="WETH_USDC_DEMO",
            timeframe="1d",
            days=240,
        )

        self.assertEqual(candles, 240)

        result = run_ma_crossover_backtest(
            db_path=self.db_path,
            chain_id=84532,
            symbol="WETH_USDC_DEMO",
            timeframe="1d",
            initial_capital="10000",
            fast_window=5,
            slow_window=15,
            fee_bps=10,
            slippage_bps=10,
        )

        self.assertGreater(result["run_id"], 0)
        self.assertEqual(result["strategy_name"], "ma_crossover_baseline")
        self.assertEqual(result["status"], "research_only")
        self.assertGreaterEqual(result["trades_count"], 1)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        candle_count = cur.execute("""
        SELECT COUNT(*)
        FROM historical_candles
        """).fetchone()[0]

        run_count = cur.execute("""
        SELECT COUNT(*)
        FROM backtest_runs
        """).fetchone()[0]

        trade_count = cur.execute("""
        SELECT COUNT(*)
        FROM backtest_trades
        """).fetchone()[0]

        conn.close()

        self.assertEqual(candle_count, 240)
        self.assertEqual(run_count, 1)
        self.assertEqual(trade_count, result["trades_count"])

    def test_backtest_rejects_insufficient_data(self):
        seed_synthetic_history(
            db_path=self.db_path,
            chain_id=84532,
            symbol="WETH_USDC_DEMO",
            timeframe="1d",
            days=10,
        )

        with self.assertRaises(ValueError):
            run_ma_crossover_backtest(
                db_path=self.db_path,
                chain_id=84532,
                symbol="WETH_USDC_DEMO",
                timeframe="1d",
                fast_window=5,
                slow_window=30,
            )


if __name__ == "__main__":
    unittest.main()
