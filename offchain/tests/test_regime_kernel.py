import unittest
from decimal import Decimal


from backtest.regime_kernel import (
    build_regime_features,
    classify_regime_at,
    classify_regimes,
    extract_ohlcv,
)


class RegimeKernelTest(unittest.TestCase):
    def make_candles(self, count=260):
        candles = []
        price = Decimal("100")

        for index in range(count):
            price += Decimal("0.50")

            candles.append({
                "timestamp_utc": f"2024-01-{(index % 28) + 1:02d}T00:00:00+00:00",
                "open": price - Decimal("0.25"),
                "high": price + Decimal("1.00"),
                "low": price - Decimal("1.00"),
                "close": price,
                "volume": Decimal("1000") + Decimal(index),
            })

        return candles

    def test_extract_ohlcv(self):
        candles = self.make_candles(5)

        ohlcv = extract_ohlcv(candles)

        self.assertEqual(len(ohlcv["open"]), 5)
        self.assertEqual(len(ohlcv["high"]), 5)
        self.assertEqual(len(ohlcv["low"]), 5)
        self.assertEqual(len(ohlcv["close"]), 5)
        self.assertEqual(len(ohlcv["volume"]), 5)
        self.assertEqual(ohlcv["close"][0], Decimal("100.50"))

    def test_build_regime_features(self):
        candles = self.make_candles()

        features = build_regime_features(candles)

        self.assertEqual(len(features["close"]), len(candles))
        self.assertEqual(len(features["ema_20"]), len(candles))
        self.assertEqual(len(features["ema_50"]), len(candles))
        self.assertEqual(len(features["ema_200"]), len(candles))
        self.assertEqual(len(features["atr_14"]), len(candles))
        self.assertEqual(len(features["adx_14"]), len(candles))
        self.assertEqual(len(features["bb_width_pct_120"]), len(candles))

        self.assertIsNotNone(features["ema_200"][-1])
        self.assertIsNotNone(features["atr_14"][-1])
        self.assertIsNotNone(features["adx_14"][-1])

    def test_classify_insufficient_data(self):
        candles = self.make_candles(20)

        regimes = classify_regimes(candles)

        self.assertEqual(regimes[0]["primary_regime"], "INSUFFICIENT_DATA")
        self.assertIn("INSUFFICIENT_DATA", regimes[0]["labels"])

    def test_classify_bull_compression_regime(self):
        features = {
            "close": [Decimal("120")],
            "ema_50": [Decimal("110")],
            "ema_200": [Decimal("100")],
            "adx_14": [Decimal("25")],
            "atr_pct_120": [Decimal("0.20")],
            "bb_width_pct_120": [Decimal("0.20")],
            "realized_vol_pct_120": [Decimal("0.30")],
        }

        regime = classify_regime_at(features, 0)

        self.assertEqual(regime["primary_regime"], "BULL_TREND")
        self.assertIn("BULL_TREND", regime["labels"])
        self.assertIn("COMPRESSION", regime["labels"])
        self.assertIn("LOW_VOLATILITY", regime["labels"])

    def test_classify_panic_volatility_priority(self):
        features = {
            "close": [Decimal("120")],
            "ema_50": [Decimal("110")],
            "ema_200": [Decimal("100")],
            "adx_14": [Decimal("30")],
            "atr_pct_120": [Decimal("0.95")],
            "bb_width_pct_120": [Decimal("0.90")],
            "realized_vol_pct_120": [Decimal("0.95")],
        }

        regime = classify_regime_at(features, 0)

        self.assertEqual(regime["primary_regime"], "PANIC_VOLATILITY")
        self.assertIn("PANIC_VOLATILITY", regime["labels"])
        self.assertIn("HIGH_VOLATILITY", regime["labels"])
        self.assertIn("EXPANSION", regime["labels"])

    def test_classify_regimes_full_series(self):
        candles = self.make_candles()

        regimes = classify_regimes(candles)

        self.assertEqual(len(regimes), len(candles))
        self.assertNotEqual(regimes[-1]["primary_regime"], "INSUFFICIENT_DATA")
        self.assertIn("primary_regime", regimes[-1])
        self.assertIn("labels", regimes[-1])


if __name__ == "__main__":
    unittest.main()
