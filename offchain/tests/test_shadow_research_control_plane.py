import sqlite3

from offchain.control_plane.shadow_research_control_plane import (
    CONTROL_CONTINUE,
    CONTROL_SAFETY_BREACH,
    parse_symbols,
    run_shadow_research_control_plane,
)


def create_ledger_table(conn):
    conn.execute(
        """
        CREATE TABLE shadow_observation_ledger_entries (
            ledger_entry_id TEXT PRIMARY KEY,
            bridge_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_plan_label TEXT NOT NULL,
            source_plan_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            observation_priority INTEGER NOT NULL,
            ledger_status TEXT NOT NULL,
            shadow_notional_usd TEXT NOT NULL,
            planned_holding_funding_events INTEGER NOT NULL,
            remaining_holding_funding_events INTEGER NOT NULL,
            fee_bps_per_side TEXT NOT NULL,
            slippage_bps TEXT NOT NULL,
            average_funding_rate_bps TEXT NOT NULL,
            latest_spread_bps TEXT NOT NULL,
            gross_horizon_carry_bps TEXT NOT NULL,
            estimated_cost_bps TEXT NOT NULL,
            expected_net_carry_bps TEXT NOT NULL,
            break_even_funding_bps TEXT NOT NULL,
            funding_gap_to_break_even_bps TEXT NOT NULL,
            observation_state TEXT NOT NULL,
            ledger_reason TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def create_market_tables(conn):
    conn.execute(
        """
        CREATE TABLE historical_public_funding_rates (
            dataset_label TEXT NOT NULL,
            symbol TEXT NOT NULL,
            funding_time INTEGER NOT NULL,
            funding_time_iso TEXT NOT NULL,
            funding_rate TEXT NOT NULL,
            funding_rate_bps TEXT NOT NULL,
            annualized_funding_rate TEXT NOT NULL,
            mark_price TEXT NOT NULL,
            source TEXT NOT NULL,
            data_mode TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            raw_payload_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            PRIMARY KEY (dataset_label, symbol, funding_time)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE historical_public_basis_observations (
            basis_id TEXT PRIMARY KEY,
            dataset_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            source_snapshot_id TEXT,
            source_ingestion_label TEXT,
            source TEXT NOT NULL,
            data_mode TEXT NOT NULL,
            mark_price TEXT NOT NULL,
            index_price TEXT NOT NULL,
            basis_bps TEXT NOT NULL,
            spread_bps TEXT NOT NULL,
            quote_volume TEXT NOT NULL,
            last_funding_rate TEXT NOT NULL,
            annualized_funding_rate TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            raw_payload_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def insert_ledger_entry(
    conn,
    bridge_label="bridge-1",
    symbol="BTCUSDT",
    priority=1,
    remaining_events=81,
    expected_net_carry_bps=25.0,
    estimated_cost_bps=0.3,
    live_order_sent=0,
):
    conn.execute(
        """
        INSERT INTO shadow_observation_ledger_entries (
            ledger_entry_id,
            bridge_label,
            created_at,
            source_plan_label,
            source_plan_id,
            symbol,
            observation_priority,
            ledger_status,
            shadow_notional_usd,
            planned_holding_funding_events,
            remaining_holding_funding_events,
            fee_bps_per_side,
            slippage_bps,
            average_funding_rate_bps,
            latest_spread_bps,
            gross_horizon_carry_bps,
            estimated_cost_bps,
            expected_net_carry_bps,
            break_even_funding_bps,
            funding_gap_to_break_even_bps,
            observation_state,
            ledger_reason,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{bridge_label}-{symbol}",
            bridge_label,
            "2026-01-01T00:00:00+00:00",
            "plan-1",
            f"plan-{symbol}",
            symbol,
            priority,
            "LEDGER_ENTRY_ACTIVE_SHADOW_TRACKING",
            "1000",
            81,
            remaining_events,
            "0.1",
            "0.1",
            "0.5",
            "0.1",
            "20.0",
            str(estimated_cost_bps),
            str(expected_net_carry_bps),
            "0.01",
            "0.49",
            "TRACKING_NOT_STARTED_SHADOW_ONLY",
            "test",
            "DISABLED",
            live_order_sent,
            "BLOCKED",
            "{}",
        ),
    )


def insert_market_data(
    conn,
    dataset_label="dataset-1",
    symbol="BTCUSDT",
    funding_bps=0.6,
    basis_bps=-2.0,
    spread_bps=0.05,
):
    conn.execute(
        """
        INSERT INTO historical_public_funding_rates (
            dataset_label,
            symbol,
            funding_time,
            funding_time_iso,
            funding_rate,
            funding_rate_bps,
            annualized_funding_rate,
            mark_price,
            source,
            data_mode,
            live_trading,
            live_order_sent,
            capital_deployment,
            raw_payload_json,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dataset_label,
            symbol,
            1700000000000,
            "2026-01-01T00:00:00+00:00",
            str(funding_bps / 10000.0),
            str(funding_bps),
            "0.1",
            "100",
            "test",
            "ONLINE_PUBLIC_API",
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
            "{}",
        ),
    )

    conn.execute(
        """
        INSERT INTO historical_public_basis_observations (
            basis_id,
            dataset_label,
            created_at,
            symbol,
            source_snapshot_id,
            source_ingestion_label,
            source,
            data_mode,
            mark_price,
            index_price,
            basis_bps,
            spread_bps,
            quote_volume,
            last_funding_rate,
            annualized_funding_rate,
            live_trading,
            live_order_sent,
            capital_deployment,
            raw_payload_json,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{dataset_label}-{symbol}-basis",
            dataset_label,
            "2026-01-01T00:00:00+00:00",
            symbol,
            None,
            None,
            "test",
            "ONLINE_PUBLIC_API",
            "100",
            "100",
            str(basis_bps),
            str(spread_bps),
            "1000000",
            str(funding_bps / 10000.0),
            "0.1",
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
            "{}",
        ),
    )


def create_docs_root(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    required = {
        "ROADMAP.md": "Mission 58: Shadow Research Control Plane",
        "MISSION_INDEX.md": "Mission 58",
        "ARCHITECTURE_STATE.md": "Shadow Research Control Plane",
        "RISK_POLICY.md": "Live Trading Remains Blocked",
        "RESEARCH_POLICY.md": "Research-First Operating Model",
        "SAFETY_INVARIANTS.md": "Non-Negotiable Safety Invariants",
        "DOCUMENTATION_REGISTRY.md": "Mission 58 Documentation Registry",
        "PROJECT_SOURCE_OF_TRUTH.md": "Mission 58 Completion Record",
    }

    for name, marker in required.items():
        (docs / name).write_text(f"# {name}\n\n{marker}\n", encoding="utf-8")

    return docs


def test_parse_symbols_deduplicates_and_uppercases():
    assert parse_symbols("btcusdt, ETHUSDT,btcusdt") == ["BTCUSDT", "ETHUSDT"]


def test_control_plane_runs_full_shadow_cycle_and_persists(tmp_path):
    db_path = tmp_path / "mission58.db"
    docs_root = create_docs_root(tmp_path)

    with sqlite3.connect(db_path) as conn:
        create_ledger_table(conn)
        create_market_tables(conn)
        insert_ledger_entry(conn, symbol="BTCUSDT", priority=1, expected_net_carry_bps=25.0)
        insert_ledger_entry(conn, symbol="ETHUSDT", priority=2, expected_net_carry_bps=9.0)
        insert_market_data(conn, symbol="BTCUSDT", funding_bps=0.6, spread_bps=0.05)
        insert_market_data(conn, symbol="ETHUSDT", funding_bps=0.7, spread_bps=0.05)
        conn.commit()

    result = run_shadow_research_control_plane(
        db_path=db_path,
        cycle_label="mission58-cycle",
        report_label="mission58-report",
        bridge_label="bridge-1",
        market_dataset_label="dataset-1",
        symbols="BTCUSDT,ETHUSDT",
        docs_root=docs_root,
    )

    assert result["control_plane_verdict"] == CONTROL_CONTINUE
    assert result["stage_count"] == 5
    assert result["tracking_update_count"] == 2
    assert result["route_count"] == 2
    assert result["continue_route_count"] == 2
    assert result["documentation_ready_count"] == result["documentation_registry_count"]

    with sqlite3.connect(db_path) as conn:
        cycle = conn.execute(
            """
            SELECT report_label, stage_count, route_count, continue_route_count, control_plane_verdict
            FROM shadow_research_control_plane_cycles
            WHERE report_label = ?
            """,
            ("mission58-report",),
        ).fetchone()

        stage_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM shadow_research_control_plane_stage_runs
            WHERE cycle_label = ?
            """,
            ("mission58-cycle",),
        ).fetchone()[0]

        doc_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM shadow_research_documentation_registry
            WHERE cycle_label = ?
            """,
            ("mission58-cycle",),
        ).fetchone()[0]

    assert cycle == ("mission58-report", 5, 2, 2, CONTROL_CONTINUE)
    assert stage_count == 5
    assert doc_count == result["documentation_registry_count"]


def test_control_plane_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "mission58-safety.db"
    docs_root = create_docs_root(tmp_path)

    with sqlite3.connect(db_path) as conn:
        create_ledger_table(conn)
        create_market_tables(conn)
        insert_ledger_entry(conn, symbol="BTCUSDT", live_order_sent=1)
        insert_market_data(conn, symbol="BTCUSDT", funding_bps=0.6)
        conn.commit()

    result = run_shadow_research_control_plane(
        db_path=db_path,
        cycle_label="mission58-safety-cycle",
        report_label="mission58-safety-report",
        bridge_label="bridge-1",
        market_dataset_label="dataset-1",
        symbols="BTCUSDT",
        docs_root=docs_root,
    )

    assert result["control_plane_verdict"] == CONTROL_SAFETY_BREACH
    assert result["safety_breach_count"] > 0
    assert result["blocked_stage_count"] > 0


def test_control_plane_handles_missing_ledger_history(tmp_path):
    db_path = tmp_path / "mission58-missing.db"
    docs_root = create_docs_root(tmp_path)

    result = run_shadow_research_control_plane(
        db_path=db_path,
        cycle_label="mission58-missing-cycle",
        report_label="mission58-missing-report",
        bridge_label="bridge-1",
        market_dataset_label="dataset-1",
        symbols="BTCUSDT",
        docs_root=docs_root,
    )

    assert result["stage_count"] == 5
    assert result["tracking_update_count"] == 0
    assert result["route_count"] == 0
    assert result["control_plane_verdict"] != CONTROL_CONTINUE


def test_documentation_registry_detects_incomplete_docs(tmp_path):
    db_path = tmp_path / "mission58-docs.db"
    docs_root = tmp_path / "docs"
    docs_root.mkdir()
    (docs_root / "ROADMAP.md").write_text("Mission 58: Shadow Research Control Plane", encoding="utf-8")

    result = run_shadow_research_control_plane(
        db_path=db_path,
        cycle_label="mission58-docs-cycle",
        report_label="mission58-docs-report",
        bridge_label="bridge-1",
        market_dataset_label="dataset-1",
        symbols="BTCUSDT",
        docs_root=docs_root,
    )

    assert result["documentation_ready_count"] < result["documentation_registry_count"]


def test_markdown_report_contains_shadow_safety_statement(tmp_path):
    db_path = tmp_path / "mission58-markdown.db"
    docs_root = create_docs_root(tmp_path)

    result = run_shadow_research_control_plane(
        db_path=db_path,
        cycle_label="mission58-markdown-cycle",
        report_label="mission58-markdown-report",
        bridge_label="bridge-1",
        market_dataset_label="dataset-1",
        symbols="BTCUSDT",
        docs_root=docs_root,
    )

    assert "# DeltaGrid Mission 58" in result["markdown_report"]
    assert "Live trading remains disabled." in result["markdown_report"]
    assert "No paid APIs were used." in result["markdown_report"]
