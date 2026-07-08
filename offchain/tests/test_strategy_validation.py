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

from backtest.strategy_validation import (
    buy_and_hold_return,
    run_ma_strategy,
    run_strategy_validation,
)


class StrategyValidationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "strategy_validation_test.db")

        init_market_database(self.db_path)

        upsert_chain(
            db_path=self.db_path,
            chain_id=0,
            name="Binance Spot",
            rpc_url="https://api.binance.com",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def make_candles(self, count=140):
        candles = []
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        price = Decimal("100")

        for index in range(count):
            if index < 50:
                price += Decimal("1")
            elif index < 90:
                price -= Decimal("0.30")
            else:
                price += Decimal("0.75")

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

    def test_buy_and_hold_return_is_calculated(self):
        candles = self.make_candles(40)

        result = buy_and_hold_return(
            candles=candles,
            initial_capital=Decimal("10000"),
            fee_bps=10,
            slippage_bps=10,
        )

        self.assertIsInstance(result, Decimal)

    def test_ma_strategy_returns_metrics(self):
        candles = self.make_candles(120)

        benchmark = buy_and_hold_return(
            candles=candles,
            initial_capital=Decimal("10000"),
            fee_bps=10,
            slippage_bps=10,
        )

        result = run_ma_strategy(
            candles=candles,
            initial_capital=Decimal("10000"),
            fast_window=5,
            slow_window=15,
            fee_bps=10,
            slippage_bps=10,
            benchmark_return=benchmark,
        )

        self.assertEqual(result["strategy_name"], "ma_crossover_baseline")
        self.assertIn("net_return_pct", result)
        self.assertIn("benchmark_return_pct", result)
        self.assertIn("verdict", result)

    def test_strategy_validation_inserts_results(self):
        candles = self.make_candles(140)
        self.seed_candles(candles)

        result = run_strategy_validation(
            db_path=self.db_path,
            chain_id=0,
            symbol="ETHUSDT",
            timeframe="1d",
            source="binance_spot",
            initial_capital=Decimal("10000"),
            fast_window=5,
            slow_window=15,
            fee_bps=10,
            slippage_bps=10,
            train_size=40,
            test_size=40,
            step_size=30,
        )

        self.assertEqual(result["symbol"], "ETHUSDT")
        self.assertEqual(result["candles_seen"], 140)
        self.assertGreaterEqual(result["walk_forward"]["splits"], 2)
        self.assertEqual(result["global_verdict"], "RESEARCH_ONLY_NO_LIVE_TRADING")

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        count = cur.execute("""
        SELECT COUNT(*)
        FROM strategy_validation_results
        """).fetchone()[0]

        conn.close()

        self.assertGreaterEqual(count, 3)


if __name__ == "__main__":
    unittest.main()
