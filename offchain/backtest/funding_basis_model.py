import argparse
import json
import os
import sqlite3
import sys
from decimal import Decimal, getcontext
from pathlib import Path

from dotenv import load_dotenv


getcontext().prec = 40

OFFCHAIN_ROOT = Path(__file__).resolve().parents[1]

if str(OFFCHAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(OFFCHAIN_ROOT))

from db.schema import init_market_database, utc_now


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")


def to_decimal(value):
    if value is None:
        return None

    return Decimal(str(value))


def resolve_db_path(db_path):
    path = Path(db_path)

    if path.is_absolute():
        return str(path)

    return str(OFFCHAIN_ROOT / db_path)


def annualize_funding_rate_pct(funding_rate, interval_hours):
    funding_rate = to_decimal(funding_rate)
    interval_hours = to_decimal(interval_hours)

    if interval_hours <= 0:
        raise ValueError("interval_hours must be positive")

    windows_per_day = Decimal("24") / interval_hours

    return funding_rate * windows_per_day * Decimal("365") * Decimal("100")


def basis_pct(spot_price, perp_mark_price):
    spot_price = to_decimal(spot_price)
    perp_mark_price = to_decimal(perp_mark_price)

    if spot_price <= 0:
        raise ValueError("spot_price must be positive")

    return (perp_mark_price - spot_price) / spot_price * Decimal("100")


def ensure_schema(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS funding_rates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exchange TEXT NOT NULL,
        symbol TEXT NOT NULL,
        funding_time_utc TEXT NOT NULL,
        funding_rate TEXT NOT NULL,
        interval_hours TEXT NOT NULL,
        annualized_rate_pct TEXT NOT NULL,
        source TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        UNIQUE(exchange, symbol, funding_time_utc, source)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS perp_mark_prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exchange TEXT NOT NULL,
        symbol TEXT NOT NULL,
        timestamp_utc TEXT NOT NULL,
        mark_price TEXT NOT NULL,
        index_price TEXT NOT NULL,
        open_interest TEXT,
        source TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        UNIQUE(exchange, symbol, timestamp_utc, source)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS spot_perp_basis_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        spot_exchange TEXT NOT NULL,
        perp_exchange TEXT NOT NULL,
        symbol TEXT NOT NULL,
        timestamp_utc TEXT NOT NULL,
        spot_price TEXT NOT NULL,
        perp_mark_price TEXT NOT NULL,
        basis_pct TEXT NOT NULL,
        annualized_funding_rate_pct TEXT NOT NULL,
        open_interest TEXT,
        source TEXT NOT NULL,
        verdict TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS delta_neutral_research_candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        timestamp_utc TEXT NOT NULL,
        spot_exchange TEXT NOT NULL,
        perp_exchange TEXT NOT NULL,
        funding_rate TEXT NOT NULL,
        annualized_funding_rate_pct TEXT NOT NULL,
        basis_pct TEXT NOT NULL,
        expected_edge_pct TEXT NOT NULL,
        verdict TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def upsert_funding_rate(
    db_path,
    exchange,
    symbol,
    funding_time_utc,
    funding_rate,
    interval_hours,
    source,
):
    annualized = annualize_funding_rate_pct(funding_rate, interval_hours)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO funding_rates (
        exchange,
        symbol,
        funding_time_utc,
        funding_rate,
        interval_hours,
        annualized_rate_pct,
        source,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(exchange, symbol, funding_time_utc, source)
    DO UPDATE SET
        funding_rate = excluded.funding_rate,
        interval_hours = excluded.interval_hours,
        annualized_rate_pct = excluded.annualized_rate_pct
    """, (
        exchange,
        symbol.upper(),
        funding_time_utc,
        format(to_decimal(funding_rate), "f"),
        format(to_decimal(interval_hours), "f"),
        format(annualized, "f"),
        source,
        utc_now(),
    ))

    row_id = cur.execute("""
    SELECT id
    FROM funding_rates
    WHERE exchange = ?
    AND symbol = ?
    AND funding_time_utc = ?
    AND source = ?
    """, (
        exchange,
        symbol.upper(),
        funding_time_utc,
        source,
    )).fetchone()[0]

    conn.commit()
    conn.close()

    return int(row_id)


def upsert_perp_mark_price(
    db_path,
    exchange,
    symbol,
    timestamp_utc,
    mark_price,
    index_price,
    open_interest,
    source,
):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO perp_mark_prices (
        exchange,
        symbol,
        timestamp_utc,
        mark_price,
        index_price,
        open_interest,
        source,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(exchange, symbol, timestamp_utc, source)
    DO UPDATE SET
        mark_price = excluded.mark_price,
        index_price = excluded.index_price,
        open_interest = excluded.open_interest
    """, (
        exchange,
        symbol.upper(),
        timestamp_utc,
        format(to_decimal(mark_price), "f"),
        format(to_decimal(index_price), "f"),
        None if open_interest is None else format(to_decimal(open_interest), "f"),
        source,
        utc_now(),
    ))

    row_id = cur.execute("""
    SELECT id
    FROM perp_mark_prices
    WHERE exchange = ?
    AND symbol = ?
    AND timestamp_utc = ?
    AND source = ?
    """, (
        exchange,
        symbol.upper(),
        timestamp_utc,
        source,
    )).fetchone()[0]

    conn.commit()
    conn.close()

    return int(row_id)


def classify_basis_snapshot(annualized_rate_pct, basis_value_pct):
    annualized_rate_pct = to_decimal(annualized_rate_pct)
    basis_value_pct = to_decimal(basis_value_pct)

    if annualized_rate_pct >= Decimal("15") and Decimal("-0.30") <= basis_value_pct <= Decimal("2.00"):
        return "DELTA_NEUTRAL_CANDIDATE"

    if annualized_rate_pct < Decimal("5"):
        return "IGNORE_LOW_FUNDING"

    return "OBSERVE_ONLY"


def insert_basis_snapshot(
    db_path,
    spot_exchange,
    perp_exchange,
    symbol,
    timestamp_utc,
    spot_price,
    perp_mark_price,
    annualized_funding_rate_pct,
    open_interest,
    source,
    assumptions,
):
    basis_value = basis_pct(spot_price, perp_mark_price)
    verdict = classify_basis_snapshot(annualized_funding_rate_pct, basis_value)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO spot_perp_basis_snapshots (
        spot_exchange,
        perp_exchange,
        symbol,
        timestamp_utc,
        spot_price,
        perp_mark_price,
        basis_pct,
        annualized_funding_rate_pct,
        open_interest,
        source,
        verdict,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        spot_exchange,
        perp_exchange,
        symbol.upper(),
        timestamp_utc,
        format(to_decimal(spot_price), "f"),
        format(to_decimal(perp_mark_price), "f"),
        format(basis_value, "f"),
        format(to_decimal(annualized_funding_rate_pct), "f"),
        None if open_interest is None else format(to_decimal(open_interest), "f"),
        source,
        verdict,
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def evaluate_delta_neutral_candidate(
    funding_rate,
    annualized_funding_rate_pct,
    basis_value_pct,
    open_interest,
    min_annualized_rate_pct=Decimal("15"),
    min_basis_pct=Decimal("-0.30"),
    max_basis_pct=Decimal("2.00"),
    min_expected_edge_pct=Decimal("10"),
):
    annualized_funding_rate_pct = to_decimal(annualized_funding_rate_pct)
    basis_value_pct = to_decimal(basis_value_pct)

    basis_penalty = max(basis_value_pct, Decimal("0")) * Decimal("0.25")
    expected_edge_pct = annualized_funding_rate_pct - basis_penalty

    checks = {
        "funding_ok": annualized_funding_rate_pct >= min_annualized_rate_pct,
        "basis_ok": min_basis_pct <= basis_value_pct <= max_basis_pct,
        "open_interest_ok": open_interest is not None and to_decimal(open_interest) > 0,
        "expected_edge_ok": expected_edge_pct >= min_expected_edge_pct,
    }

    if all(checks.values()):
        verdict = "GO_FOR_RESEARCH"
        recommended_action = "LONG_SPOT_SHORT_PERP_RESEARCH"
    elif not checks["funding_ok"]:
        verdict = "NO_GO_LOW_FUNDING"
        recommended_action = "IGNORE_UNTIL_FUNDING_EXPANDS"
    elif not checks["basis_ok"]:
        verdict = "NO_GO_BASIS_OUT_OF_RANGE"
        recommended_action = "WAIT_FOR_BASIS_NORMALIZATION"
    elif not checks["open_interest_ok"]:
        verdict = "NO_GO_MISSING_OPEN_INTEREST"
        recommended_action = "COLLECT_MORE_DATA"
    else:
        verdict = "OBSERVE_ONLY"
        recommended_action = "KEEP_MONITORING"

    return {
        "funding_rate": format(to_decimal(funding_rate), "f"),
        "annualized_funding_rate_pct": annualized_funding_rate_pct,
        "basis_pct": basis_value_pct,
        "expected_edge_pct": expected_edge_pct,
        "verdict": verdict,
        "recommended_action": recommended_action,
        "checks": checks,
    }


def insert_delta_neutral_candidate(
    db_path,
    symbol,
    timestamp_utc,
    spot_exchange,
    perp_exchange,
    funding_rate,
    annualized_funding_rate_pct,
    basis_value_pct,
    open_interest,
    assumptions,
):
    evaluation = evaluate_delta_neutral_candidate(
        funding_rate=funding_rate,
        annualized_funding_rate_pct=annualized_funding_rate_pct,
        basis_value_pct=basis_value_pct,
        open_interest=open_interest,
    )

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO delta_neutral_research_candidates (
        symbol,
        timestamp_utc,
        spot_exchange,
        perp_exchange,
        funding_rate,
        annualized_funding_rate_pct,
        basis_pct,
        expected_edge_pct,
        verdict,
        recommended_action,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        symbol.upper(),
        timestamp_utc,
        spot_exchange,
        perp_exchange,
        format(to_decimal(funding_rate), "f"),
        format(evaluation["annualized_funding_rate_pct"], "f"),
        format(evaluation["basis_pct"], "f"),
        format(evaluation["expected_edge_pct"], "f"),
        evaluation["verdict"],
        evaluation["recommended_action"],
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def table_count(db_path, table_name, source=None):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    if source is None:
        count = cur.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    else:
        count = cur.execute(
            f"SELECT COUNT(*) FROM {table_name} WHERE source = ?",
            (source,),
        ).fetchone()[0]

    conn.close()

    return int(count)


def run_demo_seed(db_path, run_label):
    db_path = resolve_db_path(db_path)

    init_market_database(db_path)
    ensure_schema(db_path)

    timestamp = "2026-07-08T00:00:00Z"
    symbol = "ETHUSDT"
    funding_rate = Decimal("0.0002")
    interval_hours = Decimal("8")
    spot_price = Decimal("3100")
    perp_mark_price = Decimal("3106.20")
    open_interest = Decimal("100000000")

    annualized = annualize_funding_rate_pct(funding_rate, interval_hours)
    basis_value = basis_pct(spot_price, perp_mark_price)

    assumptions = {
        "research_only": True,
        "no_private_keys": True,
        "no_signing": True,
        "no_real_trades": True,
        "funding_rate_source": "synthetic_demo",
        "purpose": "mission_22_data_model_verification",
    }

    funding_id = upsert_funding_rate(
        db_path=db_path,
        exchange="Binance Futures",
        symbol=symbol,
        funding_time_utc=timestamp,
        funding_rate=funding_rate,
        interval_hours=interval_hours,
        source=run_label,
    )

    mark_id = upsert_perp_mark_price(
        db_path=db_path,
        exchange="Binance Futures",
        symbol=symbol,
        timestamp_utc=timestamp,
        mark_price=perp_mark_price,
        index_price=spot_price,
        open_interest=open_interest,
        source=run_label,
    )

    basis_id = insert_basis_snapshot(
        db_path=db_path,
        spot_exchange="Binance Spot",
        perp_exchange="Binance Futures",
        symbol=symbol,
        timestamp_utc=timestamp,
        spot_price=spot_price,
        perp_mark_price=perp_mark_price,
        annualized_funding_rate_pct=annualized,
        open_interest=open_interest,
        source=run_label,
        assumptions=assumptions,
    )

    candidate_id = insert_delta_neutral_candidate(
        db_path=db_path,
        symbol=symbol,
        timestamp_utc=timestamp,
        spot_exchange="Binance Spot",
        perp_exchange="Binance Futures",
        funding_rate=funding_rate,
        annualized_funding_rate_pct=annualized,
        basis_value_pct=basis_value,
        open_interest=open_interest,
        assumptions=assumptions,
    )

    return {
        "run_label": run_label,
        "symbol": symbol,
        "funding_id": funding_id,
        "mark_id": mark_id,
        "basis_id": basis_id,
        "candidate_id": candidate_id,
        "annualized_funding_rate_pct": format(annualized, "f"),
        "basis_pct": format(basis_value, "f"),
        "funding_rates": table_count(db_path, "funding_rates", run_label),
        "perp_mark_prices": table_count(db_path, "perp_mark_prices", run_label),
        "spot_perp_basis_snapshots": table_count(db_path, "spot_perp_basis_snapshots", run_label),
        "delta_neutral_research_candidates": table_count(db_path, "delta_neutral_research_candidates"),
        "global_verdict": "DATA_MODEL_READY_NO_LIVE_TRADING",
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--run-label", default="mission_22_funding_basis_model")
    parser.add_argument("--demo", action="store_true")

    args = parser.parse_args()

    print("DeltaGrid Funding / Basis Data Model")
    print("Mode: research-only")
    print("No private keys. No signing. No real trades.")

    db_path = resolve_db_path(args.db_path)

    init_market_database(db_path)
    ensure_schema(db_path)

    if args.demo:
        result = run_demo_seed(
            db_path=args.db_path,
            run_label=args.run_label,
        )
    else:
        result = {
            "db_path": db_path,
            "schema_ready": True,
            "global_verdict": "SCHEMA_READY_NO_LIVE_TRADING",
        }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
