import sqlite3

from offchain.portfolio.shadow_portfolio_simulator import (
    ALLOC_EXCLUDED,
    ALLOC_INCLUDED,
    PORTFOLIO_NO_ELIGIBLE,
    PORTFOLIO_READY,
    parse_symbols,
    run_shadow_portfolio_simulator,
)


def create_gate_table(conn):
    conn.execute(
        """
        CREATE TABLE data_quality_strategy_candidate_gates (
            gate_id TEXT PRIMARY KEY,
            regime_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_factory_label TEXT NOT NULL,
            source_candidate_id TEXT NOT NULL,
            strategy_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            candidate_status TEXT NOT NULL,
            promotion_eligible INTEGER NOT NULL,
            alpha_score TEXT NOT NULL,
            market_risk_state TEXT NOT NULL,
            data_quality_score TEXT NOT NULL,
            candidate_gate_status TEXT NOT NULL,
            gate_reason TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def insert_gate(
    conn,
    gate_id,
    regime_label="regime-1",
    strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH",
    symbol="BTCUSDT",
    alpha_score="100",
    promotion_eligible=1,
    gate_status="CANDIDATE_GATE_PASS_RESEARCH_REVIEW",
    market_risk_state="MARKET_RISK_STATE_NORMAL",
    data_quality_score="95",
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO data_quality_strategy_candidate_gates (
            gate_id,
            regime_label,
            created_at,
            source_factory_label,
            source_candidate_id,
            strategy_id,
            symbol,
            candidate_status,
            promotion_eligible,
            alpha_score,
            market_risk_state,
            data_quality_score,
            candidate_gate_status,
            gate_reason,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            gate_id,
            regime_label,
            "2026-01-01T00:00:00+00:00",
            "factory-1",
            f"candidate-{gate_id}",
            strategy_id,
            symbol,
            "STRATEGY_CANDIDATE_PROMOTION_SHORTLIST_SHADOW_ONLY",
            promotion_eligible,
            alpha_score,
            market_risk_state,
            data_quality_score,
            gate_status,
            "test",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
        ),
    )


def test_parse_symbols_deduplicates_and_uppercases():
    assert parse_symbols("btcusdt, ETHUSDT,btcusdt") == ["BTCUSDT", "ETHUSDT"]


def test_portfolio_simulator_allocates_and_persists(tmp_path):
    db_path = tmp_path / "mission61.db"

    with sqlite3.connect(db_path) as conn:
        create_gate_table(conn)
        insert_gate(conn, "gate-1", symbol="BTCUSDT", strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH", alpha_score="100")
        insert_gate(conn, "gate-2", symbol="ETHUSDT", strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH", alpha_score="80")
        insert_gate(conn, "gate-3", symbol="ETHUSDT", strategy_id="BASIS_MEAN_REVERSION", alpha_score="70")
        insert_gate(conn, "gate-4", symbol="BTCUSDT", strategy_id="VOLATILITY_REGIME_FILTER", alpha_score="60")
        conn.commit()

    result = run_shadow_portfolio_simulator(
        db_path=db_path,
        portfolio_label="portfolio-1",
        report_label="report-1",
        regime_label="regime-1",
        shadow_notional=100000,
        max_symbol_weight=0.6,
        max_strategy_weight=0.5,
        max_candidate_weight=0.35,
    )

    assert result["source_gate_count"] == 4
    assert result["eligible_candidate_count"] == 4
    assert result["included_allocation_count"] >= 3
    assert result["total_allocated_weight"] <= 1.0
    assert result["allocated_notional"] <= 100000
    assert result["safety_breach_count"] == 0
    assert result["global_verdict"] == PORTFOLIO_READY

    with sqlite3.connect(db_path) as conn:
        allocation_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM shadow_portfolio_allocations
            WHERE portfolio_label = ?
            """,
            ("portfolio-1",),
        ).fetchone()[0]

        report = conn.execute(
            """
            SELECT portfolio_label, source_gate_count, global_verdict
            FROM shadow_portfolio_simulations
            WHERE portfolio_label = ?
            """,
            ("portfolio-1",),
        ).fetchone()

    assert allocation_count == 4
    assert report == ("portfolio-1", 4, PORTFOLIO_READY)


def test_portfolio_respects_caps(tmp_path):
    db_path = tmp_path / "mission61-caps.db"

    with sqlite3.connect(db_path) as conn:
        create_gate_table(conn)
        insert_gate(conn, "gate-1", symbol="BTCUSDT", strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH", alpha_score="100")
        insert_gate(conn, "gate-2", symbol="BTCUSDT", strategy_id="VOLATILITY_REGIME_FILTER", alpha_score="90")
        insert_gate(conn, "gate-3", symbol="ETHUSDT", strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH", alpha_score="80")
        insert_gate(conn, "gate-4", symbol="ETHUSDT", strategy_id="BASIS_MEAN_REVERSION", alpha_score="70")
        conn.commit()

    result = run_shadow_portfolio_simulator(
        db_path=db_path,
        portfolio_label="caps-portfolio",
        report_label="caps-report",
        regime_label="regime-1",
        max_symbol_weight=0.55,
        max_strategy_weight=0.5,
        max_candidate_weight=0.35,
    )

    assert result["observed_max_symbol_weight"] <= 0.55
    assert result["observed_max_strategy_weight"] <= 0.5


def test_portfolio_excludes_watch_and_non_promotion_candidates(tmp_path):
    db_path = tmp_path / "mission61-exclusions.db"

    with sqlite3.connect(db_path) as conn:
        create_gate_table(conn)
        insert_gate(conn, "gate-pass", symbol="BTCUSDT", alpha_score="100")
        insert_gate(
            conn,
            "gate-watch",
            symbol="SOLUSDT",
            alpha_score="70",
            gate_status="CANDIDATE_GATE_WATCHLIST_ONLY_BY_REGIME",
        )
        insert_gate(
            conn,
            "gate-not-promo",
            symbol="ETHUSDT",
            alpha_score="60",
            promotion_eligible=0,
        )
        conn.commit()

    result = run_shadow_portfolio_simulator(
        db_path=db_path,
        portfolio_label="exclude-portfolio",
        report_label="exclude-report",
        regime_label="regime-1",
    )

    included = [item for item in result["allocations"] if item["allocation_status"] == ALLOC_INCLUDED]
    excluded = [item for item in result["allocations"] if item["allocation_status"] == ALLOC_EXCLUDED]

    assert len(included) == 1
    assert len(excluded) == 2
    assert included[0]["symbol"] == "BTCUSDT"


def test_portfolio_no_eligible_candidates(tmp_path):
    db_path = tmp_path / "mission61-empty.db"

    with sqlite3.connect(db_path) as conn:
        create_gate_table(conn)
        insert_gate(
            conn,
            "gate-watch",
            symbol="SOLUSDT",
            alpha_score="50",
            gate_status="CANDIDATE_GATE_WATCHLIST_ONLY_BY_REGIME",
            promotion_eligible=0,
        )
        conn.commit()

    result = run_shadow_portfolio_simulator(
        db_path=db_path,
        portfolio_label="empty-portfolio",
        report_label="empty-report",
        regime_label="regime-1",
    )

    assert result["included_allocation_count"] == 0
    assert result["global_verdict"] == PORTFOLIO_NO_ELIGIBLE


def test_markdown_report_contains_shadow_safety_statement(tmp_path):
    db_path = tmp_path / "mission61-markdown.db"

    with sqlite3.connect(db_path) as conn:
        create_gate_table(conn)
        insert_gate(conn, "gate-1")
        conn.commit()

    result = run_shadow_portfolio_simulator(
        db_path=db_path,
        portfolio_label="markdown-portfolio",
        report_label="markdown-report",
        regime_label="regime-1",
    )

    assert "# DeltaGrid Mission 61" in result["markdown_report"]
    assert "Live trading remains disabled." in result["markdown_report"]
    assert "No paid APIs were used." in result["markdown_report"]
