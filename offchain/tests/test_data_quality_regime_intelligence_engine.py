import sqlite3

from offchain.research.data_quality_regime_intelligence_engine import (
    GATE_BLOCK,
    GATE_PASS,
    GATE_WATCH,
    REPORT_CAUTION,
    REPORT_DANGER,
    REPORT_READY,
    RISK_CAUTION,
    RISK_DANGER,
    RISK_NORMAL,
    parse_symbols,
    run_data_quality_regime_intelligence_engine,
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


def create_candidate_table(conn):
    conn.execute(
        """
        CREATE TABLE multi_strategy_research_candidates (
            candidate_id TEXT PRIMARY KEY,
            factory_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_dataset_label TEXT NOT NULL,
            strategy_id TEXT NOT NULL,
            strategy_family TEXT NOT NULL,
            symbol TEXT NOT NULL,
            rank INTEGER NOT NULL,
            candidate_status TEXT NOT NULL,
            promotion_eligible INTEGER NOT NULL,
            alpha_score TEXT NOT NULL,
            confidence_score TEXT NOT NULL,
            risk_score TEXT NOT NULL,
            data_quality_score TEXT NOT NULL,
            average_funding_bps TEXT NOT NULL,
            latest_funding_bps TEXT NOT NULL,
            funding_positive_ratio TEXT NOT NULL,
            funding_trend_bps TEXT NOT NULL,
            latest_basis_bps TEXT NOT NULL,
            latest_spread_bps TEXT NOT NULL,
            funding_volatility_bps TEXT NOT NULL,
            relative_strength_score TEXT NOT NULL,
            rejection_reason TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def insert_symbol_data(
    conn,
    dataset_label="dataset-1",
    symbol="BTCUSDT",
    funding_bps=0.5,
    basis_bps=-2.0,
    spread_bps=0.05,
    count=30,
    outlier=None,
):
    for i in range(count):
        value = funding_bps + (0.02 if i % 2 == 0 else -0.01)
        if outlier is not None and i == 0:
            value = outlier

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
                1700000000000 + i,
                "2026-01-01T00:00:00+00:00",
                str(value / 10000.0),
                str(value),
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


def insert_candidate(
    conn,
    factory_label="factory-1",
    candidate_id="candidate-1",
    symbol="BTCUSDT",
    strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH",
    alpha_score="100",
):
    conn.execute(
        """
        INSERT INTO multi_strategy_research_candidates (
            candidate_id,
            factory_label,
            created_at,
            source_dataset_label,
            strategy_id,
            strategy_family,
            symbol,
            rank,
            candidate_status,
            promotion_eligible,
            alpha_score,
            confidence_score,
            risk_score,
            data_quality_score,
            average_funding_bps,
            latest_funding_bps,
            funding_positive_ratio,
            funding_trend_bps,
            latest_basis_bps,
            latest_spread_bps,
            funding_volatility_bps,
            relative_strength_score,
            rejection_reason,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            candidate_id,
            factory_label,
            "2026-01-01T00:00:00+00:00",
            "dataset-1",
            strategy_id,
            "cross_sectional",
            symbol,
            1,
            "STRATEGY_CANDIDATE_PROMOTION_SHORTLIST_SHADOW_ONLY",
            1,
            alpha_score,
            "90",
            "5",
            "100",
            "0.5",
            "0.6",
            "0.8",
            "0.1",
            "-2",
            "0.05",
            "0.2",
            "100",
            "test",
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
        ),
    )


def test_parse_symbols_deduplicates_and_uppercases():
    assert parse_symbols("btcusdt, ETHUSDT,btcusdt") == ["BTCUSDT", "ETHUSDT"]


def test_engine_scores_symbol_regimes_and_persists(tmp_path):
    db_path = tmp_path / "mission60.db"

    with sqlite3.connect(db_path) as conn:
        create_market_tables(conn)
        insert_symbol_data(conn, symbol="BTCUSDT", funding_bps=0.7, basis_bps=-2.0, spread_bps=0.04)
        insert_symbol_data(conn, symbol="ETHUSDT", funding_bps=0.3, basis_bps=-2.0, spread_bps=0.05)
        conn.commit()

    result = run_data_quality_regime_intelligence_engine(
        db_path=db_path,
        regime_label="regime-1",
        report_label="report-1",
        dataset_label="dataset-1",
        symbols="BTCUSDT,ETHUSDT",
    )

    assert result["symbol_count"] == 2
    assert result["high_confidence_count"] == 2
    assert result["normal_risk_count"] == 2
    assert result["global_verdict"] == REPORT_READY
    assert result["safety_breach_count"] == 0

    with sqlite3.connect(db_path) as conn:
        symbol_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM data_quality_regime_symbol_reports
            WHERE regime_label = ?
            """,
            ("regime-1",),
        ).fetchone()[0]

        report = conn.execute(
            """
            SELECT report_label, symbol_count, global_verdict
            FROM data_quality_regime_intelligence_reports
            WHERE report_label = ?
            """,
            ("report-1",),
        ).fetchone()

    assert symbol_count == 2
    assert report == ("report-1", 2, REPORT_READY)


def test_engine_marks_missing_data_as_danger(tmp_path):
    db_path = tmp_path / "mission60-missing.db"

    result = run_data_quality_regime_intelligence_engine(
        db_path=db_path,
        regime_label="missing-regime",
        report_label="missing-report",
        dataset_label="dataset-1",
        symbols="BTCUSDT",
    )

    assert result["symbol_count"] == 1
    assert result["danger_risk_count"] == 1
    assert result["global_verdict"] == REPORT_DANGER
    assert result["symbol_reports"][0]["market_risk_state"] == RISK_DANGER


def test_engine_marks_wide_spread_as_caution(tmp_path):
    db_path = tmp_path / "mission60-wide.db"

    with sqlite3.connect(db_path) as conn:
        create_market_tables(conn)
        insert_symbol_data(conn, symbol="SOLUSDT", funding_bps=0.2, basis_bps=-3.0, spread_bps=1.2)
        conn.commit()

    result = run_data_quality_regime_intelligence_engine(
        db_path=db_path,
        regime_label="wide-regime",
        report_label="wide-report",
        dataset_label="dataset-1",
        symbols="SOLUSDT",
        max_acceptable_spread_bps=1.0,
    )

    assert result["symbol_count"] == 1
    assert result["caution_risk_count"] == 1
    assert result["symbol_reports"][0]["market_risk_state"] == RISK_CAUTION
    assert result["global_verdict"] == REPORT_CAUTION


def test_candidate_gates_use_symbol_regime(tmp_path):
    db_path = tmp_path / "mission60-gates.db"

    with sqlite3.connect(db_path) as conn:
        create_market_tables(conn)
        create_candidate_table(conn)
        insert_symbol_data(conn, symbol="BTCUSDT", funding_bps=0.7, basis_bps=-2.0, spread_bps=0.04)
        insert_symbol_data(conn, symbol="SOLUSDT", funding_bps=0.2, basis_bps=-3.0, spread_bps=1.2)
        insert_candidate(conn, candidate_id="btc-candidate", symbol="BTCUSDT")
        insert_candidate(conn, candidate_id="sol-candidate", symbol="SOLUSDT")
        insert_candidate(conn, candidate_id="missing-candidate", symbol="DOGEUSDT")
        conn.commit()

    result = run_data_quality_regime_intelligence_engine(
        db_path=db_path,
        regime_label="gate-regime",
        report_label="gate-report",
        dataset_label="dataset-1",
        factory_label="factory-1",
        symbols="BTCUSDT,SOLUSDT,DOGEUSDT",
        max_acceptable_spread_bps=1.0,
    )

    gate_counts = result["candidate_gate_counts"]

    assert result["candidate_gate_count"] == 3
    assert gate_counts[GATE_PASS] == 1
    assert gate_counts[GATE_WATCH] == 1
    assert gate_counts[GATE_BLOCK] == 1


def test_markdown_report_contains_shadow_safety_statement(tmp_path):
    db_path = tmp_path / "mission60-markdown.db"

    with sqlite3.connect(db_path) as conn:
        create_market_tables(conn)
        insert_symbol_data(conn, symbol="BTCUSDT")
        conn.commit()

    result = run_data_quality_regime_intelligence_engine(
        db_path=db_path,
        regime_label="markdown-regime",
        report_label="markdown-report",
        dataset_label="dataset-1",
        symbols="BTCUSDT",
    )

    assert "# DeltaGrid Mission 60" in result["markdown_report"]
    assert "Live trading remains disabled." in result["markdown_report"]
    assert "No paid APIs were used." in result["markdown_report"]
