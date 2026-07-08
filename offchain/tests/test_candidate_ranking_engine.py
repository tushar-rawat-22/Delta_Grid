import json
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from db.schema import init_market_database, utc_now

from backtest.funding_basis_model import ensure_schema as ensure_funding_basis_schema
from backtest.multi_symbol_funding_scanner import ensure_schema as ensure_multi_symbol_scan_schema
from backtest.funding_walk_forward_validation import ensure_schema as ensure_walk_forward_schema
from backtest.liquidation_leverage_risk_model import ensure_schema as ensure_liquidation_risk_schema
from backtest.execution_cost_slippage_simulator import ensure_schema as ensure_execution_cost_schema

from backtest.candidate_ranking_engine import (
    compute_composite_score,
    ensure_schema,
    evaluate_candidate,
    run_candidate_ranking_engine,
)


class CandidateRankingEngineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "candidate_ranking_test.db")

        init_market_database(self.db_path)
        ensure_funding_basis_schema(self.db_path)
        ensure_multi_symbol_scan_schema(self.db_path)
        ensure_walk_forward_schema(self.db_path)
        ensure_liquidation_risk_schema(self.db_path)
        ensure_execution_cost_schema(self.db_path)
        ensure_schema(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def seed_scan_result(
        self,
        symbol,
        run_label,
        scanner_score,
        final_verdict,
        annualized="25",
        net_edge="0.20",
        edge_ratio="3.0",
        liquidity_score="80",
    ):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO multi_symbol_funding_scan_results (
            run_label,
            exchange,
            symbol,
            current_funding_rate,
            annualized_funding_rate_pct,
            mark_price,
            index_price,
            basis_pct,
            price_change_pct_24h,
            quote_volume_24h,
            open_interest,
            open_interest_value_usd,
            expected_funding_edge_pct,
            combined_cost_proxy_pct,
            net_expected_edge_pct,
            edge_to_cost_ratio,
            liquidity_score,
            funding_score,
            basis_risk_penalty,
            scanner_score,
            final_verdict,
            recommended_action,
            assumptions_json,
            created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_label,
            "Binance Futures",
            symbol,
            "0.00025",
            annualized,
            "100",
            "99.9",
            "0.10",
            "1.5",
            "2000000000",
            "10000",
            "1000000000",
            "0.275",
            "0.0755",
            net_edge,
            edge_ratio,
            liquidity_score,
            "50",
            "0",
            scanner_score,
            final_verdict,
            "PROMOTE_TO_CANDIDATE_RANKING_ENGINE" if final_verdict == "GO_FOR_RESEARCH" else "IGNORE_UNTIL_FUNDING_EXPANDS",
            json.dumps({"test": True}),
            utc_now(),
        ))

        conn.commit()
        conn.close()

    def seed_walk_forward_go(self, symbol, run_label):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO funding_walk_forward_summary (
            run_label,
            source_run_label,
            symbol,
            variant_name,
            variant_version,
            splits_tested,
            go_splits,
            no_go_splits,
            total_trades,
            avg_net_return_pct,
            total_net_return_pct,
            avg_trade_return_pct,
            worst_drawdown_pct,
            avg_profit_factor,
            avg_positive_funding_ratio_pct,
            avg_annualized_funding_pct,
            stability_score,
            final_verdict,
            recommended_action,
            assumptions_json,
            created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_label,
            "source",
            symbol,
            "funding_wf",
            "test_go",
            3,
            3,
            0,
            6,
            "0.25",
            "0.75",
            "0.12",
            "0.50",
            "2.50",
            "100",
            "25",
            "125",
            "GO_FOR_RESEARCH",
            "PROMOTE_TO_FUNDING_RISK_MODELING",
            json.dumps({"test": True}),
            utc_now(),
        ))

        conn.commit()
        conn.close()

    def seed_liquidation_go(self, symbol, run_label):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO liquidation_leverage_risk_summary (
            run_label,
            source_run_label,
            symbol,
            scenarios_tested,
            go_count,
            no_go_count,
            best_result_id,
            best_variant_version,
            best_max_safe_leverage,
            worst_buffer_after_stress_pct,
            worst_total_stress_loss_pct,
            global_verdict,
            recommended_action,
            assumptions_json,
            created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_label,
            "source",
            symbol,
            3,
            2,
            1,
            1,
            "conservative",
            "3.5",
            "10",
            "3",
            "LIQUIDATION_LEVERAGE_RISK_ACCEPTABLE_NO_LIVE_TRADING",
            "PROMOTE_TO_FUNDING_RISK_INTEGRATION",
            json.dumps({"test": True}),
            utc_now(),
        ))

        conn.commit()
        conn.close()

    def seed_execution_go(self, symbol, run_label):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO execution_cost_slippage_summary (
            run_label,
            source_run_label,
            symbol,
            scenarios_tested,
            go_count,
            no_go_count,
            best_result_id,
            best_scenario_version,
            best_net_expected_edge_pct,
            lowest_combined_cost_pct,
            highest_combined_cost_pct,
            global_verdict,
            recommended_action,
            assumptions_json,
            created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_label,
            "source",
            symbol,
            3,
            1,
            2,
            1,
            "small",
            "0.20",
            "0.05",
            "0.10",
            "EXECUTION_COST_ACCEPTABLE_NO_LIVE_TRADING",
            "PROMOTE_TO_MULTI_SYMBOL_SCANNER",
            json.dumps({"test": True}),
            utc_now(),
        ))

        conn.commit()
        conn.close()

    def test_composite_score_rewards_good_gates(self):
        candidate = {
            "scanner_score": Decimal("100"),
            "net_expected_edge_pct": Decimal("0.20"),
            "edge_to_cost_ratio": Decimal("3"),
            "liquidity_score": Decimal("80"),
            "annualized_funding_rate_pct": Decimal("25"),
            "basis_risk_penalty": Decimal("0"),
        }

        good = compute_composite_score(
            candidate=candidate,
            walk_forward={
                "walk_forward_verdict": "GO_FOR_RESEARCH",
            },
            liquidation={
                "liquidation_verdict": "LIQUIDATION_LEVERAGE_RISK_ACCEPTABLE_NO_LIVE_TRADING",
            },
            execution_cost={
                "execution_cost_verdict": "EXECUTION_COST_ACCEPTABLE_NO_LIVE_TRADING",
            },
        )

        bad = compute_composite_score(
            candidate=candidate,
            walk_forward={
                "walk_forward_verdict": "NO_GO_WALK_FORWARD_STABILITY",
            },
            liquidation={
                "liquidation_verdict": "REJECT_ALL_LEVERAGE_SCENARIOS_NO_LIVE_TRADING",
            },
            execution_cost={
                "execution_cost_verdict": "REJECT_ALL_EXECUTION_COST_SCENARIOS_NO_LIVE_TRADING",
            },
        )

        self.assertGreater(good, bad)

    def test_evaluate_candidate_go(self):
        candidate = {
            "symbol": "BTCUSDT",
            "scanner_final_verdict": "GO_FOR_RESEARCH",
            "scanner_recommended_action": "PROMOTE_TO_CANDIDATE_RANKING_ENGINE",
            "annualized_funding_rate_pct": Decimal("25"),
            "net_expected_edge_pct": Decimal("0.20"),
            "edge_to_cost_ratio": Decimal("3"),
            "liquidity_score": Decimal("80"),
            "funding_score": Decimal("50"),
            "basis_risk_penalty": Decimal("0"),
            "scanner_score": Decimal("100"),
        }

        result = evaluate_candidate(
            candidate=candidate,
            walk_forward={
                "walk_forward_verdict": "GO_FOR_RESEARCH",
                "walk_forward_score": Decimal("100"),
            },
            liquidation={
                "liquidation_verdict": "LIQUIDATION_LEVERAGE_RISK_ACCEPTABLE_NO_LIVE_TRADING",
                "max_safe_leverage": Decimal("3.5"),
            },
            execution_cost={
                "execution_cost_verdict": "EXECUTION_COST_ACCEPTABLE_NO_LIVE_TRADING",
                "combined_cost_pct": Decimal("0.05"),
                "net_execution_edge_pct": Decimal("0.20"),
            },
            min_net_expected_edge_pct=Decimal("0.02"),
            min_edge_to_cost_ratio=Decimal("1.5"),
            min_composite_score=Decimal("75"),
            require_walk_forward=True,
            require_liquidation=True,
            require_execution_cost=True,
        )

        self.assertEqual(result["final_verdict"], "GO_FOR_RESEARCH_RANKED")

    def test_run_candidate_ranking_engine_inserts_results(self):
        self.seed_scan_result(
            symbol="BTCUSDT",
            run_label="scan_run",
            scanner_score="110",
            final_verdict="GO_FOR_RESEARCH",
        )

        self.seed_scan_result(
            symbol="ETHUSDT",
            run_label="scan_run",
            scanner_score="80",
            final_verdict="NO_GO_LOW_FUNDING",
            annualized="5",
            net_edge="-0.05",
            edge_ratio="0.5",
        )

        self.seed_walk_forward_go("BTCUSDT", "wf_run")
        self.seed_liquidation_go("BTCUSDT", "liq_run")
        self.seed_execution_go("BTCUSDT", "cost_run")

        result = run_candidate_ranking_engine(
            db_path=self.db_path,
            scan_run_label="scan_run",
            walk_forward_run_label="wf_run",
            liquidation_run_label="liq_run",
            execution_cost_run_label="cost_run",
            run_label="ranking_run",
            min_net_expected_edge_pct=Decimal("0.02"),
            min_edge_to_cost_ratio=Decimal("1.5"),
            min_composite_score=Decimal("75"),
            require_walk_forward=True,
            require_liquidation=True,
            require_execution_cost=True,
        )

        self.assertEqual(result["candidates_seen"], 2)
        self.assertEqual(result["ranked_count"], 2)
        self.assertEqual(result["go_count"], 1)
        self.assertEqual(result["best_symbol"], "BTCUSDT")

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        result_count = cur.execute("""
        SELECT COUNT(*)
        FROM candidate_ranking_results
        WHERE run_label = 'ranking_run'
        """).fetchone()[0]

        summary_count = cur.execute("""
        SELECT COUNT(*)
        FROM candidate_ranking_summary
        WHERE run_label = 'ranking_run'
        """).fetchone()[0]

        conn.close()

        self.assertEqual(result_count, 2)
        self.assertEqual(summary_count, 1)


if __name__ == "__main__":
    unittest.main()
