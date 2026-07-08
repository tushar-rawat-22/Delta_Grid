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

from backtest.strategy_candidate_lab import (
    benchmark_return,
    run_candidate_lab,
    run_ma_crossover,
)


class StrategyCandidateLabTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "candidate_lab_test.db")

        init_market_database(self.db_path)

        upsert_chain(
            db_path=self.db_path,
            chain_id=0,
            name="Binance Spot",
            rpc_url="https://api.binance.com",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def make_candles(self, count=180):
        candles = []
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        price = Decimal("100")

        for index in range(count):
            if index < 60:
                price += Decimal("0.8")
            elif index < 110:
                price -= Decimal("0.35")
            else:
                price += Decimal("0.6")

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

    def test_benchmark_return_calculates(self):
        candles = self.make_candles(120)

        result = benchmark_return(
            candles=candles,
            initial_capital=Decimal("10000"),
            fee_bps=10,
            slippage_bps=10,
        )

        self.assertIsInstance(result, Decimal)

    def test_candidate_strategy_returns_result(self):
        candles = self.make_candles(180)

        bench = benchmark_return(
            candles=candles,
            initial_capital=Decimal("10000"),
            fee_bps=10,
            slippage_bps=10,
        )

        result = run_ma_crossover(
            candles=candles,
            initial_capital=Decimal("10000"),
            fast_window=10,
            slow_window=30,
            fee_bps=10,
            slippage_bps=10,
            benchmark=bench,
        )

        self.assertEqual(result["strategy_name"], "ma_crossover")
        self.assertIn("rank_score", result)
        self.assertIn("verdict", result)

    def test_candidate_lab_inserts_results(self):
        candles = self.make_candles(180)
        self.seed_candles(candles)

        result = run_candidate_lab(
            db_path=self.db_path,
            chain_id=0,
            symbol="ETHUSDT",
            timeframe="1d",
            source="binance_spot",
            initial_capital=Decimal("10000"),
            fee_bps=10,
            slippage_bps=10,
            run_label="test_candidate_lab",
        )

        self.assertEqual(result["symbol"], "ETHUSDT")
        self.assertEqual(result["candidate_count"], 5)
        self.assertEqual(len(result["ranked_candidates"]), 5)
        self.assertIn("best_candidate", result)
        self.assertIn(
            result["global_verdict"],
            [
                "RESEARCH_CANDIDATE_FOUND_NO_LIVE_TRADING",
                "REJECT_ALL_NO_LIVE_TRADING",
            ],
        )

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        count = cur.execute("""
        SELECT COUNT(*)
        FROM strategy_candidate_results
        """).fetchone()[0]

        conn.close()

        self.assertEqual(count, 5)


if __name__ == "__main__":
    unittest.main()
