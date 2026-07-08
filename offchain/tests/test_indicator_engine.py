import unittest
from decimal import Decimal

from backtest.indicator_engine import (
    adx,
    atr,
    bollinger_bandwidth,
    donchian_channel,
    ema,
    rolling_percentile_rank,
    rolling_realized_volatility,
    rolling_std,
    rsi,
    simple_returns,
    sma,
    true_range,
)


class IndicatorEngineTest(unittest.TestCase):
    def test_sma_and_ema(self):
        values = [1, 2, 3, 4, 5]

        sma_values = sma(values, 3)
        ema_values = ema(values, 3)

        self.assertIsNone(sma_values[0])
        self.assertEqual(sma_values[2], Decimal("2"))
        self.assertEqual(sma_values[4], Decimal("4"))

        self.assertIsNone(ema_values[1])
        self.assertEqual(ema_values[2], Decimal("2"))
        self.assertEqual(ema_values[3], Decimal("3"))
        self.assertEqual(ema_values[4], Decimal("4"))

    def test_rolling_std_and_percentile_rank(self):
        values = [1, 2, 3, 2, 5]

        std_values = rolling_std(values, 3)
        percentile_values = rolling_percentile_rank(values, 3)

        self.assertIsNone(std_values[1])
        self.assertGreater(std_values[2], Decimal("0"))

        self.assertEqual(percentile_values[2], Decimal("1"))
        self.assertEqual(percentile_values[3], Decimal("0.6666666666666666666666666666666666666667"))

    def test_true_range_and_atr(self):
        highs = [11, 12, 13, 14, 15]
        lows = [8, 9, 10, 11, 12]
        closes = [9, 11, 12, 13, 14]

        self.assertEqual(true_range(12, 9, 9), Decimal("3"))

        atr_values = atr(highs, lows, closes, 3)

        self.assertIsNone(atr_values[1])
        self.assertEqual(atr_values[2], Decimal("3"))
        self.assertEqual(atr_values[4], Decimal("3"))

    def test_rsi(self):
        closes = [1, 2, 3, 2, 3, 4, 5, 4, 5, 6]

        rsi_values = rsi(closes, 3)

        self.assertIsNone(rsi_values[2])
        self.assertIsNotNone(rsi_values[3])
        self.assertGreaterEqual(rsi_values[5], Decimal("0"))
        self.assertLessEqual(rsi_values[5], Decimal("100"))

    def test_bollinger_bandwidth(self):
        closes = [10, 11, 12, 13, 14, 15, 16]

        bandwidth = bollinger_bandwidth(closes, 3, Decimal("2"))

        self.assertIsNone(bandwidth[1])
        self.assertIsNotNone(bandwidth[3])
        self.assertGreater(bandwidth[3], Decimal("0"))

    def test_donchian_channel(self):
        highs = [10, 11, 12, 13, 14]
        lows = [9, 8, 7, 6, 5]

        channel = donchian_channel(highs, lows, 3)

        self.assertIsNone(channel["high"][2])
        self.assertEqual(channel["high"][3], Decimal("12"))
        self.assertEqual(channel["low"][3], Decimal("7"))
        self.assertEqual(channel["high"][4], Decimal("13"))
        self.assertEqual(channel["low"][4], Decimal("6"))

    def test_returns_and_realized_volatility(self):
        closes = [100, 101, 99, 102, 104, 103, 105]

        returns = simple_returns(closes)
        vol = rolling_realized_volatility(closes, 3)

        self.assertIsNone(returns[0])
        self.assertIsNotNone(returns[1])
        self.assertIsNone(vol[2])
        self.assertIsNotNone(vol[3])
        self.assertGreater(vol[3], Decimal("0"))

    def test_adx(self):
        highs = [
            10, 11, 12, 13, 14, 15, 16, 17, 18, 19,
            20, 21, 22, 23, 24, 25, 26, 27, 28, 29,
            30, 31, 32, 33, 34, 35, 36, 37, 38, 39,
            40, 41, 42, 43, 44
        ]

        lows = [
            8, 9, 10, 11, 12, 13, 14, 15, 16, 17,
            18, 19, 20, 21, 22, 23, 24, 25, 26, 27,
            28, 29, 30, 31, 32, 33, 34, 35, 36, 37,
            38, 39, 40, 41, 42
        ]

        closes = [
            9, 10, 11, 12, 13, 14, 15, 16, 17, 18,
            19, 20, 21, 22, 23, 24, 25, 26, 27, 28,
            29, 30, 31, 32, 33, 34, 35, 36, 37, 38,
            39, 40, 41, 42, 43
        ]

        adx_values = adx(highs, lows, closes, 14)

        self.assertIsNone(adx_values[27])
        self.assertIsNotNone(adx_values[28])
        self.assertGreaterEqual(adx_values[28], Decimal("0"))


if __name__ == "__main__":
    unittest.main()
