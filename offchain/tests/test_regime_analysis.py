import sqlite3
import tempfile
import unittest
from pathlib import Path

from backtest.historical_data import seed_synthetic_history
from backtest.regime_analysis import (
    classify_trend,
    classify_volatility,
    run_strategy_regime_analysis,
)


class RegimeAnalysisTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "regime_test.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_regime_classifiers(self):
        self.assertEqual(classify_trend(6.0), "bull")
        self.assertEqual(classify_trend(-6.0), "bear")
        self.assertEqual(classify_trend(1.0), "sideways")

        self.assertEqual(classify_volatility(2.5), "high_volatility")
        self.assertEqual(classify_volatility(1.0), "low_volatility")

    def test_run_strategy_regime_analysis(self):
        seed_synthetic_history(
            db_path=self.db_path,
            chain_id=84532,
            symbol="WETH_USDC_DEMO",
            timeframe="1d",
            days=240,
        )

        result = run_strategy_regime_analysis(
            db_path=self.db_path,
            chain_id=84532,
            symbol="WETH_USDC_DEMO",
            timeframe="1d",
            regime_window=30,
            initial_capital="10000",
            fast_window=5,
            slow_window=15,
            fee_bps=10,
            slippage_bps=10,
        )

        self.assertGreater(result["run_id"], 0)
        self.assertEqual(result["labels_stored"], 240)
        self.assertGreater(result["metrics_stored"], 0)
        self.assertGreaterEqual(result["trades_count"], 1)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        label_count = cur.execute("""
        SELECT COUNT(*)
        FROM market_regime_labels
        """).fetchone()[0]

        metric_count = cur.execute("""
        SELECT COUNT(*)
        FROM strategy_regime_metrics
        """).fetchone()[0]

        verdicts = {
            row[0]
            for row in cur.execute("""
            SELECT verdict
            FROM strategy_regime_metrics
            """).fetchall()
        }

        conn.close()

        self.assertEqual(label_count, 240)
        self.assertEqual(metric_count, result["metrics_stored"])
        self.assertTrue(verdicts)


if __name__ == "__main__":
    unittest.main()
