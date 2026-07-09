import sqlite3

from offchain.research.multi_strategy_research_factory import (
    FACTORY_READY,
    FACTORY_WATCHLIST_ONLY,
    CANDIDATE_PROMOTION_SHORTLIST,
    STRATEGY_FUNDING_BASIS,
    parse_symbols,
    run_multi_strategy_research_factory,
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


def insert_symbol_data(
    conn,
    dataset_label="dataset-1",
    symbol="BTCUSDT",
    funding_bps=0.5,
    basis_bps=-2.0,
    spread_bps=0.05,
    count=30,
):
    for i in range(count):
        value = funding_bps + (0.02 if i % 2 == 0 else -0.01)
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


def test_parse_symbols_deduplicates_and_uppercases():
    assert parse_symbols("btcusdt, ETHUSDT,btcusdt") == ["BTCUSDT", "ETHUSDT"]


def test_factory_creates_multi_strategy_candidates_and_persists(tmp_path):
    db_path = tmp_path / "mission59.db"

    with sqlite3.connect(db_path) as conn:
        create_market_tables(conn)
        insert_symbol_data(conn, symbol="BTCUSDT", funding_bps=0.7, basis_bps=-3.0, spread_bps=0.04)
        insert_symbol_data(conn, symbol="ETHUSDT", funding_bps=0.4, basis_bps=-2.0, spread_bps=0.05)
        conn.commit()

    result = run_multi_strategy_research_factory(
        db_path=db_path,
        factory_label="mission59-factory",
        report_label="mission59-report",
        dataset_label="dataset-1",
        symbols="BTCUSDT,ETHUSDT",
        lookback_records=30,
        min_funding_records=20,
        min_promotion_score=55.0,
        min_watchlist_score=20.0,
    )

    assert result["symbol_count"] == 2
    assert result["strategy_count"] == 5
    assert result["candidate_count"] == 10
    assert result["promotion_shortlist_count"] >= 1
    assert result["global_verdict"] == FACTORY_READY
    assert result["safety_breach_count"] == 0

    with sqlite3.connect(db_path) as conn:
        candidate_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM multi_strategy_research_candidates
            WHERE factory_label = ?
            """,
            ("mission59-factory",),
        ).fetchone()[0]

        report = conn.execute(
            """
            SELECT report_label, candidate_count, global_verdict
            FROM multi_strategy_research_factory_reports
            WHERE report_label = ?
            """,
            ("mission59-report",),
        ).fetchone()

    assert candidate_count == 10
    assert report == ("mission59-report", 10, FACTORY_READY)


def test_factory_handles_missing_data_without_crash(tmp_path):
    db_path = tmp_path / "mission59-missing.db"

    result = run_multi_strategy_research_factory(
        db_path=db_path,
        factory_label="missing-factory",
        report_label="missing-report",
        dataset_label="dataset-1",
        symbols="BTCUSDT",
    )

    assert result["symbol_count"] == 1
    assert result["candidate_count"] == 5
    assert result["data_insufficient_count"] == 5


def test_factory_can_return_watchlist_only(tmp_path):
    db_path = tmp_path / "mission59-watchlist.db"

    with sqlite3.connect(db_path) as conn:
        create_market_tables(conn)
        insert_symbol_data(conn, symbol="BTCUSDT", funding_bps=0.12, basis_bps=-1.0, spread_bps=0.1)
        conn.commit()

    result = run_multi_strategy_research_factory(
        db_path=db_path,
        factory_label="watchlist-factory",
        report_label="watchlist-report",
        dataset_label="dataset-1",
        symbols="BTCUSDT",
        min_promotion_score=95.0,
        min_watchlist_score=10.0,
    )

    assert result["global_verdict"] in {FACTORY_WATCHLIST_ONLY, FACTORY_READY}
    assert result["candidate_count"] == 5


def test_top_candidate_fields_are_present(tmp_path):
    db_path = tmp_path / "mission59-fields.db"

    with sqlite3.connect(db_path) as conn:
        create_market_tables(conn)
        insert_symbol_data(conn, symbol="BTCUSDT", funding_bps=0.8, basis_bps=-3.0, spread_bps=0.03)
        conn.commit()

    result = run_multi_strategy_research_factory(
        db_path=db_path,
        factory_label="fields-factory",
        report_label="fields-report",
        dataset_label="dataset-1",
        symbols="BTCUSDT",
        min_promotion_score=50.0,
    )

    top = result["top_candidates"][0]
    assert top["strategy_id"] in {
        STRATEGY_FUNDING_BASIS,
        "FUNDING_RATE_MOMENTUM",
        "BASIS_MEAN_REVERSION",
        "VOLATILITY_REGIME_FILTER",
        "CROSS_SYMBOL_RELATIVE_STRENGTH",
    }
    assert "alpha_score" in top
    assert "rejection_reason" in top
    assert top["live_trading"] == "DISABLED"
    assert top["capital_deployment"] == "BLOCKED"


def test_markdown_report_contains_shadow_safety_statement(tmp_path):
    db_path = tmp_path / "mission59-markdown.db"

    with sqlite3.connect(db_path) as conn:
        create_market_tables(conn)
        insert_symbol_data(conn, symbol="BTCUSDT")
        conn.commit()

    result = run_multi_strategy_research_factory(
        db_path=db_path,
        factory_label="markdown-factory",
        report_label="markdown-report",
        dataset_label="dataset-1",
        symbols="BTCUSDT",
    )

    assert "# DeltaGrid Mission 59" in result["markdown_report"]
    assert "Live trading remains disabled." in result["markdown_report"]
    assert "No paid APIs were used." in result["markdown_report"]
