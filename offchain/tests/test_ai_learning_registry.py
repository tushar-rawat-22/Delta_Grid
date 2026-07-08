import json
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from db.schema import init_market_database, utc_now

from backtest.funding_basis_model import ensure_schema as ensure_funding_basis_schema
from backtest.candidate_ranking_engine import ensure_schema as ensure_candidate_ranking_schema
from backtest.paper_trading_engine import ensure_schema as ensure_paper_trading_schema

from backtest.ai_learning_registry import (
    build_features,
    build_labels,
    ensure_schema,
    learning_example_verdict,
    run_ai_learning_registry,
    train_baseline_model,
)


class AILearningRegistryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "ai_learning_test.db")

        init_market_database(self.db_path)
        ensure_funding_basis_schema(self.db_path)
        ensure_candidate_ranking_schema(self.db_path)
        ensure_paper_trading_schema(self.db_path)
        ensure_schema(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def seed_candidate(
        self,
        run_label,
        symbol,
        final_verdict,
        composite_score,
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
            "GO_FOR_RESEARCH" if final_verdict == "GO_FOR_RESEARCH_RANKED" else "NO_GO_LOW_FUNDING",
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

        row_id = cur.lastrowid

        conn.commit()
        conn.close()

        return int(row_id)

    def seed_paper_trade(
        self,
        paper_run_label,
        candidate_result_id,
        symbol,
        net_return_pct,
        net_pnl_usd,
    ):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO paper_trading_positions (
            run_label,
            source_ranking_run_label,
            candidate_result_id,
            symbol,
            allocation_usd,
            gross_notional_usd,
            spot_notional_usd,
            perp_notional_usd,
            annualized_funding_rate_pct,
            expected_holding_days,
            expected_funding_return_pct,
            expected_cost_pct,
            expected_net_return_pct,
            entry_time_utc,
            planned_exit_time_utc,
            status,
            final_verdict,
            recommended_action,
            assumptions_json,
            created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            paper_run_label,
            "ranking_run",
            candidate_result_id,
            symbol,
            "1000",
            "2000",
            "1000",
            "1000",
            "30",
            7,
            "0.2876712328767123287671232876712328767123",
            "0.05",
            str(net_return_pct),
            "2026-07-08T00:00:00Z",
            "2026-07-15T00:00:00Z",
            "CLOSED_SIMULATED",
            "GO_PAPER_POSITION",
            "SIMULATE_PAPER_TRADE",
            json.dumps({"test": True}),
            utc_now(),
        ))

        position_id = cur.lastrowid

        verdict = "PAPER_TRADE_WIN" if Decimal(str(net_pnl_usd)) > 0 else "PAPER_TRADE_LOSS"

        cur.execute("""
        INSERT INTO paper_trading_trades (
            run_label,
            source_ranking_run_label,
            position_id,
            symbol,
            side_description,
            entry_time_utc,
            exit_time_utc,
            holding_days,
            allocation_usd,
            gross_notional_usd,
            gross_funding_pnl_usd,
            execution_cost_usd,
            simulated_net_pnl_usd,
            simulated_net_return_pct,
            trade_verdict,
            exit_reason,
            assumptions_json,
            created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            paper_run_label,
            "ranking_run",
            position_id,
            symbol,
            "SIMULATED_LONG_SPOT_SHORT_PERP",
            "2026-07-08T00:00:00Z",
            "2026-07-15T00:00:00Z",
            7,
            "1000",
            "2000",
            "2.8767",
            "0.5",
            str(net_pnl_usd),
            str(net_return_pct),
            verdict,
            "TEST_EXIT",
            json.dumps({"test": True}),
            utc_now(),
        ))

        trade_id = cur.lastrowid

        conn.commit()
        conn.close()

        return int(position_id), int(trade_id)

    def test_build_features(self):
        row = {
            "annualized_funding_rate_pct": Decimal("30"),
            "net_expected_edge_pct": Decimal("0.20"),
            "edge_to_cost_ratio": Decimal("3"),
            "liquidity_score": Decimal("80"),
            "funding_score": Decimal("50"),
            "basis_risk_penalty": Decimal("0"),
            "scanner_score": Decimal("100"),
            "composite_score": Decimal("120"),
            "combined_cost_pct": Decimal("0.05"),
            "scanner_final_verdict": "GO_FOR_RESEARCH",
            "ranking_final_verdict": "GO_FOR_RESEARCH_RANKED",
            "walk_forward_verdict": "GO_FOR_RESEARCH",
            "liquidation_verdict": "LIQUIDATION_LEVERAGE_RISK_ACCEPTABLE_NO_LIVE_TRADING",
            "execution_cost_verdict": "EXECUTION_COST_ACCEPTABLE_NO_LIVE_TRADING",
        }

        features = build_features(row)

        self.assertEqual(features["scanner_go"], 1)
        self.assertEqual(features["ranking_go"], 1)
        self.assertEqual(features["composite_score"], "120")

    def test_build_labels_from_winning_trade(self):
        row = {
            "paper_trade_id": 10,
            "simulated_net_return_pct": Decimal("0.20"),
            "simulated_net_pnl_usd": Decimal("2"),
        }

        labels = build_labels(
            row=row,
            min_label_net_return_pct=Decimal("0.05"),
        )

        self.assertEqual(labels["label_profitable"], 1)
        self.assertEqual(labels["label_go"], 1)
        self.assertEqual(labels["eligible_for_training"], 1)

    def test_build_labels_without_trade_not_eligible(self):
        row = {
            "paper_trade_id": None,
            "simulated_net_return_pct": Decimal("0"),
            "simulated_net_pnl_usd": Decimal("0"),
        }

        labels = build_labels(
            row=row,
            min_label_net_return_pct=Decimal("0.05"),
        )

        self.assertEqual(labels["label_profitable"], 0)
        self.assertEqual(labels["label_go"], 0)
        self.assertEqual(labels["eligible_for_training"], 0)
        self.assertEqual(learning_example_verdict(labels), "OBSERVATION_ONLY_NOT_TRAINING_ELIGIBLE")

    def test_train_baseline_rejects_insufficient_data(self):
        result = train_baseline_model(
            examples=[],
            min_training_examples=10,
            min_positive_examples=2,
            min_negative_examples=2,
            min_accuracy=Decimal("0.55"),
            min_precision=Decimal("0.55"),
        )

        self.assertEqual(result["final_verdict"], "NO_GO_INSUFFICIENT_TRAINING_DATA")

    def test_train_baseline_registers_with_balanced_data(self):
        examples = []

        for index in range(5):
            examples.append({
                "eligible_for_training": 1,
                "label_go": 1,
                "label_profitable": 1,
                "simulated_net_return_pct": Decimal("0.20"),
                "features": {
                    "composite_score": "120",
                },
            })

        for index in range(5):
            examples.append({
                "eligible_for_training": 1,
                "label_go": 0,
                "label_profitable": 0,
                "simulated_net_return_pct": Decimal("-0.10"),
                "features": {
                    "composite_score": "40",
                },
            })

        result = train_baseline_model(
            examples=examples,
            min_training_examples=10,
            min_positive_examples=5,
            min_negative_examples=5,
            min_accuracy=Decimal("0.55"),
            min_precision=Decimal("0.55"),
        )

        self.assertEqual(result["final_verdict"], "MODEL_REGISTERED_RESEARCH_ONLY")
        self.assertEqual(result["approved_for_research"], 1)
        self.assertEqual(result["approved_for_live"], 0)

    def test_run_ai_learning_registry_without_paper_trades(self):
        self.seed_candidate(
            run_label="ranking_run",
            symbol="ETHUSDT",
            final_verdict="NO_GO_SCANNER_REJECTED",
            composite_score="50",
            annualized="8",
            net_edge="0",
            edge_ratio="1",
        )

        result = run_ai_learning_registry(
            db_path=self.db_path,
            ranking_run_label="ranking_run",
            paper_run_label="paper_run",
            run_label="learning_run",
            model_run_label="model_run",
            min_label_net_return_pct=Decimal("0.05"),
            min_training_examples=10,
            min_positive_examples=2,
            min_negative_examples=2,
            min_accuracy=Decimal("0.55"),
            min_precision=Decimal("0.55"),
        )

        self.assertEqual(result["examples_created"], 1)
        self.assertEqual(result["eligible_training_examples"], 0)
        self.assertEqual(result["global_verdict"], "NO_GO_INSUFFICIENT_TRAINING_DATA")

    def test_run_ai_learning_registry_with_seeded_trades(self):
        for index in range(5):
            candidate_id = self.seed_candidate(
                run_label="ranking_run",
                symbol=f"WIN{index}USDT",
                final_verdict="GO_FOR_RESEARCH_RANKED",
                composite_score="120",
                annualized="30",
                net_edge="0.20",
                edge_ratio="3",
            )

            self.seed_paper_trade(
                paper_run_label="paper_run",
                candidate_result_id=candidate_id,
                symbol=f"WIN{index}USDT",
                net_return_pct="0.20",
                net_pnl_usd="2",
            )

        for index in range(5):
            candidate_id = self.seed_candidate(
                run_label="ranking_run",
                symbol=f"LOSS{index}USDT",
                final_verdict="GO_FOR_RESEARCH_RANKED",
                composite_score="40",
                annualized="5",
                net_edge="-0.05",
                edge_ratio="0.5",
            )

            self.seed_paper_trade(
                paper_run_label="paper_run",
                candidate_result_id=candidate_id,
                symbol=f"LOSS{index}USDT",
                net_return_pct="-0.10",
                net_pnl_usd="-1",
            )

        result = run_ai_learning_registry(
            db_path=self.db_path,
            ranking_run_label="ranking_run",
            paper_run_label="paper_run",
            run_label="learning_run",
            model_run_label="model_run",
            min_label_net_return_pct=Decimal("0.05"),
            min_training_examples=10,
            min_positive_examples=5,
            min_negative_examples=5,
            min_accuracy=Decimal("0.55"),
            min_precision=Decimal("0.55"),
        )

        self.assertEqual(result["examples_created"], 10)
        self.assertEqual(result["eligible_training_examples"], 10)
        self.assertEqual(result["positive_labels"], 5)
        self.assertEqual(result["negative_labels"], 5)
        self.assertEqual(result["global_verdict"], "MODEL_REGISTERED_RESEARCH_ONLY")

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        example_count = cur.execute("""
        SELECT COUNT(*)
        FROM ai_learning_examples
        WHERE run_label = 'learning_run'
        """).fetchone()[0]

        model_count = cur.execute("""
        SELECT COUNT(*)
        FROM ai_model_registry
        WHERE run_label = 'model_run'
        """).fetchone()[0]

        conn.close()

        self.assertEqual(example_count, 10)
        self.assertEqual(model_count, 1)


if __name__ == "__main__":
    unittest.main()
