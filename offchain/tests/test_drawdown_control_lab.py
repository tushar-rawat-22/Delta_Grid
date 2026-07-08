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

from backtest.drawdown_control_lab import (
    rolling_volatility_pct,
    run_controlled_ma_strategy,
    run_drawdown_control_lab,
)

from backtest.strategy_candidate_lab import benchmark_return


class DrawdownControlLabTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "drawdown_control_test.db")

        init_market_database(self.db_path)

        upsert_chain(
            db_path=self.db_path,
            chain_id=0,
            name="Binance Spot",
            rpc_url="https://api.binance.com",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def make_candles(self, count=220):
        candles = []
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        price = Decimal("100")

        for index in range(count):
            if index < 70:
                price += Decimal("0.75")
            elif index < 120:
                price -= Decimal("0.65")
            elif index < 170:
                price += Decimal("0.55")
            else:
                price += Decimal("0.20")

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

    def test_rolling_volatility_calculates(self):
        candles = self.make_candles(80)

        result = rolling_volatility_pct(
            candles=candles,
            index=40,
            window=20,
        )

        self.assertIsNotNone(result)
        self.assertIsInstance(result, Decimal)

    def test_controlled_ma_strategy_returns_metrics(self):
        candles = self.make_candles(220)

        bench = benchmark_return(
            candles=candles,
            initial_capital=Decimal("10000"),
            fee_bps=10,
            slippage_bps=10,
        )

        result = run_controlled_ma_strategy(
            candles=candles,
            initial_capital=Decimal("10000"),
            fast_window=20,
            slow_window=60,
            fee_bps=10,
            slippage_bps=10,
            benchmark=bench,
            stop_loss_pct=Decimal("10"),
            trailing_stop_pct=Decimal("15"),
            volatility_window=20,
            max_volatility_pct=Decimal("85"),
            drawdown_guard_pct=Decimal("25"),
            cooldown_days=20,
        )

        self.assertEqual(result["strategy_name"], "controlled_ma")
        self.assertIn("max_drawdown_pct", result)
        self.assertIn("verdict", result)
        self.assertIn("rank_score", result)

    def test_drawdown_control_lab_inserts_results(self):
        candles = self.make_candles(220)
        self.seed_candles(candles)

        result = run_drawdown_control_lab(
            db_path=self.db_path,
            chain_id=0,
            symbol="ETHUSDT",
            timeframe="1d",
            source="binance_spot",
            initial_capital=Decimal("10000"),
            fee_bps=10,
            slippage_bps=10,
            run_label="test_drawdown_control_lab",
        )

        self.assertEqual(result["symbol"], "ETHUSDT")
        self.assertEqual(result["candidate_count"], 5)
        self.assertEqual(len(result["ranked_candidates"]), 5)
        self.assertIn("best_candidate", result)

        self.assertIn(
            result["global_verdict"],
            [
                "RISK_CONTROL_CANDIDATE_FOUND_NO_LIVE_TRADING",
                "REJECT_ALL_NO_LIVE_TRADING",
            ],
        )

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        count = cur.execute("""
        SELECT COUNT(*)
        FROM drawdown_control_results
        """).fetchone()[0]

        conn.close()

        self.assertEqual(count, 5)


if __name__ == "__main__":
    unittest.main()
