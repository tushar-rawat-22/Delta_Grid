import sqlite3

from offchain.ai_dataset.paper_dataset_expansion_scheduler import (
    DECISION_BLOCK_SAFETY,
    DECISION_READY,
    DECISION_REJECT_MISSING,
    DECISION_UNSTABLE,
    VERDICT_BLOCKED,
    VERDICT_MISSING,
    VERDICT_READY,
    VERDICT_UNSTABLE,
    parse_labels,
    parse_symbols,
    run_ai_paper_dataset_expansion_scheduler,
)


def create_guard_tables(conn):
    conn.execute(
        """
        CREATE TABLE ai_feature_quality_drift_guard_reviews (
            review_label TEXT PRIMARY KEY,
            report_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_learning_run_label TEXT NOT NULL,
            baseline_learning_run_label TEXT,
            source_multi_cycle_track_label TEXT,
            source_session_label TEXT,
            source_portfolio_label TEXT,
            cycle_count INTEGER NOT NULL,
            feature_count INTEGER NOT NULL,
            label_count INTEGER NOT NULL,
            recommendation_count INTEGER NOT NULL,
            required_feature_group_count INTEGER NOT NULL,
            observed_feature_group_count INTEGER NOT NULL,
            missing_required_group_count INTEGER NOT NULL,
            invalid_normalized_feature_count INTEGER NOT NULL,
            invalid_feature_weight_count INTEGER NOT NULL,
            feature_weight_total TEXT NOT NULL,
            learning_score TEXT NOT NULL,
            max_feature_drift TEXT NOT NULL,
            average_feature_drift TEXT NOT NULL,
            drift_check_count INTEGER NOT NULL,
            quality_check_count INTEGER NOT NULL,
            pass_check_count INTEGER NOT NULL,
            fail_check_count INTEGER NOT NULL,
            safety_breach_count INTEGER NOT NULL,
            drift_status TEXT NOT NULL,
            quality_state TEXT NOT NULL,
            guard_decision TEXT NOT NULL,
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
        CREATE TABLE ai_feature_quality_drift_guard_checks (
            check_id TEXT PRIMARY KEY,
            review_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_learning_run_label TEXT NOT NULL,
            check_category TEXT NOT NULL,
            check_name TEXT NOT NULL,
            check_status TEXT NOT NULL,
            observed_value TEXT NOT NULL,
            threshold_value TEXT NOT NULL,
            check_reason TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_feature_quality_drift_guard_feature_drifts (
            drift_id TEXT PRIMARY KEY,
            review_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_learning_run_label TEXT NOT NULL,
            baseline_learning_run_label TEXT,
            feature_group TEXT NOT NULL,
            feature_name TEXT NOT NULL,
            current_normalized_value TEXT NOT NULL,
            baseline_normalized_value TEXT,
            absolute_drift TEXT NOT NULL,
            drift_status TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def insert_guard_review(
    conn,
    review_label="guard-1",
    cycle_count=1,
    learning_score="84.8641975",
    max_feature_drift="0",
    quality_check_count=16,
    pass_check_count=16,
    fail_check_count=0,
    safety_breach_count=0,
    drift_status="AI_FEATURE_DRIFT_WITHIN_LIMIT",
    quality_state="AI_FEATURE_QUALITY_STATE_READY",
    guard_decision="AI_FEATURE_QUALITY_DRIFT_GUARD_APPROVED_FOR_DATASET_EXPANSION",
    verdict="AI_FEATURE_QUALITY_DRIFT_GUARD_READY_SHADOW_ONLY",
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO ai_feature_quality_drift_guard_reviews (
            review_label,
            report_label,
            created_at,
            source_learning_run_label,
            baseline_learning_run_label,
            source_multi_cycle_track_label,
            source_session_label,
            source_portfolio_label,
            cycle_count,
            feature_count,
            label_count,
            recommendation_count,
            required_feature_group_count,
            observed_feature_group_count,
            missing_required_group_count,
            invalid_normalized_feature_count,
            invalid_feature_weight_count,
            feature_weight_total,
            learning_score,
            max_feature_drift,
            average_feature_drift,
            drift_check_count,
            quality_check_count,
            pass_check_count,
            fail_check_count,
            safety_breach_count,
            drift_status,
            quality_state,
            guard_decision,
            global_verdict,
            recommended_action,
            next_mission,
            live_trading,
            live_order_sent,
            capital_deployment,
            summary_json,
            markdown_report
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            review_label,
            f"{review_label}-report",
            "2026-01-01T00:00:00+00:00",
            "learning-1",
            "learning-baseline",
            "track-1",
            "session-1",
            "portfolio-1",
            cycle_count,
            12,
            4,
            3,
            9,
            9,
            0,
            0,
            0,
            "1.08",
            learning_score,
            max_feature_drift,
            "0",
            12,
            quality_check_count,
            pass_check_count,
            fail_check_count,
            safety_breach_count,
            drift_status,
            quality_state,
            guard_decision,
            verdict,
            "CONTINUE_AI_DATASET_EXPANSION_WITH_DRIFT_MONITORING",
            "Mission 72 AI Paper Dataset Expansion Scheduler",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
            "# report",
        ),
    )


def insert_guard_check(conn, check_id="check-1", review_label="guard-1"):
    conn.execute(
        """
        INSERT INTO ai_feature_quality_drift_guard_checks (
            check_id,
            review_label,
            created_at,
            source_learning_run_label,
            check_category,
            check_name,
            check_status,
            observed_value,
            threshold_value,
            check_reason,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            check_id,
            review_label,
            "2026-01-01T00:00:00+00:00",
            "learning-1",
            "safety",
            "safety breach count",
            "AI_FEATURE_QUALITY_CHECK_PASS",
            "0",
            "0",
            "test",
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
        ),
    )


def insert_guard_drift(conn, drift_id="drift-1", review_label="guard-1", absolute_drift="0"):
    conn.execute(
        """
        INSERT INTO ai_feature_quality_drift_guard_feature_drifts (
            drift_id,
            review_label,
            created_at,
            source_learning_run_label,
            baseline_learning_run_label,
            feature_group,
            feature_name,
            current_normalized_value,
            baseline_normalized_value,
            absolute_drift,
            drift_status,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            drift_id,
            review_label,
            "2026-01-01T00:00:00+00:00",
            "learning-1",
            "learning-baseline",
            "performance",
            "cumulative_net_pnl_bps",
            "0.96",
            "0.96",
            absolute_drift,
            "AI_FEATURE_DRIFT_WITHIN_LIMIT",
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
        ),
    )


def seed_good(conn):
    create_guard_tables(conn)
    insert_guard_review(conn)
    insert_guard_check(conn)
    insert_guard_drift(conn)


def test_parse_labels_deduplicates():
    assert parse_labels("guard-1,guard-2,guard-1") == ["guard-1", "guard-2"]


def test_parse_symbols_deduplicates_and_uppercases():
    assert parse_symbols("btcusdt, ETHUSDT,btcusdt") == ["BTCUSDT", "ETHUSDT"]


def test_scheduler_approves_good_guard_and_persists(tmp_path):
    db_path = tmp_path / "mission72.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_paper_dataset_expansion_scheduler(
        db_path=db_path,
        schedule_label="schedule-1",
        report_label="report-1",
        guard_review_label="guard-1",
        symbols="BTCUSDT,ETHUSDT",
        planned_cycle_count=2,
        schedule_start_at="2026-01-02T00:00:00+00:00",
    )

    assert result["schedule_decision"] == DECISION_READY
    assert result["global_verdict"] == VERDICT_READY
    assert result["planned_cycle_count"] == 2
    assert result["planned_symbol_count"] == 2
    assert result["planned_item_count"] == 4
    assert result["expansion_check_count"] == 13
    assert result["pass_check_count"] == 13
    assert result["fail_check_count"] == 0
    assert result["safety_breach_count"] == 0

    with sqlite3.connect(db_path) as conn:
        schedule = conn.execute(
            """
            SELECT schedule_label, schedule_decision, global_verdict
            FROM ai_paper_dataset_expansion_schedules
            WHERE schedule_label = ?
            """,
            ("schedule-1",),
        ).fetchone()

        item_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM ai_paper_dataset_expansion_schedule_items
            WHERE schedule_label = ?
            """,
            ("schedule-1",),
        ).fetchone()[0]

    assert schedule == ("schedule-1", DECISION_READY, VERDICT_READY)
    assert item_count == 4


def test_scheduler_rejects_missing_guard(tmp_path):
    db_path = tmp_path / "mission72-missing.db"

    result = run_ai_paper_dataset_expansion_scheduler(
        db_path=db_path,
        schedule_label="missing-schedule",
        report_label="missing-report",
        guard_review_label="missing-guard",
    )

    assert result["schedule_decision"] == DECISION_REJECT_MISSING
    assert result["global_verdict"] == VERDICT_MISSING
    assert result["fail_check_count"] == 1


def test_scheduler_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "mission72-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_guard_tables(conn)
        insert_guard_review(conn, safety_breach_count=1, live_trading="ENABLED")
        insert_guard_check(conn)
        conn.commit()

    result = run_ai_paper_dataset_expansion_scheduler(
        db_path=db_path,
        schedule_label="safety-schedule",
        report_label="safety-report",
        guard_review_label="guard-1",
    )

    assert result["schedule_decision"] == DECISION_BLOCK_SAFETY
    assert result["global_verdict"] == VERDICT_BLOCKED
    assert result["safety_breach_count"] >= 1


def test_scheduler_flags_unapproved_guard(tmp_path):
    db_path = tmp_path / "mission72-unapproved.db"

    with sqlite3.connect(db_path) as conn:
        create_guard_tables(conn)
        insert_guard_review(
            conn,
            guard_decision="AI_FEATURE_QUALITY_DRIFT_GUARD_UNSTABLE_REVIEW_REQUIRED",
            verdict="AI_FEATURE_QUALITY_DRIFT_GUARD_UNSTABLE_SHADOW_ONLY",
            quality_state="AI_FEATURE_QUALITY_STATE_UNSTABLE",
        )
        conn.commit()

    result = run_ai_paper_dataset_expansion_scheduler(
        db_path=db_path,
        schedule_label="unapproved-schedule",
        report_label="unapproved-report",
        guard_review_label="guard-1",
    )

    assert result["schedule_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["fail_check_count"] >= 1


def test_scheduler_flags_high_feature_drift(tmp_path):
    db_path = tmp_path / "mission72-drift.db"

    with sqlite3.connect(db_path) as conn:
        create_guard_tables(conn)
        insert_guard_review(conn, max_feature_drift="0.25")
        insert_guard_drift(conn, absolute_drift="0.25")
        conn.commit()

    result = run_ai_paper_dataset_expansion_scheduler(
        db_path=db_path,
        schedule_label="drift-schedule",
        report_label="drift-report",
        guard_review_label="guard-1",
        max_allowed_feature_drift=0.10,
    )

    assert result["schedule_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["max_feature_drift"] == 0.25


def test_scheduler_flags_over_expansion(tmp_path):
    db_path = tmp_path / "mission72-over.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_paper_dataset_expansion_scheduler(
        db_path=db_path,
        schedule_label="over-schedule",
        report_label="over-report",
        guard_review_label="guard-1",
        planned_cycle_count=10,
        max_planned_cycles=6,
    )

    assert result["schedule_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE


def test_scheduler_flags_target_total_cycles_not_met(tmp_path):
    db_path = tmp_path / "mission72-target.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_paper_dataset_expansion_scheduler(
        db_path=db_path,
        schedule_label="target-schedule",
        report_label="target-report",
        guard_review_label="guard-1",
        planned_cycle_count=1,
        min_planned_cycles=1,
        target_total_cycles=5,
    )

    assert result["schedule_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE


def test_markdown_report_contains_paper_only_scope(tmp_path):
    db_path = tmp_path / "mission72-markdown.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_paper_dataset_expansion_scheduler(
        db_path=db_path,
        schedule_label="markdown-schedule",
        report_label="markdown-report",
        guard_review_label="guard-1",
    )

    assert "# DeltaGrid Mission 72" in result["markdown_report"]
    assert "paper dataset collection plans only" in result["markdown_report"]
    assert "does not perform autonomous trading" in result["markdown_report"]
    assert "No exchange orders were sent." in result["markdown_report"]
