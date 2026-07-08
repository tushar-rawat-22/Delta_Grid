import json
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from db.schema import init_market_database, utc_now

from backtest.funding_basis_model import ensure_schema as ensure_funding_basis_schema
from backtest.multi_symbol_funding_scanner import ensure_schema as ensure_multi_symbol_scan_schema
from backtest.candidate_ranking_engine import ensure_schema as ensure_candidate_ranking_schema
from backtest.paper_trading_engine import ensure_schema as ensure_paper_trading_schema
from backtest.ai_learning_registry import ensure_schema as ensure_ai_learning_schema

from backtest.research_dashboard_alerts import (
    build_snapshot,
    determine_overall_verdict,
    ensure_schema,
    generate_alerts,
    render_report_markdown,
    run_research_dashboard_alerts,
)


class ResearchDashboardAlertsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "research_dashboard_test.db")
        self.report_path = str(Path(self.tmp.name) / "report.md")

        init_market_database(self.db_path)
        ensure_funding_basis_schema(self.db_path)
        ensure_multi_symbol_scan_schema(self.db_path)
        ensure_candidate_ranking_schema(self.db_path)
        ensure_paper_trading_schema(self.db_path)
        ensure_ai_learning_schema(self.db_path)
        ensure_schema(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def seed_pipeline(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO multi_symbol_funding_scan_summary (
            run_label,
            exchange,
            symbols_requested,
            symbols_scanned,
            results_created,
            go_count,
            no_go_count,
            best_result_id,
            best_symbol,
            best_scanner_score,
            global_verdict,
            recommended_action,
            assumptions_json,
            created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "scanner_run",
            "Binance Futures",
            2,
            2,
            2,
            0,
            2,
            1,
            "ETHUSDT",
            "100",
            "NO_MULTI_SYMBOL_FUNDING_CANDIDATES_NO_LIVE_TRADING",
            "KEEP_SCANNING_AND_WAIT_FOR_EDGE",
            json.dumps({"test": True}),
            utc_now(),
        ))

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
            "scanner_run",
            "Binance Futures",
            "ETHUSDT",
            "0.00007",
            "8",
            "1700",
            "1700",
            "0",
            "1",
            "1000000000",
            "1000",
            "1700000",
            "0.08",
            "0.0755",
            "0.0045",
            "1.05",
            "80",
            "16",
            "0",
            "100",
            "NO_GO_LOW_FUNDING",
            "IGNORE_UNTIL_FUNDING_EXPANDS",
            json.dumps({"test": True}),
            utc_now(),
        ))

        cur.execute("""
        INSERT INTO candidate_ranking_summary (
            run_label,
            source_scan_run_label,
            candidates_seen,
            ranked_count,
            go_count,
            no_go_count,
            best_result_id,
            best_symbol,
            best_composite_score,
            global_verdict,
            recommended_action,
            assumptions_json,
            created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "ranking_run",
            "scanner_run",
            2,
            2,
            0,
            2,
            1,
            "ETHUSDT",
            "50",
            "NO_RANKED_CANDIDATES_NO_LIVE_TRADING",
            "KEEP_SCANNING_AND_WAIT_FOR_STRONGER_EDGE",
            json.dumps({"test": True}),
            utc_now(),
        ))

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
            "ranking_run",
            "scanner_run",
            "ETHUSDT",
            "NO_GO_LOW_FUNDING",
            "IGNORE_UNTIL_FUNDING_EXPANDS",
            "8",
            "0.0045",
            "1.05",
            "80",
            "16",
            "0",
            "100",
            "NO_GO_WALK_FORWARD_STABILITY",
            "-64",
            "LIQUIDATION_LEVERAGE_RISK_ACCEPTABLE_NO_LIVE_TRADING",
            "3.5",
            "REJECT_ALL_EXECUTION_COST_SCENARIOS_NO_LIVE_TRADING",
            "0.0755",
            "-0.04",
            json.dumps(["NO_GO_LOW_FUNDING", "EDGE_TO_COST_RATIO_TOO_LOW"]),
            "50",
            "NO_GO_SCANNER_REJECTED",
            "WAIT_FOR_SCANNER_GO_SIGNAL",
            json.dumps({"test": True}),
            utc_now(),
        ))

        cur.execute("""
        INSERT INTO paper_trading_summary (
            run_label,
            source_ranking_run_label,
            candidates_seen,
            eligible_candidates,
            positions_created,
            trades_created,
            starting_equity_usd,
            ending_equity_usd,
            total_pnl_usd,
            total_return_pct,
            max_drawdown_pct,
            win_rate_pct,
            avg_trade_return_pct,
            profit_factor,
            final_verdict,
            recommended_action,
            assumptions_json,
            created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "paper_run",
            "ranking_run",
            2,
            0,
            0,
            0,
            "10000",
            "10000",
            "0",
            "0",
            "0",
            "0",
            "0",
            "0",
            "NO_GO_NO_ELIGIBLE_PAPER_CANDIDATES",
            "KEEP_SCANNING_AND_WAIT_FOR_RANKED_CANDIDATES",
            json.dumps({"test": True}),
            utc_now(),
        ))

        cur.execute("""
        INSERT INTO ai_model_registry (
            run_label,
            source_learning_run_label,
            model_name,
            model_version,
            model_type,
            training_examples,
            eligible_training_examples,
            positive_labels,
            negative_labels,
            feature_names_json,
            metrics_json,
            model_params_json,
            approval_status,
            approved_for_research,
            approved_for_paper,
            approved_for_live,
            final_verdict,
            recommended_action,
            assumptions_json,
            created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "model_run",
            "learning_run",
            "baseline",
            "v1",
            "RULE_BASED",
            18,
            0,
            0,
            0,
            json.dumps(["composite_score"]),
            json.dumps({"accuracy": "0"}),
            json.dumps({}),
            "REJECTED",
            0,
            0,
            0,
            "NO_GO_INSUFFICIENT_TRAINING_DATA",
            "COLLECT_MORE_PAPER_TRADES",
            json.dumps({"test": True}),
            utc_now(),
        ))

        conn.commit()
        conn.close()

    def test_determine_overall_verdict_missing_scanner(self):
        scanner = {"found": False}
        ranking = {"found": False}
        paper = {"found": False}
        ai_model = {"found": False}

        result = determine_overall_verdict(
            scanner=scanner,
            ranking=ranking,
            paper=paper,
            ai_model=ai_model,
        )

        self.assertEqual(result, "NO_GO_DASHBOARD_MISSING_SCANNER")

    def test_generate_alerts_blocks_live_trading(self):
        scanner = {
            "found": True,
            "go_count": 0,
            "best_symbol": "ETHUSDT",
            "recommended_action": "SCAN",
        }

        ranking = {
            "found": True,
            "go_count": 0,
            "best_symbol": "ETHUSDT",
            "recommended_action": "RANK",
        }

        paper = {
            "final_verdict": "NO_GO_NO_ELIGIBLE_PAPER_CANDIDATES",
            "eligible_candidates": 0,
            "recommended_action": "WAIT",
        }

        ai_model = {
            "approval_status": "REJECTED",
            "recommended_action": "COLLECT_MORE_DATA",
        }

        alerts = generate_alerts(
            scanner=scanner,
            ranking=ranking,
            paper=paper,
            ai_model=ai_model,
            top_ranking=[],
        )

        alert_types = [
            alert["alert_type"]
            for alert in alerts
        ]

        self.assertIn("LIVE_TRADING_DISABLED", alert_types)

    def test_build_snapshot_counts_alerts(self):
        scanner = {
            "global_verdict": "NO_GO",
            "go_count": 0,
            "no_go_count": 2,
            "best_symbol": "ETHUSDT",
        }

        ranking = {
            "global_verdict": "NO_GO",
            "go_count": 0,
            "no_go_count": 2,
            "best_symbol": "ETHUSDT",
        }

        paper = {
            "final_verdict": "NO_GO",
            "eligible_candidates": 0,
            "trades_created": 0,
            "total_return_pct": Decimal("0"),
            "max_drawdown_pct": Decimal("0"),
        }

        ai_model = {
            "final_verdict": "NO_GO",
            "approval_status": "REJECTED",
            "eligible_training_examples": 0,
            "positive_labels": 0,
            "negative_labels": 0,
        }

        alerts = [
            {"is_blocking": 1},
            {"is_blocking": 0},
        ]

        snapshot = build_snapshot(
            scanner=scanner,
            ranking=ranking,
            paper=paper,
            ai_model=ai_model,
            alerts=alerts,
            overall_verdict="NO_GO",
            action="WAIT",
        )

        self.assertEqual(snapshot["alert_count"], 2)
        self.assertEqual(snapshot["blocking_alert_count"], 1)

    def test_render_report_contains_sections(self):
        scanner = {
            "global_verdict": "NO_GO",
            "go_count": 0,
            "no_go_count": 1,
            "best_symbol": "ETHUSDT",
        }

        ranking = {
            "global_verdict": "NO_GO",
            "go_count": 0,
            "no_go_count": 1,
            "best_symbol": "ETHUSDT",
        }

        paper = {
            "final_verdict": "NO_GO",
            "eligible_candidates": 0,
            "trades_created": 0,
            "total_return_pct": Decimal("0"),
            "max_drawdown_pct": Decimal("0"),
        }

        ai_model = {
            "final_verdict": "NO_GO",
            "approval_status": "REJECTED",
            "eligible_training_examples": 0,
            "positive_labels": 0,
            "negative_labels": 0,
            "approved_for_live": 0,
        }

        snapshot = {
            "overall_system_verdict": "NO_GO",
            "recommended_action": "WAIT",
            "alert_count": 1,
            "blocking_alert_count": 1,
        }

        report = render_report_markdown(
            run_label="dashboard_run",
            scanner_run_label="scanner",
            ranking_run_label="ranking",
            paper_run_label="paper",
            ai_learning_run_label="learning",
            ai_model_run_label="model",
            snapshot=snapshot,
            scanner=scanner,
            ranking=ranking,
            paper=paper,
            ai_model=ai_model,
            top_scanner=[],
            top_ranking=[],
            alerts=[
                {
                    "alert_level": "CRITICAL",
                    "alert_type": "LIVE_TRADING_DISABLED",
                    "source_component": "safety",
                    "is_blocking": 1,
                    "message": "No live trading.",
                }
            ],
        )

        self.assertIn("DeltaGrid Research Dashboard Report", report)
        self.assertIn("## Alerts", report)
        self.assertIn("No live trading", report)

    def test_run_dashboard_with_seeded_pipeline_inserts_rows(self):
        self.seed_pipeline()

        result = run_research_dashboard_alerts(
            db_path=self.db_path,
            run_label="dashboard_run",
            scanner_run_label="scanner_run",
            ranking_run_label="ranking_run",
            paper_run_label="paper_run",
            ai_learning_run_label="learning_run",
            ai_model_run_label="model_run",
            report_path=self.report_path,
        )

        self.assertEqual(result["overall_system_verdict"], "RESEARCH_PIPELINE_NO_GO_WAIT_FOR_EDGE_NO_LIVE_TRADING")
        self.assertTrue(Path(self.report_path).exists())
        self.assertTrue(result["alert_count"] >= 1)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        snapshot_count = cur.execute("""
        SELECT COUNT(*)
        FROM research_dashboard_snapshots
        WHERE run_label = 'dashboard_run'
        """).fetchone()[0]

        alert_count = cur.execute("""
        SELECT COUNT(*)
        FROM research_dashboard_alerts
        WHERE run_label = 'dashboard_run'
        """).fetchone()[0]

        report_count = cur.execute("""
        SELECT COUNT(*)
        FROM research_daily_reports
        WHERE run_label = 'dashboard_run'
        """).fetchone()[0]

        conn.close()

        self.assertEqual(snapshot_count, 1)
        self.assertEqual(report_count, 1)
        self.assertEqual(alert_count, result["alert_count"])

    def test_run_dashboard_without_sources_still_reports_missing(self):
        result = run_research_dashboard_alerts(
            db_path=self.db_path,
            run_label="dashboard_missing",
            scanner_run_label="missing_scanner",
            ranking_run_label="missing_ranking",
            paper_run_label="missing_paper",
            ai_learning_run_label="missing_learning",
            ai_model_run_label="missing_model",
            report_path=self.report_path,
        )

        self.assertEqual(result["overall_system_verdict"], "NO_GO_DASHBOARD_MISSING_SCANNER")
        self.assertTrue(result["blocking_alert_count"] >= 1)

    def test_dashboard_report_file_is_written(self):
        self.seed_pipeline()

        result = run_research_dashboard_alerts(
            db_path=self.db_path,
            run_label="dashboard_report",
            scanner_run_label="scanner_run",
            ranking_run_label="ranking_run",
            paper_run_label="paper_run",
            ai_learning_run_label="learning_run",
            ai_model_run_label="model_run",
            report_path=self.report_path,
        )

        text = Path(result["report_path"]).read_text()

        self.assertIn("Research Dashboard", text)
        self.assertIn("LIVE_TRADING_DISABLED", text)


if __name__ == "__main__":
    unittest.main()
