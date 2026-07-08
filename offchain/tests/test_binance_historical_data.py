import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backtest.binance_historical_data import (
    ingest_binance_klines,
    normalize_kline,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class BinanceHistoricalDataTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "binance_test.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_normalize_kline(self):
        row = [
            1672531200000,
            "1000",
            "1100",
            "900",
            "1050",
            "123.45",
            1672617599999,
            "99999",
            100,
            "50",
            "50000",
            "0",
        ]

        candle = normalize_kline(row)

        self.assertEqual(candle["timestamp_utc"], "2023-01-01T00:00:00+00:00")
        self.assertEqual(candle["open"], "1000")
        self.assertEqual(candle["high"], "1100")
        self.assertEqual(candle["low"], "900")
        self.assertEqual(candle["close"], "1050")
        self.assertEqual(candle["volume"], "123.45")

    @patch("backtest.binance_historical_data.requests.get")
    def test_ingest_binance_klines(self, mock_get):
        mock_get.return_value = FakeResponse([
            [
                1672531200000,
                "1000",
                "1100",
                "900",
                "1050",
                "123.45",
                1672617599999,
                "99999",
                100,
                "50",
                "50000",
                "0",
            ],
            [
                1672617600000,
                "1050",
                "1200",
                "1000",
                "1150",
                "200",
                1672703999999,
                "99999",
                120,
                "80",
                "80000",
                "0",
            ],
        ])

        result = ingest_binance_klines(
            db_path=self.db_path,
            symbol="ETHUSDT",
            interval="1d",
            start_date="2023-01-01",
            end_date="2023-01-03",
            limit=1000,
        )

        self.assertEqual(result["source"], "binance_spot")
        self.assertEqual(result["symbol"], "ETHUSDT")
        self.assertEqual(result["candles_inserted_or_updated"], 2)
        self.assertEqual(result["requests_made"], 1)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        count = cur.execute("""
        SELECT COUNT(*)
        FROM historical_candles
        WHERE source = 'binance_spot'
        AND symbol = 'ETHUSDT'
        """).fetchone()[0]

        close_values = cur.execute("""
        SELECT close
        FROM historical_candles
        WHERE source = 'binance_spot'
        AND symbol = 'ETHUSDT'
        ORDER BY timestamp_utc
        """).fetchall()

        conn.close()

        self.assertEqual(count, 2)
        self.assertEqual(close_values[0][0], "1050")
        self.assertEqual(close_values[1][0], "1150")


if __name__ == "__main__":
    unittest.main()
