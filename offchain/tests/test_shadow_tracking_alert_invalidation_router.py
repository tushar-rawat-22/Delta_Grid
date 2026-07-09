import json
import sqlite3

from offchain.backtest.shadow_tracking_alert_invalidation_router import (
    CONTINUE_VERDICT,
    INVALIDATION_VERDICT,
    NO_PERFORMANCE_HISTORY_VERDICT,
    ROUTE_CONTINUE,
    ROUTE_INVALIDATE,
    ROUTE_SAFETY_BLOCK,
    SAFETY_BREACH_VERDICT,
    parse_symbols,
    run_shadow_tracking_alert_invalidation_router,
)


def create_performance_table(conn):
    conn.execute(
        """
        CREATE TABLE shadow_tracking_performance_reports (
            report_label TEXT PRIMARY KEY,
            performance_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_update_label TEXT,
            requested_symbol_count INTEGER NOT NULL,
            tracking_update_count INTEGER NOT NULL,
            active_count INTEGER NOT NULL,
            invalidated_count INTEGER NOT NULL,
            complete_count INTEGER NOT NULL,
            no_market_data_count INTEGER NOT NULL,
            safety_breach_count INTEGER NOT NULL,
            average_updated_remaining_carry_bps TEXT NOT NULL,
            average_carry_drift_bps TEXT NOT NULL,
            average_latest_funding_bps TEXT NOT NULL,
            average_latest_spread_bps TEXT NOT NULL,
            average_remaining_funding_events TEXT NOT NULL,
            strongest_symbol TEXT,
            weakest_symbol TEXT,
            strongest_updated_remaining_carry_bps TEXT NOT NULL,
            weakest_updated_remaining_carry_bps TEXT NOT NULL,
            global_verdict TEXT NOT NULL,
            recommended_action TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            markdown_report TEXT NOT NULL
        )
        """
    )


def insert_performance_report(
    conn,
    performance_label="performance-1",
    global_verdict="TRACKING_PERFORMANCE_STRONG_SHADOW_ONLY",
    safety_breach_count=0,
    symbol_health="SYMBOL_TRACKING_HEALTH_STRONG",
):
    summary = {
        "safety_breach_count": safety_breach_count,
        "symbol_summaries": [
            {
                "symbol": "ETHUSDT",
                "health_status": symbol_health,
                "latest_update_status": "TRACKING_UPDATE_ACTIVE_SHADOW_ONLY",
                "average_updated_remaining_carry_bps": 56.4,
                "average_carry_drift_bps": 47.3,
                "average_latest_funding_bps": 0.7,
                "average_latest_spread_bps": 0.05,
                "average_remaining_funding_events": 79,
            },
            {
                "symbol": "BTCUSDT",
                "health_status": symbol_health,
                "latest_update_status": "TRACKING_UPDATE_ACTIVE_SHADOW_ONLY",
                "average_updated_remaining_carry_bps": 48.3,
                "average_carry_drift_bps": 23.3,
                "average_latest_funding_bps": 0.6,
                "average_latest_spread_bps": 0.02,
                "average_remaining_funding_events": 79,
            },
        ],
    }

    conn.execute(
        """
        INSERT INTO shadow_tracking_performance_reports (
            report_label,
            performance_label,
            created_at,
            source_update_label,
            requested_symbol_count,
            tracking_update_count,
            active_count,
            invalidated_count,
            complete_count,
            no_market_data_count,
            safety_breach_count,
            average_updated_remaining_carry_bps,
            average_carry_drift_bps,
            average_latest_funding_bps,
            average_latest_spread_bps,
            average_remaining_funding_events,
            strongest_symbol,
            weakest_symbol,
            strongest_updated_remaining_carry_bps,
            weakest_updated_remaining_carry_bps,
            global_verdict,
            recommended_action,
            summary_json,
            markdown_report
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{performance_label}-report",
            performance_label,
            "2026-01-01T00:00:00+00:00",
            "update-1",
            2,
            2,
            2,
            0,
            0,
            0,
            safety_breach_count,
            "52.0",
            "35.0",
            "0.65",
            "0.04",
            "79",
            "ETHUSDT",
            "BTCUSDT",
            "56.4",
            "48.3",
            global_verdict,
            "test",
            json.dumps(summary, sort_keys=True),
            "# report",
        ),
    )


def test_parse_symbols_deduplicates_and_uppercases():
    assert parse_symbols("btcusdt, ETHUSDT,btcusdt") == ["BTCUSDT", "ETHUSDT"]


def test_missing_database_returns_no_performance_history(tmp_path):
    db_path = tmp_path / "missing.db"

    result = run_shadow_tracking_alert_invalidation_router(
        db_path=db_path,
        route_label="missing-route",
        report_label="missing-report",
    )

    assert result["global_verdict"] == NO_PERFORMANCE_HISTORY_VERDICT
    assert result["route_count"] == 0


def test_router_creates_continue_routes_and_persists(tmp_path):
    db_path = tmp_path / "mission57-continue.db"

    with sqlite3.connect(db_path) as conn:
        create_performance_table(conn)
        insert_performance_report(conn)
        conn.commit()

    result = run_shadow_tracking_alert_invalidation_router(
        db_path=db_path,
        route_label="mission57-route",
        report_label="mission57-report",
        performance_label="performance-1",
        symbols="BTCUSDT,ETHUSDT",
        min_continue_carry_bps=10.0,
        max_warning_spread_bps=1.0,
    )

    assert result["global_verdict"] == CONTINUE_VERDICT
    assert result["route_count"] == 2
    assert result["continue_route_count"] == 2
    assert result["routes"][0]["route_status"] == ROUTE_CONTINUE
    assert result["routes"][0]["symbol"] == "ETHUSDT"

    with sqlite3.connect(db_path) as conn:
        route_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM shadow_tracking_alert_routes
            WHERE route_label = ?
            """,
            ("mission57-route",),
        ).fetchone()[0]

        report = conn.execute(
            """
            SELECT report_label, route_count, continue_route_count, global_verdict
            FROM shadow_tracking_alert_router_reports
            WHERE report_label = ?
            """,
            ("mission57-report",),
        ).fetchone()

    assert route_count == 2
    assert report == ("mission57-report", 2, 2, CONTINUE_VERDICT)


def test_router_routes_invalidated_performance(tmp_path):
    db_path = tmp_path / "mission57-invalidated.db"

    with sqlite3.connect(db_path) as conn:
        create_performance_table(conn)
        insert_performance_report(
            conn,
            global_verdict="TRACKING_PERFORMANCE_INVALIDATED_SHADOW_ONLY",
            symbol_health="SYMBOL_TRACKING_HEALTH_INVALIDATED",
        )
        conn.commit()

    result = run_shadow_tracking_alert_invalidation_router(
        db_path=db_path,
        route_label="mission57-invalidated-route",
        report_label="mission57-invalidated-report",
        performance_label="performance-1",
    )

    assert result["global_verdict"] == INVALIDATION_VERDICT
    assert result["invalidation_route_count"] == 2
    assert result["routes"][0]["route_status"] == ROUTE_INVALIDATE


def test_router_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "mission57-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_performance_table(conn)
        insert_performance_report(
            conn,
            global_verdict="TRACKING_PERFORMANCE_SAFETY_BREACH_BLOCKED",
            safety_breach_count=1,
            symbol_health="SYMBOL_TRACKING_HEALTH_BLOCKED",
        )
        conn.commit()

    result = run_shadow_tracking_alert_invalidation_router(
        db_path=db_path,
        route_label="mission57-safety-route",
        report_label="mission57-safety-report",
        performance_label="performance-1",
    )

    assert result["global_verdict"] == SAFETY_BREACH_VERDICT
    assert result["safety_breach_count"] == 2
    assert result["routes"][0]["route_status"] == ROUTE_SAFETY_BLOCK


def test_markdown_report_contains_shadow_safety_statement(tmp_path):
    db_path = tmp_path / "mission57-markdown.db"

    with sqlite3.connect(db_path) as conn:
        create_performance_table(conn)
        insert_performance_report(conn)
        conn.commit()

    result = run_shadow_tracking_alert_invalidation_router(
        db_path=db_path,
        route_label="mission57-markdown-route",
        report_label="mission57-markdown-report",
        performance_label="performance-1",
    )

    assert "# DeltaGrid Mission 57" in result["markdown_report"]
    assert "Live trading remains disabled." in result["markdown_report"]
    assert "No paid APIs were used." in result["markdown_report"]
