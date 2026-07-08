import json
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from db.schema import init_market_database, utc_now

from backtest.funding_basis_model import ensure_schema as ensure_funding_basis_schema
from backtest.candidate_ranking_engine import ensure_schema as ensure_candidate_ranking_schema

from backtest.paper_trading_engine import (
    build_paper_position,
    ensure_schema,
    expected_funding_return_pct,
    profit_factor,
    run_paper_trading_engine,
    simulate_trade_from_position,
)


class PaperTradingEngineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "paper_trading_test.db")

        init_market_database(self.db_path)
        ensure_funding_basis_schema(self.db_path)
        ensure_candidate_ranking_schema(self.db_path)
        ensure_schema(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def seed_candidate(
        self,
        run_label,
        symbol,
        final_verdict,
        composite_score="120",
        annualized="30",
        net_edge="0.20",
        edge_ratio="3",
        combined_cost="0.05",
    ):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO candidate_ranking_results (
            run_label,
            source_scan_run_label,
            symbol,
            scanner_final_verdict,
            scanner_recommended_action,
            annualized_funding_rate_pct,
            net_expected_edge_pct,
            edge_to_cost_ratio,
            liquidity_score,
            funding_score,
            basis_risk_penalty,
            scanner_score,
            walk_forward_verdict,
            walk_forward_score,
            liquidation_verdict,
            max_safe_leverage,
            execution_cost_verdict,
            combined_cost_pct,
            net_execution_edge_pct,
            rejection_reasons_json,
            composite_score,
            final_verdict,
            recommended_action,
            assumptions_json,
            created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_label,
            "scan",
            symbol,
            "GO_FOR_RESEARCH",
            "PROMOTE_TO_CANDIDATE_RANKING_ENGINE",
            annualized,
            net_edge,
            edge_ratio,
            "80",
            "50",
            "0",
            "100",
            "GO_FOR_RESEARCH",
            "100",
            "LIQUIDATION_LEVERAGE_RISK_ACCEPTABLE_NO_LIVE_TRADING",
            "3.5",
            "EXECUTION_COST_ACCEPTABLE_NO_LIVE_TRADING",
            combined_cost,
            net_edge,
            json.dumps([]),
            composite_score,
            final_verdict,
            "PROMOTE_TO_PAPER_TRADING_CANDIDATE_SET",
            json.dumps({"test": True}),
            utc_now(),
        ))

        conn.commit()
        conn.close()

    def test_expected_funding_return_pct(self):
        result = expected_funding_return_pct(
            annualized_funding_rate_pct=Decimal("36.5"),
            holding_days=10,
            perp_weight=Decimal("0.5"),
        )

        self.assertEqual(result, Decimal("0.50"))

    def test_profit_factor(self):
        result = profit_factor([
            Decimal("10"),
            Decimal("-5"),
            Decimal("15"),
        ])

        self.assertEqual(result, Decimal("5"))

    def test_build_paper_position_go(self):
        candidate = {
            "candidate_result_id": 1,
            "symbol": "BTCUSDT",
            "annualized_funding_rate_pct": Decimal("30"),
            "combined_cost_pct": Decimal("0.05"),
        }

        position = build_paper_position(
            candidate=candidate,
            starting_equity_usd=Decimal("10000"),
            allocation_pct=Decimal("10"),
            max_allocation_usd=Decimal("1000"),
            gross_notional_multiplier=Decimal("2"),
            holding_days=7,
            perp_weight=Decimal("0.5"),
            default_cost_pct=Decimal("0.0755"),
            min_position_net_return_pct=Decimal("0.02"),
        )

        self.assertEqual(position["final_verdict"], "GO_PAPER_POSITION")
        self.assertEqual(position["allocation_usd"], Decimal("1000"))

    def test_simulate_trade_from_position(self):
        candidate = {
            "candidate_result_id": 1,
            "symbol": "BTCUSDT",
            "annualized_funding_rate_pct": Decimal("30"),
            "combined_cost_pct": Decimal("0.05"),
        }

        position = build_paper_position(
            candidate=candidate,
            starting_equity_usd=Decimal("10000"),
            allocation_pct=Decimal("10"),
            max_allocation_usd=Decimal("1000"),
            gross_notional_multiplier=Decimal("2"),
            holding_days=7,
            perp_weight=Decimal("0.5"),
            default_cost_pct=Decimal("0.0755"),
            min_position_net_return_pct=Decimal("0.02"),
        )

        trade = simulate_trade_from_position(position)

        self.assertEqual(trade["trade_verdict"], "PAPER_TRADE_WIN")
        self.assertTrue(trade["simulated_net_pnl_usd"] > Decimal("0"))

    def test_run_paper_trading_engine_no_eligible_candidates(self):
        self.seed_candidate(
            run_label="ranking_run",
            symbol="ETHUSDT",
            final_verdict="NO_GO_SCANNER_REJECTED",
            composite_score="50",
            annualized="8",
            net_edge="0.00",
            edge_ratio="1",
        )

        result = run_paper_trading_engine(
            db_path=self.db_path,
            ranking_run_label="ranking_run",
            run_label="paper_run",
            starting_equity_usd=Decimal("10000"),
            allocation_pct=Decimal("10"),
            max_allocation_usd=Decimal("1000"),
            max_positions=5,
            gross_notional_multiplier=Decimal("2"),
            holding_days=7,
            perp_weight=Decimal("0.5"),
            default_cost_pct=Decimal("0.0755"),
            min_composite_score=Decimal("75"),
            min_net_expected_edge_pct=Decimal("0.02"),
            min_edge_to_cost_ratio=Decimal("1.5"),
            min_position_net_return_pct=Decimal("0.02"),
            min_trades=1,
            min_total_return_pct=Decimal("0.01"),
            max_drawdown_limit_pct=Decimal("5"),
            min_profit_factor=Decimal("1.2"),
            allow_no_go_candidates=False,
        )

        self.assertEqual(result["eligible_candidates"], 0)
        self.assertEqual(result["trades_created"], 0)
        self.assertEqual(result["global_verdict"], "NO_GO_NO_ELIGIBLE_PAPER_CANDIDATES")

    def test_run_paper_trading_engine_with_go_candidate(self):
        self.seed_candidate(
            run_label="ranking_run",
            symbol="BTCUSDT",
            final_verdict="GO_FOR_RESEARCH_RANKED",
            composite_score="120",
            annualized="30",
            net_edge="0.20",
            edge_ratio="3",
            combined_cost="0.05",
        )

        result = run_paper_trading_engine(
            db_path=self.db_path,
            ranking_run_label="ranking_run",
            run_label="paper_run",
            starting_equity_usd=Decimal("10000"),
            allocation_pct=Decimal("10"),
            max_allocation_usd=Decimal("1000"),
            max_positions=5,
            gross_notional_multiplier=Decimal("2"),
            holding_days=7,
            perp_weight=Decimal("0.5"),
            default_cost_pct=Decimal("0.0755"),
            min_composite_score=Decimal("75"),
            min_net_expected_edge_pct=Decimal("0.02"),
            min_edge_to_cost_ratio=Decimal("1.5"),
            min_position_net_return_pct=Decimal("0.02"),
            min_trades=1,
            min_total_return_pct=Decimal("0.01"),
            max_drawdown_limit_pct=Decimal("5"),
            min_profit_factor=Decimal("1.2"),
            allow_no_go_candidates=False,
        )

        self.assertEqual(result["eligible_candidates"], 1)
        self.assertEqual(result["positions_created"], 1)
        self.assertEqual(result["trades_created"], 1)
        self.assertEqual(result["global_verdict"], "GO_PAPER_TRADING_VALIDATED")

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        positions = cur.execute("""
        SELECT COUNT(*)
        FROM paper_trading_positions
        WHERE run_label = 'paper_run'
        """).fetchone()[0]

        trades = cur.execute("""
        SELECT COUNT(*)
        FROM paper_trading_trades
        WHERE run_label = 'paper_run'
        """).fetchone()[0]

        summary = cur.execute("""
        SELECT COUNT(*)
        FROM paper_trading_summary
        WHERE run_label = 'paper_run'
        """).fetchone()[0]

        conn.close()

        self.assertEqual(positions, 1)
        self.assertEqual(trades, 1)
        self.assertEqual(summary, 1)


if __name__ == "__main__":
    unittest.main()
