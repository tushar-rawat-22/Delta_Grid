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

from backtest.vt_tsmom_lab import (
    momentum_score_at,
    position_fraction_from_vol,
    result_verdict,
    run_vt_tsmom_lab,
    run_vt_tsmom_strategy,
    variant_specs,
)


class VolTargetTSMOMLabTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "vt_tsmom_test.db")

        init_market_database(self.db_path)

        upsert_chain(
            db_path=self.db_path,
            chain_id=0,
            name="Binance Spot",
            rpc_url="https://api.binance.com",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def make_candles(self, count=720):
        candles = []
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        price = Decimal("100")

        for index in range(count):
            if index < 180:
                price += Decimal("0.20")
            elif index < 300:
                price -= Decimal("0.08")
            elif index < 520:
                price += Decimal("0.28")
            else:
                price += Decimal("0.05")

            timestamp = start + timedelta(days=index)

            candles.append({
                "timestamp_utc": timestamp.isoformat(),
                "open": price - Decimal("0.30"),
                "high": price + Decimal("1.00"),
                "low": price - Decimal("1.00"),
                "close": price,
                "volume": Decimal("1000") + Decimal(index),
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
        self.assertEqual(specs[0]["name"], "vt_tsmom")

    def test_momentum_score_at(self):
        closes = [
            Decimal("100"),
            Decimal("101"),
            Decimal("102"),
            Decimal("103"),
            Decimal("104"),
            Decimal("105"),
        ]

        score = momentum_score_at(closes, 5, [1, 2, 3])

        self.assertEqual(score, Decimal("3"))

    def test_position_fraction_from_vol_clamps(self):
        low_vol_fraction = position_fraction_from_vol(
            realized_vol=Decimal("0.10"),
            target_vol=Decimal("0.25"),
            min_position_fraction=Decimal("0.20"),
            max_position_fraction=Decimal("1.00"),
        )

        high_vol_fraction = position_fraction_from_vol(
            realized_vol=Decimal("2.00"),
            target_vol=Decimal("0.25"),
            min_position_fraction=Decimal("0.20"),
            max_position_fraction=Decimal("1.00"),
        )

        self.assertEqual(low_vol_fraction, Decimal("1.00"))
        self.assertEqual(high_vol_fraction, Decimal("0.20"))

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
        candles = self.make_candles(320)

        result = run_vt_tsmom_strategy(
            candles=candles,
            initial_capital=Decimal("10000"),
            lookbacks=[14, 42, 84],
            ema_trend=150,
            ema_exit=75,
            adx_period=14,
            adx_min=Decimal("18"),
            atr_period=14,
            atr_stop_mult=Decimal("2.5"),
            atr_trail_mult=Decimal("2.5"),
            target_vol=Decimal("0.20"),
            max_position_fraction=Decimal("0.90"),
            min_position_fraction=Decimal("0.15"),
            max_vol_percentile=Decimal("0.85"),
            panic_vol_percentile=Decimal("0.90"),
            cooldown=10,
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
        self.assertIn("avg_position_fraction", result)
        self.assertIn("momentum_signals", result)
        self.assertIn("verdict", result)

    def test_vt_tsmom_lab_inserts_results(self):
        candles = self.make_candles()
        self.seed_candles(candles)

        result = run_vt_tsmom_lab(
            db_path=self.db_path,
            chain_id=0,
            symbol="ETHUSDT",
            timeframe="1d",
            source="binance_spot",
            initial_capital=Decimal("10000"),
            fee_bps=10,
            slippage_bps=10,
            train_size=120,
            test_size=260,
            step_size=160,
            min_pass_ratio=Decimal("0.60"),
            run_label="test_vt_tsmom_lab",
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
        FROM vt_tsmom_split_results
        WHERE run_label = 'test_vt_tsmom_lab'
        """).fetchone()[0]

        summary_count = cur.execute("""
        SELECT COUNT(*)
        FROM vt_tsmom_summary
        WHERE run_label = 'test_vt_tsmom_lab'
        """).fetchone()[0]

        conn.close()

        self.assertEqual(split_count, result["split_results_created"])
        self.assertEqual(summary_count, result["summary_results_created"])


if __name__ == "__main__":
    unittest.main()
