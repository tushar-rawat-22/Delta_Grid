import sqlite3

from offchain.ai_dataset.outcome_dataset_builder import (
    DECISION_BLOCK_SAFETY,
    DECISION_READY,
    DECISION_REJECT_MISSING,
    DECISION_UNSTABLE,
    HANDOFF_STATUS_READY,
    OUTCOME_LABEL_PENDING,
    TARGET_LABEL_PENDING,
    VERDICT_BLOCKED,
    VERDICT_MISSING,
    VERDICT_READY,
    VERDICT_UNSTABLE,
    parse_labels,
    run_ai_outcome_dataset_builder,
)


def create_schedule_tables(conn):
    conn.execute(
        """
        CREATE TABLE ai_paper_dataset_expansion_schedules (
            schedule_label TEXT PRIMARY KEY,
            report_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_guard_review_label TEXT,
            source_learning_run_label TEXT,
            source_multi_cycle_track_label TEXT,
            source_session_label TEXT,
            source_portfolio_label TEXT,
            planned_cycle_count INTEGER NOT NULL,
            planned_symbol_count INTEGER NOT NULL,
            planned_item_count INTEGER NOT NULL,
            schedule_start_at TEXT NOT NULL,
            schedule_end_at TEXT NOT NULL,
            schedule_interval_hours INTEGER NOT NULL,
            min_required_prior_cycles INTEGER NOT NULL,
            current_cycle_count INTEGER NOT NULL,
            target_total_cycles INTEGER NOT NULL,
            max_feature_drift TEXT NOT NULL,
            learning_score TEXT NOT NULL,
            guard_quality_check_count INTEGER NOT NULL,
            guard_pass_check_count INTEGER NOT NULL,
            guard_fail_check_count INTEGER NOT NULL,
            safety_breach_count INTEGER NOT NULL,
            expansion_check_count INTEGER NOT NULL,
            pass_check_count INTEGER NOT NULL,
            fail_check_count INTEGER NOT NULL,
            schedule_state TEXT NOT NULL,
            schedule_decision TEXT NOT NULL,
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
        CREATE TABLE ai_paper_dataset_expansion_schedule_items (
            item_id TEXT PRIMARY KEY,
            schedule_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_guard_review_label TEXT NOT NULL,
            item_index INTEGER NOT NULL,
            planned_cycle_index INTEGER NOT NULL,
            planned_symbol TEXT NOT NULL,
            planned_start_at TEXT NOT NULL,
            planned_end_at TEXT NOT NULL,
            item_status TEXT NOT NULL,
            collection_scope TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_paper_dataset_expansion_checks (
            check_id TEXT PRIMARY KEY,
            schedule_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_guard_review_label TEXT NOT NULL,
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


def insert_schedule(
    conn,
    label="schedule-1",
    planned_cycle_count=2,
    planned_symbol_count=2,
    planned_item_count=4,
    source_guard="guard-1",
    source_learning="learning-1",
    source_track="track-1",
    source_session="session-1",
    source_portfolio="portfolio-1",
    safety_breach_count=0,
    fail_check_count=0,
    state="AI_DATASET_EXPANSION_SCHEDULE_READY",
    decision="AI_DATASET_EXPANSION_SCHEDULE_APPROVED_PAPER_ONLY",
    verdict="AI_DATASET_EXPANSION_SCHEDULE_READY_SHADOW_ONLY",
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO ai_paper_dataset_expansion_schedules (
            schedule_label,
            report_label,
            created_at,
            source_guard_review_label,
            source_learning_run_label,
            source_multi_cycle_track_label,
            source_session_label,
            source_portfolio_label,
            planned_cycle_count,
            planned_symbol_count,
            planned_item_count,
            schedule_start_at,
            schedule_end_at,
            schedule_interval_hours,
            min_required_prior_cycles,
            current_cycle_count,
            target_total_cycles,
            max_feature_drift,
            learning_score,
            guard_quality_check_count,
            guard_pass_check_count,
            guard_fail_check_count,
            safety_breach_count,
            expansion_check_count,
            pass_check_count,
            fail_check_count,
            schedule_state,
            schedule_decision,
            global_verdict,
            recommended_action,
            next_mission,
            live_trading,
            live_order_sent,
            capital_deployment,
            summary_json,
            markdown_report
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            label,
            f"{label}-report",
            "2026-01-01T00:00:00+00:00",
            source_guard,
            source_learning,
            source_track,
            source_session,
            source_portfolio,
            planned_cycle_count,
            planned_symbol_count,
            planned_item_count,
            "2026-01-01T00:00:00+00:00",
            "2026-01-03T00:00:00+00:00",
            24,
            1,
            1,
            3,
            "0",
            "84.8641975",
            16,
            16,
            0,
            safety_breach_count,
            13,
            13,
            fail_check_count,
            state,
            decision,
            verdict,
            "RUN_SCHEDULED_PAPER_DATASET_COLLECTION_ONLY",
            "Mission 73 AI Outcome Dataset Builder",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
            "# report",
        ),
    )


def insert_item(conn, schedule_label="schedule-1", cycle=1, symbol="BTCUSDT", index=1):
    conn.execute(
        """
        INSERT INTO ai_paper_dataset_expansion_schedule_items (
            item_id,
            schedule_label,
            created_at,
            source_guard_review_label,
            item_index,
            planned_cycle_index,
            planned_symbol,
            planned_start_at,
            planned_end_at,
            item_status,
            collection_scope,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{schedule_label}-cycle-{cycle}-{symbol}",
            schedule_label,
            "2026-01-01T00:00:00+00:00",
            "guard-1",
            index,
            cycle,
            symbol,
            "2026-01-01T00:00:00+00:00",
            "2026-01-02T00:00:00+00:00",
            "AI_DATASET_EXPANSION_ITEM_PLANNED_PAPER_ONLY",
            "PAPER_DATASET_COLLECTION_PLAN_ONLY",
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
        ),
    )


def insert_check(conn, schedule_label="schedule-1"):
    conn.execute(
        """
        INSERT INTO ai_paper_dataset_expansion_checks (
            check_id,
            schedule_label,
            created_at,
            source_guard_review_label,
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
            f"{schedule_label}-safety",
            schedule_label,
            "2026-01-01T00:00:00+00:00",
            "guard-1",
            "safety",
            "safety breach count",
            "AI_DATASET_EXPANSION_CHECK_PASS",
            "0",
            "0",
            "test",
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
        ),
    )


def seed_good(conn):
    create_schedule_tables(conn)
    insert_schedule(conn)
    insert_item(conn, cycle=1, symbol="BTCUSDT", index=1)
    insert_item(conn, cycle=1, symbol="ETHUSDT", index=2)
    insert_item(conn, cycle=2, symbol="BTCUSDT", index=3)
    insert_item(conn, cycle=2, symbol="ETHUSDT", index=4)
    insert_check(conn)


def test_parse_labels_deduplicates():
    assert parse_labels("schedule-1,schedule-2,schedule-1") == ["schedule-1", "schedule-2"]


def test_builder_creates_dataset_rows_and_persists(tmp_path):
    db_path = tmp_path / "mission73.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_outcome_dataset_builder(
        db_path=db_path,
        build_label="build-1",
        report_label="report-1",
        schedule_label="schedule-1",
    )

    assert result["build_decision"] == DECISION_READY
    assert result["global_verdict"] == VERDICT_READY
    assert result["dataset_row_count"] == 4
    assert result["pending_outcome_count"] == 4
    assert result["training_eligible_count"] == 0
    assert result["lineage_complete_count"] == 4
    assert result["quality_check_count"] == 14
    assert result["pass_check_count"] == 14
    assert result["fail_check_count"] == 0
    assert result["handoff"]["handoff_status"] == HANDOFF_STATUS_READY

    with sqlite3.connect(db_path) as conn:
        build = conn.execute(
            """
            SELECT build_label, build_decision, global_verdict
            FROM ai_outcome_dataset_builds
            WHERE build_label = ?
            """,
            ("build-1",),
        ).fetchone()

        row_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM ai_outcome_dataset_rows
            WHERE build_label = ?
            """,
            ("build-1",),
        ).fetchone()[0]

    assert build == ("build-1", DECISION_READY, VERDICT_READY)
    assert row_count == 4


def test_builder_rejects_missing_schedule(tmp_path):
    db_path = tmp_path / "mission73-missing.db"

    result = run_ai_outcome_dataset_builder(
        db_path=db_path,
        build_label="missing-build",
        report_label="missing-report",
        schedule_label="missing-schedule",
    )

    assert result["build_decision"] == DECISION_REJECT_MISSING
    assert result["global_verdict"] == VERDICT_MISSING
    assert result["fail_check_count"] == 1


def test_builder_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "mission73-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_schedule_tables(conn)
        insert_schedule(conn, safety_breach_count=1, live_trading="ENABLED")
        conn.commit()

    result = run_ai_outcome_dataset_builder(
        db_path=db_path,
        build_label="safety-build",
        report_label="safety-report",
        schedule_label="schedule-1",
    )

    assert result["build_decision"] == DECISION_BLOCK_SAFETY
    assert result["global_verdict"] == VERDICT_BLOCKED
    assert result["safety_breach_count"] >= 1


def test_builder_flags_unapproved_schedule(tmp_path):
    db_path = tmp_path / "mission73-unapproved.db"

    with sqlite3.connect(db_path) as conn:
        create_schedule_tables(conn)
        insert_schedule(
            conn,
            state="AI_DATASET_EXPANSION_SCHEDULE_UNSTABLE",
            decision="AI_DATASET_EXPANSION_SCHEDULE_UNSTABLE_REVIEW_REQUIRED",
            verdict="AI_DATASET_EXPANSION_SCHEDULE_UNSTABLE_SHADOW_ONLY",
        )
        conn.commit()

    result = run_ai_outcome_dataset_builder(
        db_path=db_path,
        build_label="unapproved-build",
        report_label="unapproved-report",
        schedule_label="schedule-1",
    )

    assert result["build_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["fail_check_count"] >= 1


def test_builder_flags_missing_schedule_items(tmp_path):
    db_path = tmp_path / "mission73-items.db"

    with sqlite3.connect(db_path) as conn:
        create_schedule_tables(conn)
        insert_schedule(conn)
        conn.commit()

    result = run_ai_outcome_dataset_builder(
        db_path=db_path,
        build_label="items-build",
        report_label="items-report",
        schedule_label="schedule-1",
    )

    assert result["build_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["dataset_row_count"] == 0


def test_builder_flags_incomplete_lineage(tmp_path):
    db_path = tmp_path / "mission73-lineage.db"

    with sqlite3.connect(db_path) as conn:
        create_schedule_tables(conn)
        insert_schedule(conn, source_learning=None)
        insert_item(conn, cycle=1, symbol="BTCUSDT", index=1)
        insert_item(conn, cycle=1, symbol="ETHUSDT", index=2)
        insert_item(conn, cycle=2, symbol="BTCUSDT", index=3)
        insert_item(conn, cycle=2, symbol="ETHUSDT", index=4)
        conn.commit()

    result = run_ai_outcome_dataset_builder(
        db_path=db_path,
        build_label="lineage-build",
        report_label="lineage-report",
        schedule_label="schedule-1",
    )

    assert result["build_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["lineage_complete_count"] == 0


def test_builder_rows_are_pending_and_not_training_eligible(tmp_path):
    db_path = tmp_path / "mission73-pending.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_outcome_dataset_builder(
        db_path=db_path,
        build_label="pending-build",
        report_label="pending-report",
        schedule_label="schedule-1",
    )

    assert all(row["outcome_label"] == OUTCOME_LABEL_PENDING for row in result["dataset_rows"])
    assert all(row["target_label"] == TARGET_LABEL_PENDING for row in result["dataset_rows"])
    assert all(row["training_eligible"] == 0 for row in result["dataset_rows"])


def test_builder_flags_too_few_rows(tmp_path):
    db_path = tmp_path / "mission73-minrows.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_outcome_dataset_builder(
        db_path=db_path,
        build_label="minrows-build",
        report_label="minrows-report",
        schedule_label="schedule-1",
        min_dataset_rows=5,
    )

    assert result["build_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE


def test_markdown_report_contains_paper_only_scope(tmp_path):
    db_path = tmp_path / "mission73-markdown.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_outcome_dataset_builder(
        db_path=db_path,
        build_label="markdown-build",
        report_label="markdown-report",
        schedule_label="schedule-1",
    )

    assert "# DeltaGrid Mission 73" in result["markdown_report"]
    assert "paper-only AI outcome dataset rows" in result["markdown_report"]
    assert "not training-eligible until paper outcomes are collected" in result["markdown_report"]
    assert "No exchange orders were sent." in result["markdown_report"]
