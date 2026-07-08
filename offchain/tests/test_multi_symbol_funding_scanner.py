import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from db.schema import init_market_database

from backtest.funding_basis_model import ensure_schema as ensure_funding_basis_schema

from backtest.multi_symbol_funding_scanner import (
    annualize_funding_rate_pct,
    basis_pct,
    build_lookup,
    ensure_schema,
    evaluate_symbol,
    parse_symbols,
    run_multi_symbol_funding_scanner,
    scanner_score,
)


class MultiSymbolFundingScannerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "multi_symbol_scanner_test.db")

        init_market_database(self.db_path)
        ensure_funding_basis_schema(self.db_path)
        ensure_schema(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def fake_client(self, endpoint, params=None, timeout=10):
        if endpoint == "/fapi/v1/ticker/24hr":
            return [
                {
                    "symbol": "BTCUSDT",
                    "priceChangePercent": "2.5",
                    "quoteVolume": "2000000000",
                },
                {
                    "symbol": "ETHUSDT",
                    "priceChangePercent": "1.2",
                    "quoteVolume": "900000000",
                },
            ]

        if endpoint == "/fapi/v1/premiumIndex":
            return [
                {
                    "symbol": "BTCUSDT",
                    "markPrice": "100000",
                    "indexPrice": "99900",
                    "lastFundingRate": "0.00025",
                },
                {
                    "symbol": "ETHUSDT",
                    "markPrice": "3000",
                    "indexPrice": "3001",
                    "lastFundingRate": "0.00002",
                },
            ]

        if endpoint == "/fapi/v1/openInterest":
            symbol = params["symbol"]

            if symbol == "BTCUSDT":
                return {
                    "symbol": symbol,
                    "openInterest": "10000",
                }

            return {
                "symbol": symbol,
                "openInterest": "100000",
            }

        raise ValueError(endpoint)

    def test_parse_symbols(self):
        symbols = parse_symbols("btcusdt, ethusdt, BTCUSDT")

        self.assertEqual(symbols, ["BTCUSDT", "ETHUSDT"])

    def test_annualize_funding_rate_pct(self):
        value = annualize_funding_rate_pct(
            funding_rate=Decimal("0.0001"),
            interval_hours=Decimal("8"),
        )

        self.assertEqual(value, Decimal("10.9500"))

    def test_basis_pct(self):
        value = basis_pct(
            mark_price=Decimal("101"),
            index_price=Decimal("100"),
        )

        self.assertEqual(value, Decimal("1.00"))

    def test_build_lookup(self):
        lookup = build_lookup([
            {
                "symbol": "BTCUSDT",
                "value": 1,
            }
        ])

        self.assertEqual(lookup["BTCUSDT"]["value"], 1)

    def test_evaluate_symbol_go(self):
        result = evaluate_symbol(
            symbol="BTCUSDT",
            ticker_row={
                "symbol": "BTCUSDT",
                "priceChangePercent": "2.5",
                "quoteVolume": "2000000000",
            },
            premium_row={
                "symbol": "BTCUSDT",
                "markPrice": "100000",
                "indexPrice": "99900",
                "lastFundingRate": "0.00025",
            },
            open_interest_row={
                "symbol": "BTCUSDT",
                "openInterest": "10000",
            },
            holding_days=7,
            interval_hours=Decimal("8"),
            perp_weight=Decimal("0.5"),
            combined_cost_proxy_pct=Decimal("0.0755"),
            min_abs_annualized_funding_pct=Decimal("10"),
            min_quote_volume_24h=Decimal("100000000"),
            min_open_interest_value_usd=Decimal("25000000"),
            min_basis_pct=Decimal("-1"),
            max_basis_pct=Decimal("1.5"),
            min_net_expected_edge_pct=Decimal("0.02"),
            min_edge_to_cost_ratio=Decimal("1.5"),
            min_scanner_score=Decimal("50"),
        )

        self.assertEqual(result["final_verdict"], "GO_FOR_RESEARCH")
        self.assertTrue(result["scanner_score"] > Decimal("50"))

    def test_scanner_score_penalizes_bad_basis(self):
        good = scanner_score(
            annualized_funding_rate_pct=Decimal("25"),
            quote_volume_24h=Decimal("1000000000"),
            open_interest_value_usd=Decimal("500000000"),
            basis_value_pct=Decimal("0.10"),
            net_expected_edge_pct=Decimal("0.20"),
            edge_to_cost_ratio=Decimal("3"),
        )

        bad = scanner_score(
            annualized_funding_rate_pct=Decimal("25"),
            quote_volume_24h=Decimal("1000000000"),
            open_interest_value_usd=Decimal("500000000"),
            basis_value_pct=Decimal("2.00"),
            net_expected_edge_pct=Decimal("0.20"),
            edge_to_cost_ratio=Decimal("3"),
        )

        self.assertTrue(good > bad)

    def test_run_multi_symbol_funding_scanner_inserts_results(self):
        result = run_multi_symbol_funding_scanner(
            db_path=self.db_path,
            symbols=["BTCUSDT", "ETHUSDT"],
            run_label="test_multi_symbol_scan",
            holding_days=7,
            interval_hours=Decimal("8"),
            perp_weight=Decimal("0.5"),
            combined_cost_proxy_pct=Decimal("0.0755"),
            min_abs_annualized_funding_pct=Decimal("10"),
            min_quote_volume_24h=Decimal("100000000"),
            min_open_interest_value_usd=Decimal("25000000"),
            min_basis_pct=Decimal("-1"),
            max_basis_pct=Decimal("1.5"),
            min_net_expected_edge_pct=Decimal("0.02"),
            min_edge_to_cost_ratio=Decimal("1.5"),
            min_scanner_score=Decimal("50"),
            timeout=5,
            client=self.fake_client,
        )

        self.assertEqual(result["symbols_requested"], 2)
        self.assertEqual(result["symbols_scanned"], 2)
        self.assertEqual(result["results_created"], 2)
        self.assertEqual(result["go_count"], 1)
        self.assertEqual(result["best_symbol"], "BTCUSDT")

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        result_count = cur.execute("""
        SELECT COUNT(*)
        FROM multi_symbol_funding_scan_results
        WHERE run_label = 'test_multi_symbol_scan'
        """).fetchone()[0]

        summary_count = cur.execute("""
        SELECT COUNT(*)
        FROM multi_symbol_funding_scan_summary
        WHERE run_label = 'test_multi_symbol_scan'
        """).fetchone()[0]

        conn.close()

        self.assertEqual(result_count, 2)
        self.assertEqual(summary_count, 1)


if __name__ == "__main__":
    unittest.main()
