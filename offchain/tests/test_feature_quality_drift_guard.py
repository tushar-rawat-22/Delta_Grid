import sqlite3

from offchain.ai_quality.feature_quality_drift_guard import (
    DECISION_BLOCK_SAFETY,
    DECISION_READY,
    DECISION_REJECT_MISSING,
    DECISION_UNSTABLE,
    DRIFT_BASELINE_UNAVAILABLE,
    DRIFT_BREACHED,
    VERDICT_BLOCKED,
    VERDICT_MISSING,
    VERDICT_READY,
    VERDICT_UNSTABLE,
    parse_labels,
    run_ai_feature_quality_drift_guard,
)


def create_ai_learning_tables(conn):
    conn.execute(
        """
        CREATE TABLE ai_paper_outcome_learning_runs (
            learning_run_label TEXT PRIMARY KEY,
            report_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_multi_cycle_track_label TEXT NOT NULL,
            source_session_label TEXT,
            source_portfolio_label TEXT,
            cycle_count INTEGER NOT NULL,
            feature_count INTEGER NOT NULL,
            label_count INTEGER NOT NULL,
            recommendation_count INTEGER NOT NULL,
            paper_notional TEXT NOT NULL,
            cumulative_net_paper_pnl TEXT NOT NULL,
            cumulative_net_pnl_bps TEXT NOT NULL,
            average_cycle_net_pnl_bps TEXT NOT NULL,
            worst_cycle_net_pnl_bps TEXT NOT NULL,
            worst_position_loss_bps TEXT NOT NULL,
            average_fee_drag_bps TEXT NOT NULL,
            total_alert_count INTEGER NOT NULL,
            total_triggered_event_count INTEGER NOT NULL,
            safety_breach_count INTEGER NOT NULL,
            learning_score TEXT NOT NULL,
            outcome_label TEXT NOT NULL,
            data_sufficiency_label TEXT NOT NULL,
            risk_label TEXT NOT NULL,
            autonomy_label TEXT NOT NULL,
            model_mode TEXT NOT NULL,
            learning_decision TEXT NOT NULL,
            global_verdict TEXT NOT NULL,
            recommended_action TEXT NOT NULL,
            next_mission TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            markdown_report TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_paper_outcome_learning_features (
            feature_id TEXT PRIMARY KEY,
            learning_run_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_multi_cycle_track_label TEXT NOT NULL,
            feature_group TEXT NOT NULL,
            feature_name TEXT NOT NULL,
            feature_value TEXT NOT NULL,
            normalized_value TEXT NOT NULL,
            feature_weight TEXT NOT NULL,
            feature_direction TEXT NOT NULL,
            feature_reason TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_paper_outcome_learning_labels (
            label_id TEXT PRIMARY KEY,
            learning_run_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_multi_cycle_track_label TEXT NOT NULL,
            label_group TEXT NOT NULL,
            label_name TEXT NOT NULL,
            label_value TEXT NOT NULL,
            label_confidence TEXT NOT NULL,
            label_reason TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_paper_outcome_learning_recommendations (
            recommendation_id TEXT PRIMARY KEY,
            learning_run_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_multi_cycle_track_label TEXT NOT NULL,
            recommendation_type TEXT NOT NULL,
            recommendation_status TEXT NOT NULL,
            recommendation_priority INTEGER NOT NULL,
            recommendation_text TEXT NOT NULL,
            expected_effect TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def insert_learning_run(
    conn,
    label="learning-1",
    created_at="2026-01-01T00:00:00+00:00",
    source_track="track-1",
    feature_count=12,
    label_count=4,
    recommendation_count=3,
    learning_score="84.8641975",
    data_label="AI_DATA_SUFFICIENCY_LABEL_EARLY_NEEDS_MORE_CYCLES",
    risk_label="AI_RISK_LABEL_NO_ALERTS_NO_TRIGGERED_EVENTS",
    autonomy_label="AI_AUTONOMY_LABEL_RECOMMENDATION_ONLY_NO_TRADING",
    model_mode="DETERMINISTIC_LOCAL_RULE_BASED_RECOMMENDATION_ONLY",
    decision="AI_PAPER_OUTCOME_LEARNING_READY_FOR_DATASET_EXPANSION",
    verdict="AI_PAPER_OUTCOME_LEARNING_READY_SHADOW_ONLY",
    safety_breach_count=0,
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO ai_paper_outcome_learning_runs (
            learning_run_label,
            report_label,
            created_at,
            source_multi_cycle_track_label,
            source_session_label,
            source_portfolio_label,
            cycle_count,
            feature_count,
            label_count,
            recommendation_count,
            paper_notional,
            cumulative_net_paper_pnl,
            cumulative_net_pnl_bps,
            average_cycle_net_pnl_bps,
            worst_cycle_net_pnl_bps,
            worst_position_loss_bps,
            average_fee_drag_bps,
            total_alert_count,
            total_triggered_event_count,
            safety_breach_count,
            learning_score,
            outcome_label,
            data_sufficiency_label,
            risk_label,
            autonomy_label,
            model_mode,
            learning_decision,
            global_verdict,
            recommended_action,
            next_mission,
            live_trading,
            live_order_sent,
            capital_deployment,
            summary_json,
            markdown_report
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            label,
            f"{label}-report",
            created_at,
            source_track,
            "session-1",
            "portfolio-1",
            1,
            feature_count,
            label_count,
            recommendation_count,
            "100000",
            "-20",
            "-2",
            "-2",
            "-2",
            "-2",
            "2",
            0,
            0,
            safety_breach_count,
            learning_score,
            "AI_PAPER_OUTCOME_LABEL_EARLY_STABLE_NEEDS_MORE_CYCLES",
            data_label,
            risk_label,
            autonomy_label,
            model_mode,
            decision,
            verdict,
            "CONTINUE_PAPER_DATASET_EXPANSION_NO_AUTONOMOUS_TRADING",
            "Mission 71 AI Feature Quality and Drift Guard",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
            "# report",
        ),
    )


FEATURES = [
    ("data", "cycle_count", "1", "0.33333333", "0.10", "HIGHER_IS_BETTER"),
    ("quality", "pass_check_ratio", "1.0", "1.0", "0.12", "HIGHER_IS_BETTER"),
    ("performance", "cumulative_net_pnl_bps", "-2.0", "0.96", "0.12", "HIGHER_IS_BETTER"),
    ("performance", "average_cycle_net_pnl_bps", "-2.0", "0.8", "0.10", "HIGHER_IS_BETTER"),
    ("risk", "worst_cycle_net_pnl_bps", "-2.0", "0.8", "0.10", "HIGHER_IS_BETTER"),
    ("risk", "worst_position_loss_bps", "-2.0", "0.8", "0.10", "HIGHER_IS_BETTER"),
    ("cost", "average_fee_drag_bps", "2.0", "0.6", "0.08", "LOWER_IS_BETTER"),
    ("alerts", "total_alert_count", "0", "1.0", "0.08", "LOWER_IS_BETTER"),
    ("events", "total_triggered_event_count", "0", "1.0", "0.08", "LOWER_IS_BETTER"),
    ("safety", "safety_breach_count", "0", "1.0", "0.08", "LOWER_IS_BETTER"),
    ("state", "multi_cycle_state_confirmed", "MULTI_CYCLE_STATE_CONFIRMED", "1.0", "0.06", "BINARY_CONFIRMED_IS_BETTER"),
    ("state", "multi_cycle_verdict_ready", "MULTI_CYCLE_OBSERVATION_TRACK_READY_SHADOW_ONLY", "1.0", "0.06", "BINARY_READY_IS_BETTER"),
]


def insert_feature(
    conn,
    run_label="learning-1",
    group="data",
    name="cycle_count",
    value="1",
    normalized="0.33333333",
    weight="0.10",
    direction="HIGHER_IS_BETTER",
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO ai_paper_outcome_learning_features (
            feature_id,
            learning_run_label,
            created_at,
            source_multi_cycle_track_label,
            feature_group,
            feature_name,
            feature_value,
            normalized_value,
            feature_weight,
            feature_direction,
            feature_reason,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{run_label}-{group}-{name}",
            run_label,
            "2026-01-01T00:00:00+00:00",
            "track-1",
            group,
            name,
            value,
            normalized,
            weight,
            direction,
            "test",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
        ),
    )


def insert_good_features(conn, run_label="learning-1"):
    for group, name, value, normalized, weight, direction in FEATURES:
        insert_feature(
            conn,
            run_label=run_label,
            group=group,
            name=name,
            value=value,
            normalized=normalized,
            weight=weight,
            direction=direction,
        )


def insert_label(
    conn,
    run_label="learning-1",
    label_group="autonomy",
    label_name="autonomy_scope_label",
    value="AI_AUTONOMY_LABEL_RECOMMENDATION_ONLY_NO_TRADING",
):
    conn.execute(
        """
        INSERT INTO ai_paper_outcome_learning_labels (
            label_id,
            learning_run_label,
            created_at,
            source_multi_cycle_track_label,
            label_group,
            label_name,
            label_value,
            label_confidence,
            label_reason,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{run_label}-{label_group}-{label_name}",
            run_label,
            "2026-01-01T00:00:00+00:00",
            "track-1",
            label_group,
            label_name,
            value,
            "1.0",
            "test",
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
        ),
    )


def insert_good_labels(conn, run_label="learning-1"):
    insert_label(conn, run_label, "outcome", "paper_outcome_label", "AI_PAPER_OUTCOME_LABEL_EARLY_STABLE_NEEDS_MORE_CYCLES")
    insert_label(conn, run_label, "data", "data_sufficiency_label", "AI_DATA_SUFFICIENCY_LABEL_EARLY_NEEDS_MORE_CYCLES")
    insert_label(conn, run_label, "risk", "risk_cleanliness_label", "AI_RISK_LABEL_NO_ALERTS_NO_TRIGGERED_EVENTS")
    insert_label(conn, run_label, "autonomy", "autonomy_scope_label", "AI_AUTONOMY_LABEL_RECOMMENDATION_ONLY_NO_TRADING")


def insert_recommendation(conn, run_label="learning-1", rec_type="collect_more_paper_cycles"):
    conn.execute(
        """
        INSERT INTO ai_paper_outcome_learning_recommendations (
            recommendation_id,
            learning_run_label,
            created_at,
            source_multi_cycle_track_label,
            recommendation_type,
            recommendation_status,
            recommendation_priority,
            recommendation_text,
            expected_effect,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{run_label}-{rec_type}",
            run_label,
            "2026-01-01T00:00:00+00:00",
            "track-1",
            rec_type,
            "RECOMMENDATION_ACTIVE",
            1,
            "test",
            "test",
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
        ),
    )


def insert_good_recommendations(conn, run_label="learning-1"):
    insert_recommendation(conn, run_label, "collect_more_paper_cycles")
    insert_recommendation(conn, run_label, "keep_autonomous_trading_disabled")
    insert_recommendation(conn, run_label, "defer_strategy_weight_changes")


def seed_good(conn, include_baseline=False):
    create_ai_learning_tables(conn)

    if include_baseline:
        insert_learning_run(conn, label="baseline-learning", created_at="2026-01-01T00:00:00+00:00")
        insert_good_features(conn, "baseline-learning")
        insert_good_labels(conn, "baseline-learning")
        insert_good_recommendations(conn, "baseline-learning")

    insert_learning_run(conn, created_at="2026-01-02T00:00:00+00:00")
    insert_good_features(conn)
    insert_good_labels(conn)
    insert_good_recommendations(conn)


def test_parse_labels_deduplicates():
    assert parse_labels("learning-1,learning-2,learning-1") == ["learning-1", "learning-2"]


def test_guard_approves_good_learning_run_without_baseline_and_persists(tmp_path):
    db_path = tmp_path / "mission71.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_feature_quality_drift_guard(
        db_path=db_path,
        review_label="guard-1",
        report_label="guard-report-1",
        learning_run_label="learning-1",
    )

    assert result["guard_decision"] == DECISION_READY
    assert result["global_verdict"] == VERDICT_READY
    assert result["feature_count"] == 12
    assert result["label_count"] == 4
    assert result["recommendation_count"] == 3
    assert result["quality_check_count"] == 16
    assert result["pass_check_count"] == 16
    assert result["fail_check_count"] == 0
    assert result["drift_status"] == DRIFT_BASELINE_UNAVAILABLE
    assert result["safety_breach_count"] == 0

    with sqlite3.connect(db_path) as conn:
        review = conn.execute(
            """
            SELECT review_label, guard_decision, global_verdict
            FROM ai_feature_quality_drift_guard_reviews
            WHERE review_label = ?
            """,
            ("guard-1",),
        ).fetchone()

    assert review == ("guard-1", DECISION_READY, VERDICT_READY)


def test_guard_approves_good_learning_run_with_baseline(tmp_path):
    db_path = tmp_path / "mission71-baseline.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn, include_baseline=True)
        conn.commit()

    result = run_ai_feature_quality_drift_guard(
        db_path=db_path,
        review_label="baseline-guard",
        report_label="baseline-report",
        learning_run_label="learning-1",
    )

    assert result["guard_decision"] == DECISION_READY
    assert result["global_verdict"] == VERDICT_READY
    assert result["baseline_learning_run_label"] == "baseline-learning"
    assert result["drift_check_count"] == 12
    assert result["max_feature_drift"] == 0


def test_guard_rejects_missing_learning_run(tmp_path):
    db_path = tmp_path / "mission71-missing.db"

    result = run_ai_feature_quality_drift_guard(
        db_path=db_path,
        review_label="missing-guard",
        report_label="missing-report",
        learning_run_label="missing-learning",
    )

    assert result["guard_decision"] == DECISION_REJECT_MISSING
    assert result["global_verdict"] == VERDICT_MISSING
    assert result["fail_check_count"] == 1


def test_guard_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "mission71-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_ai_learning_tables(conn)
        insert_learning_run(conn, safety_breach_count=1, live_trading="ENABLED")
        insert_good_features(conn)
        insert_good_labels(conn)
        insert_good_recommendations(conn)
        conn.commit()

    result = run_ai_feature_quality_drift_guard(
        db_path=db_path,
        review_label="safety-guard",
        report_label="safety-report",
        learning_run_label="learning-1",
    )

    assert result["guard_decision"] == DECISION_BLOCK_SAFETY
    assert result["global_verdict"] == VERDICT_BLOCKED
    assert result["safety_breach_count"] >= 1


def test_guard_flags_invalid_normalized_feature(tmp_path):
    db_path = tmp_path / "mission71-invalid-normalized.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.execute(
            """
            UPDATE ai_paper_outcome_learning_features
            SET normalized_value = ?
            WHERE learning_run_label = ?
            AND feature_group = ?
            AND feature_name = ?
            """,
            ("1.5", "learning-1", "data", "cycle_count"),
        )
        conn.commit()

    result = run_ai_feature_quality_drift_guard(
        db_path=db_path,
        review_label="invalid-normalized-guard",
        report_label="invalid-normalized-report",
        learning_run_label="learning-1",
    )

    assert result["guard_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["invalid_normalized_feature_count"] == 1


def test_guard_flags_missing_required_feature_group(tmp_path):
    db_path = tmp_path / "mission71-missing-group.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.execute(
            """
            DELETE FROM ai_paper_outcome_learning_features
            WHERE learning_run_label = ?
            AND feature_group = ?
            """,
            ("learning-1", "events"),
        )
        conn.commit()

    result = run_ai_feature_quality_drift_guard(
        db_path=db_path,
        review_label="missing-group-guard",
        report_label="missing-group-report",
        learning_run_label="learning-1",
    )

    assert result["guard_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["missing_required_group_count"] == 1


def test_guard_flags_high_feature_drift(tmp_path):
    db_path = tmp_path / "mission71-drift.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn, include_baseline=True)
        conn.execute(
            """
            UPDATE ai_paper_outcome_learning_features
            SET normalized_value = ?
            WHERE learning_run_label = ?
            AND feature_group = ?
            AND feature_name = ?
            """,
            ("0.1", "learning-1", "performance", "cumulative_net_pnl_bps"),
        )
        conn.commit()

    result = run_ai_feature_quality_drift_guard(
        db_path=db_path,
        review_label="drift-guard",
        report_label="drift-report",
        learning_run_label="learning-1",
        max_allowed_feature_drift=0.1,
    )

    assert result["guard_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["drift_status"] == DRIFT_BREACHED
    assert result["max_feature_drift"] > 0.1


def test_markdown_report_contains_no_autonomous_trading_scope(tmp_path):
    db_path = tmp_path / "mission71-markdown.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_feature_quality_drift_guard(
        db_path=db_path,
        review_label="markdown-guard",
        report_label="markdown-report",
        learning_run_label="learning-1",
    )

    assert "# DeltaGrid Mission 71" in result["markdown_report"]
    assert "does not perform autonomous trading" in result["markdown_report"]
    assert "does not adjust strategy weights automatically" in result["markdown_report"]
    assert "No exchange orders were sent." in result["markdown_report"]
