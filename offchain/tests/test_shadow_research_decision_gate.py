import sqlite3

from offchain.backtest.shadow_candidate_replay_harness import run_shadow_candidate_replay
from offchain.backtest.shadow_replay_performance_reporter import generate_shadow_replay_performance_report
from offchain.backtest.shadow_research_decision_gate import (
    APPROVE_SHADOW_ONLY_DECISION,
    NO_PERFORMANCE_HISTORY_DECISION,
    REJECT_WEAK_REPLAY_DECISION,
    REQUIRE_MORE_SAMPLES_DECISION,
    run_shadow_research_decision_gate,
)


def test_missing_database_blocks_and_requests_performance_history(tmp_path):
    db_path = tmp_path / "missing.db"

    result = run_shadow_research_decision_gate(
        db_path=db_path,
        gate_label="mission37-missing-db",
    )

    assert result["database_exists"] is False
    assert result["gate_decision"] == NO_PERFORMANCE_HISTORY_DECISION
    assert result["live_trading_decision"] == "BLOCKED"
    assert result["capital_deployment_decision"] == "BLOCKED"
    assert result["approved_next_stage"] == "RUN_MISSION_36_PERFORMANCE_REPORTER"


def test_decision_gate_approves_shadow_observation_only_for_valid_report(tmp_path):
    db_path = tmp_path / "mission37-approved.db"

    run_shadow_candidate_replay(
        db_path=db_path,
        replay_label="mission37-replay",
        scenario_names=["all"],
    )

    generate_shadow_replay_performance_report(
        db_path=db_path,
        report_label="mission37-performance",
        replay_label="mission37-replay",
    )

    result = run_shadow_research_decision_gate(
        db_path=db_path,
        gate_label="mission37-gate",
        report_label="mission37-performance",
    )

    assert result["gate_label"] == "mission37-gate"
    assert result["source_report_label"] == "mission37-performance"
    assert result["gate_decision"] == APPROVE_SHADOW_ONLY_DECISION
    assert result["approved_next_stage"] == "SHADOW_PAPER_OBSERVATION_ONLY"
    assert result["live_trading_decision"] == "BLOCKED"
    assert result["capital_deployment_decision"] == "BLOCKED"
    assert result["metrics"]["candidate_count"] == 8
    assert result["metrics"]["total_approved_count"] == 2
    assert result["metrics"]["total_rejected_count"] == 6
    assert result["metrics"]["approval_rate"] == 0.25
    assert result["metrics"]["live_trading_breach_count"] == 0

    with sqlite3.connect(db_path) as conn:
        stored = conn.execute(
            """
            SELECT
                gate_label,
                source_report_label,
                gate_decision,
                live_trading_decision,
                capital_deployment_decision,
                approved_next_stage
            FROM shadow_research_decision_gate_reports
            WHERE gate_label = ?
            """,
            ("mission37-gate",),
        ).fetchone()

    assert stored == (
        "mission37-gate",
        "mission37-performance",
        APPROVE_SHADOW_ONLY_DECISION,
        "BLOCKED",
        "BLOCKED",
        "SHADOW_PAPER_OBSERVATION_ONLY",
    )


def test_decision_gate_requires_more_samples_for_small_report(tmp_path):
    db_path = tmp_path / "mission37-small.db"

    run_shadow_candidate_replay(
        db_path=db_path,
        replay_label="mission37-small-replay",
        scenario_names=["approved_shadow_btc"],
    )

    generate_shadow_replay_performance_report(
        db_path=db_path,
        report_label="mission37-small-performance",
        replay_label="mission37-small-replay",
    )

    result = run_shadow_research_decision_gate(
        db_path=db_path,
        gate_label="mission37-small-gate",
        report_label="mission37-small-performance",
    )

    assert result["gate_decision"] == REQUIRE_MORE_SAMPLES_DECISION
    assert result["approved_next_stage"] == "COLLECT_MORE_SHADOW_REPLAY_SAMPLES"
    assert result["live_trading_decision"] == "BLOCKED"
    assert result["capital_deployment_decision"] == "BLOCKED"


def test_decision_gate_rejects_no_approval_report_when_minimums_are_relaxed(tmp_path):
    db_path = tmp_path / "mission37-weak.db"

    run_shadow_candidate_replay(
        db_path=db_path,
        replay_label="mission37-weak-replay",
        scenario_names=["non_universe_rejection"],
    )

    generate_shadow_replay_performance_report(
        db_path=db_path,
        report_label="mission37-weak-performance",
        replay_label="mission37-weak-replay",
    )

    result = run_shadow_research_decision_gate(
        db_path=db_path,
        gate_label="mission37-weak-gate",
        report_label="mission37-weak-performance",
        min_scenario_count=1,
        min_pipeline_run_count=1,
        min_candidate_count=1,
    )

    assert result["gate_decision"] == REJECT_WEAK_REPLAY_DECISION
    assert result["approved_next_stage"] == "CONTINUE_SHADOW_RESEARCH_NO_APPROVAL"
    assert result["metrics"]["total_approved_count"] == 0
    assert result["metrics"]["total_rejected_count"] == 1
    assert result["live_trading_decision"] == "BLOCKED"
    assert result["capital_deployment_decision"] == "BLOCKED"
