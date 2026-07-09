"""
Mission 60: Data Quality and Regime Intelligence Engine.

This module scores public market data quality and classifies symbol regimes.

It reads:
- historical_public_funding_rates
- historical_public_basis_observations
- multi_strategy_research_candidates, when a factory label is supplied

It writes:
- data_quality_regime_symbol_reports
- data_quality_strategy_candidate_gates
- data_quality_regime_intelligence_reports

It is a research and risk-intelligence layer only.

It never:
- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FUNDING_TABLE = "historical_public_funding_rates"
BASIS_TABLE = "historical_public_basis_observations"
M59_CANDIDATES_TABLE = "multi_strategy_research_candidates"

SYMBOL_REPORTS_TABLE = "data_quality_regime_symbol_reports"
CANDIDATE_GATES_TABLE = "data_quality_strategy_candidate_gates"
REGIME_REPORTS_TABLE = "data_quality_regime_intelligence_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

CONFIDENCE_HIGH = "DATA_CONFIDENCE_HIGH"
CONFIDENCE_MEDIUM = "DATA_CONFIDENCE_MEDIUM"
CONFIDENCE_LOW = "DATA_CONFIDENCE_LOW"

FUNDING_POSITIVE = "FUNDING_REGIME_POSITIVE_CARRY"
FUNDING_MIXED = "FUNDING_REGIME_MIXED"
FUNDING_NEGATIVE = "FUNDING_REGIME_NEGATIVE_CARRY"

VOL_LOW = "VOLATILITY_REGIME_LOW"
VOL_MODERATE = "VOLATILITY_REGIME_MODERATE"
VOL_HIGH = "VOLATILITY_REGIME_HIGH"

LIQ_TIGHT = "LIQUIDITY_REGIME_TIGHT_SPREAD"
LIQ_ACCEPTABLE = "LIQUIDITY_REGIME_ACCEPTABLE_SPREAD"
LIQ_WIDE = "LIQUIDITY_REGIME_WIDE_SPREAD"

BASIS_DISCOUNT = "BASIS_REGIME_PERP_DISCOUNT"
BASIS_NEUTRAL = "BASIS_REGIME_NEUTRAL"
BASIS_PREMIUM = "BASIS_REGIME_PERP_PREMIUM"

RISK_NORMAL = "MARKET_RISK_STATE_NORMAL"
RISK_CAUTION = "MARKET_RISK_STATE_CAUTION"
RISK_DANGER = "MARKET_RISK_STATE_DANGER"

SYMBOL_USE = "SYMBOL_RESEARCH_USABLE"
SYMBOL_WATCH = "SYMBOL_RESEARCH_WATCHLIST_ONLY"
SYMBOL_EXCLUDE = "SYMBOL_RESEARCH_EXCLUDED_BY_DATA_QUALITY"

GATE_PASS = "CANDIDATE_GATE_PASS_RESEARCH_REVIEW"
GATE_WATCH = "CANDIDATE_GATE_WATCHLIST_ONLY_BY_REGIME"
GATE_BLOCK = "CANDIDATE_GATE_BLOCK_PROMOTION_BY_REGIME"
GATE_SAFETY = "CANDIDATE_GATE_SAFETY_BLOCKED"

REPORT_READY = "DATA_QUALITY_REGIME_READY_SHADOW_ONLY"
REPORT_CAUTION = "DATA_QUALITY_REGIME_CAUTION_SHADOW_ONLY"
REPORT_DANGER = "DATA_QUALITY_REGIME_DANGER_SHADOW_ONLY"
REPORT_MISSING = "DATA_QUALITY_REGIME_DATA_MISSING"
REPORT_SAFETY = "DATA_QUALITY_REGIME_SAFETY_BREACH_BLOCKED"

ACTION_USE = "USE_NORMAL_REGIME_SYMBOLS_FOR_SHADOW_RESEARCH"
ACTION_FILTER = "APPLY_REGIME_FILTERS_BEFORE_PROMOTION_REVIEW"
ACTION_REFRESH = "REFRESH_PUBLIC_DATA_AND_RERUN_REGIME_ENGINE"
ACTION_STOP = "STOP_AND_REVIEW_REGIME_SAFETY_STATE"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_regime_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission60-regime-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission60-report-{stamp}-{uuid.uuid4().hex[:8]}"


def safe_float(value: Any) -> float:
    try:
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return 0.0
        return number
    except (TypeError, ValueError):
        return 0.0


def safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def round8(value: float) -> float:
    return round(float(value), 8)


def parse_symbols(value: str | list[str] | tuple[str, ...] | None) -> list[str] | None:
    if value is None:
        return None

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    symbols: list[str] = []

    for item in raw_items:
        symbol = str(item).strip().upper()

        if not symbol:
            continue

        if not symbol.endswith("USDT"):
            raise ValueError(f"Only USDT perpetual symbols are supported for Mission 60: {symbol}")

        if not symbol.replace("_", "").isalnum():
            raise ValueError(f"Invalid symbol: {symbol}")

        if symbol not in symbols:
            symbols.append(symbol)

    if not symbols:
        raise ValueError("At least one symbol is required when symbols are supplied")

    return symbols


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        AND name = ?
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def ensure_schema(db_path: str | Path) -> None:
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS data_quality_regime_symbol_reports (
                symbol_report_id TEXT PRIMARY KEY,
                regime_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_dataset_label TEXT NOT NULL,
                symbol TEXT NOT NULL,
                funding_record_count INTEGER NOT NULL,
                basis_observation_count INTEGER NOT NULL,
                missing_funding_count INTEGER NOT NULL,
                outlier_count INTEGER NOT NULL,
                outlier_ratio TEXT NOT NULL,
                average_funding_bps TEXT NOT NULL,
                latest_funding_bps TEXT NOT NULL,
                funding_positive_ratio TEXT NOT NULL,
                funding_volatility_bps TEXT NOT NULL,
                latest_basis_bps TEXT NOT NULL,
                latest_spread_bps TEXT NOT NULL,
                data_quality_score TEXT NOT NULL,
                data_confidence TEXT NOT NULL,
                funding_regime TEXT NOT NULL,
                volatility_regime TEXT NOT NULL,
                liquidity_regime TEXT NOT NULL,
                basis_regime TEXT NOT NULL,
                market_risk_state TEXT NOT NULL,
                recommended_symbol_action TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS data_quality_strategy_candidate_gates (
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

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS data_quality_regime_intelligence_reports (
                report_label TEXT PRIMARY KEY,
                regime_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_dataset_label TEXT NOT NULL,
                source_factory_label TEXT,
                requested_symbol_count INTEGER NOT NULL,
                symbol_count INTEGER NOT NULL,
                high_confidence_count INTEGER NOT NULL,
                medium_confidence_count INTEGER NOT NULL,
                low_confidence_count INTEGER NOT NULL,
                normal_risk_count INTEGER NOT NULL,
                caution_risk_count INTEGER NOT NULL,
                danger_risk_count INTEGER NOT NULL,
                candidate_gate_count INTEGER NOT NULL,
                pass_gate_count INTEGER NOT NULL,
                watch_gate_count INTEGER NOT NULL,
                block_gate_count INTEGER NOT NULL,
                safety_gate_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                top_symbol TEXT,
                weakest_symbol TEXT,
                average_data_quality_score TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.commit()


def load_funding_rows(
    conn: sqlite3.Connection,
    dataset_label: str,
    symbols: list[str] | None,
    lookback_records: int,
) -> dict[str, list[sqlite3.Row]]:
    if not table_exists(conn, FUNDING_TABLE):
        return {}

    params: list[Any] = [dataset_label]
    symbol_clause = ""

    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        symbol_clause = f" AND symbol IN ({placeholders})"
        params.extend(symbols)

    query = f"""
        SELECT *
        FROM historical_public_funding_rates
        WHERE dataset_label = ?
        {symbol_clause}
        ORDER BY symbol ASC, funding_time DESC
    """

    rows = conn.execute(query, params).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)

    for row in rows:
        symbol = str(row["symbol"])
        if len(grouped[symbol]) < lookback_records:
            grouped[symbol].append(row)

    return grouped


def load_basis_rows(
    conn: sqlite3.Connection,
    dataset_label: str,
    symbols: list[str] | None,
) -> dict[str, list[sqlite3.Row]]:
    if not table_exists(conn, BASIS_TABLE):
        return {}

    params: list[Any] = [dataset_label]
    symbol_clause = ""

    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        symbol_clause = f" AND symbol IN ({placeholders})"
        params.extend(symbols)

    query = f"""
        SELECT *
        FROM historical_public_basis_observations
        WHERE dataset_label = ?
        {symbol_clause}
        ORDER BY symbol ASC, created_at DESC
    """

    rows = conn.execute(query, params).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)

    for row in rows:
        grouped[str(row["symbol"])].append(row)

    return grouped


def detect_outliers(values: list[float]) -> tuple[int, float]:
    if len(values) < 4:
        return 0, 0.0

    median = statistics.median(values)
    deviations = [abs(value - median) for value in values]
    mad = statistics.median(deviations)

    if mad == 0:
        mean = statistics.mean(values)
        stdev = statistics.pstdev(values)
        if stdev == 0:
            return 0, 0.0
        outlier_count = sum(1 for value in values if abs(value - mean) > 3 * stdev)
    else:
        outlier_count = sum(1 for value in values if abs(value - median) / mad > 6)

    return outlier_count, round8(outlier_count / len(values))


def funding_stats(rows: list[sqlite3.Row]) -> dict[str, float]:
    values = [safe_float(row["funding_rate_bps"]) for row in rows]
    missing = sum(1 for row in rows if str(row["funding_rate_bps"]).strip() == "")

    if not values:
        return {
            "funding_record_count": 0,
            "missing_funding_count": missing,
            "outlier_count": 0,
            "outlier_ratio": 0.0,
            "average_funding_bps": 0.0,
            "latest_funding_bps": 0.0,
            "funding_positive_ratio": 0.0,
            "funding_volatility_bps": 0.0,
        }

    outlier_count, outlier_ratio = detect_outliers(values)

    return {
        "funding_record_count": len(values),
        "missing_funding_count": missing,
        "outlier_count": outlier_count,
        "outlier_ratio": outlier_ratio,
        "average_funding_bps": round8(statistics.mean(values)),
        "latest_funding_bps": round8(values[0]),
        "funding_positive_ratio": round8(sum(1 for value in values if value > 0) / len(values)),
        "funding_volatility_bps": round8(statistics.pstdev(values) if len(values) > 1 else 0.0),
    }


def basis_stats(rows: list[sqlite3.Row]) -> dict[str, float]:
    if not rows:
        return {
            "basis_observation_count": 0,
            "latest_basis_bps": 0.0,
            "latest_spread_bps": 999.0,
        }

    latest = rows[0]

    return {
        "basis_observation_count": len(rows),
        "latest_basis_bps": round8(safe_float(latest["basis_bps"])),
        "latest_spread_bps": round8(safe_float(latest["spread_bps"])),
    }


def classify_confidence(score: float) -> str:
    if score >= 80:
        return CONFIDENCE_HIGH
    if score >= 50:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def classify_funding(metrics: dict[str, float]) -> str:
    average = metrics["average_funding_bps"]
    ratio = metrics["funding_positive_ratio"]

    if average > 0.1 and ratio >= 0.6:
        return FUNDING_POSITIVE

    if average < -0.05 and ratio < 0.5:
        return FUNDING_NEGATIVE

    return FUNDING_MIXED


def classify_volatility(volatility_bps: float) -> str:
    if volatility_bps <= 0.5:
        return VOL_LOW
    if volatility_bps <= 1.0:
        return VOL_MODERATE
    return VOL_HIGH


def classify_liquidity(spread_bps: float, max_acceptable_spread_bps: float) -> str:
    if spread_bps <= min(0.1, max_acceptable_spread_bps):
        return LIQ_TIGHT

    if spread_bps <= max_acceptable_spread_bps:
        return LIQ_ACCEPTABLE

    return LIQ_WIDE


def classify_basis(basis_bps: float) -> str:
    if basis_bps <= -1.0:
        return BASIS_DISCOUNT

    if basis_bps >= 1.0:
        return BASIS_PREMIUM

    return BASIS_NEUTRAL


def quality_score(
    metrics: dict[str, float],
    min_funding_records: int,
    max_acceptable_spread_bps: float,
) -> float:
    funding_records = metrics["funding_record_count"]
    basis_count = metrics["basis_observation_count"]
    spread = metrics["latest_spread_bps"]
    outlier_ratio = metrics["outlier_ratio"]

    funding_component = min(55.0, (funding_records / max(1, min_funding_records)) * 55.0)
    basis_component = 20.0 if basis_count > 0 else 0.0

    if spread <= 0.1:
        spread_component = 20.0
    elif spread <= max_acceptable_spread_bps:
        spread_component = 14.0
    elif spread <= max_acceptable_spread_bps * 1.5:
        spread_component = 7.0
    else:
        spread_component = 0.0

    outlier_penalty = min(25.0, outlier_ratio * 100.0)

    return round8(max(0.0, min(100.0, funding_component + basis_component + spread_component - outlier_penalty)))


def classify_risk(
    data_quality_score: float,
    volatility_regime: str,
    liquidity_regime: str,
    outlier_ratio: float,
) -> str:
    if data_quality_score < 50:
        return RISK_DANGER

    if liquidity_regime == LIQ_WIDE and data_quality_score < 75:
        return RISK_DANGER

    if volatility_regime == VOL_HIGH:
        return RISK_DANGER

    if outlier_ratio > 0.2:
        return RISK_DANGER

    if data_quality_score < 80:
        return RISK_CAUTION

    if liquidity_regime == LIQ_WIDE:
        return RISK_CAUTION

    if volatility_regime == VOL_MODERATE:
        return RISK_CAUTION

    if outlier_ratio > 0:
        return RISK_CAUTION

    return RISK_NORMAL


def symbol_action(market_risk_state: str, data_confidence: str) -> str:
    if market_risk_state == RISK_DANGER or data_confidence == CONFIDENCE_LOW:
        return SYMBOL_EXCLUDE

    if market_risk_state == RISK_CAUTION or data_confidence == CONFIDENCE_MEDIUM:
        return SYMBOL_WATCH

    return SYMBOL_USE


def build_symbol_report(
    regime_label: str,
    created_at: str,
    dataset_label: str,
    symbol: str,
    funding_rows: list[sqlite3.Row],
    basis_rows: list[sqlite3.Row],
    min_funding_records: int,
    max_acceptable_spread_bps: float,
) -> dict[str, Any]:
    metrics = {**funding_stats(funding_rows), **basis_stats(basis_rows)}
    score = quality_score(metrics, min_funding_records, max_acceptable_spread_bps)

    confidence = classify_confidence(score)
    funding_regime = classify_funding(metrics)
    volatility_regime = classify_volatility(metrics["funding_volatility_bps"])
    liquidity_regime = classify_liquidity(metrics["latest_spread_bps"], max_acceptable_spread_bps)
    basis_regime = classify_basis(metrics["latest_basis_bps"])
    market_risk_state = classify_risk(
        data_quality_score=score,
        volatility_regime=volatility_regime,
        liquidity_regime=liquidity_regime,
        outlier_ratio=metrics["outlier_ratio"],
    )
    action = symbol_action(market_risk_state, confidence)

    return {
        "symbol_report_id": f"{regime_label}-{symbol}",
        "regime_label": regime_label,
        "created_at": created_at,
        "source_dataset_label": dataset_label,
        "symbol": symbol,
        "funding_record_count": int(metrics["funding_record_count"]),
        "basis_observation_count": int(metrics["basis_observation_count"]),
        "missing_funding_count": int(metrics["missing_funding_count"]),
        "outlier_count": int(metrics["outlier_count"]),
        "outlier_ratio": round8(metrics["outlier_ratio"]),
        "average_funding_bps": round8(metrics["average_funding_bps"]),
        "latest_funding_bps": round8(metrics["latest_funding_bps"]),
        "funding_positive_ratio": round8(metrics["funding_positive_ratio"]),
        "funding_volatility_bps": round8(metrics["funding_volatility_bps"]),
        "latest_basis_bps": round8(metrics["latest_basis_bps"]),
        "latest_spread_bps": round8(metrics["latest_spread_bps"]),
        "data_quality_score": score,
        "data_confidence": confidence,
        "funding_regime": funding_regime,
        "volatility_regime": volatility_regime,
        "liquidity_regime": liquidity_regime,
        "basis_regime": basis_regime,
        "market_risk_state": market_risk_state,
        "recommended_symbol_action": action,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "research_role": "DATA_QUALITY_AND_REGIME_INTELLIGENCE_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
        },
    }


def build_symbol_reports(
    regime_label: str,
    created_at: str,
    dataset_label: str,
    funding_by_symbol: dict[str, list[sqlite3.Row]],
    basis_by_symbol: dict[str, list[sqlite3.Row]],
    requested_symbols: list[str] | None,
    min_funding_records: int,
    max_acceptable_spread_bps: float,
) -> list[dict[str, Any]]:
    universe = set(funding_by_symbol.keys()) | set(basis_by_symbol.keys())

    if requested_symbols:
        universe = set(requested_symbols)

    reports = []

    for symbol in sorted(universe):
        reports.append(
            build_symbol_report(
                regime_label=regime_label,
                created_at=created_at,
                dataset_label=dataset_label,
                symbol=symbol,
                funding_rows=funding_by_symbol.get(symbol, []),
                basis_rows=basis_by_symbol.get(symbol, []),
                min_funding_records=min_funding_records,
                max_acceptable_spread_bps=max_acceptable_spread_bps,
            )
        )

    reports.sort(
        key=lambda item: (
            item["market_risk_state"] == RISK_NORMAL,
            item["data_quality_score"],
            -item["latest_spread_bps"],
        ),
        reverse=True,
    )

    return reports


def load_strategy_candidates(
    conn: sqlite3.Connection,
    factory_label: str | None,
    symbols: list[str] | None,
) -> list[sqlite3.Row]:
    if not factory_label:
        return []

    if not table_exists(conn, M59_CANDIDATES_TABLE):
        return []

    params: list[Any] = [factory_label]
    symbol_clause = ""

    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        symbol_clause = f" AND symbol IN ({placeholders})"
        params.extend(symbols)

    query = f"""
        SELECT
            candidate_id,
            factory_label,
            strategy_id,
            symbol,
            candidate_status,
            promotion_eligible,
            alpha_score,
            live_trading,
            live_order_sent,
            capital_deployment
        FROM multi_strategy_research_candidates
        WHERE factory_label = ?
        {symbol_clause}
        ORDER BY CAST(alpha_score AS REAL) DESC
    """

    return conn.execute(query, params).fetchall()


def gate_candidate(
    regime_label: str,
    created_at: str,
    candidate: sqlite3.Row,
    symbol_report_by_symbol: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    symbol = str(candidate["symbol"])
    symbol_report = symbol_report_by_symbol.get(symbol)

    if symbol_report is None:
        market_risk_state = RISK_DANGER
        data_quality = 0.0
        gate_status = GATE_BLOCK
        reason = "No regime report exists for this candidate symbol."
    else:
        market_risk_state = symbol_report["market_risk_state"]
        data_quality = symbol_report["data_quality_score"]

        if market_risk_state == RISK_DANGER or data_quality < 50:
            gate_status = GATE_BLOCK
            reason = "Candidate blocked by dangerous data or market regime."
        elif market_risk_state == RISK_CAUTION or data_quality < 80:
            gate_status = GATE_WATCH
            reason = "Candidate limited to watchlist by caution regime."
        else:
            gate_status = GATE_PASS
            reason = "Candidate passes data quality and regime gate."

    safety_problem = (
        str(candidate["live_trading"]) != LIVE_TRADING_STATUS
        or safe_int(candidate["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
        or str(candidate["capital_deployment"]) != CAPITAL_DEPLOYMENT_STATUS
    )

    if safety_problem:
        gate_status = GATE_SAFETY
        reason = "Candidate has a safety invariant breach."

    return {
        "gate_id": f"{regime_label}-{candidate['candidate_id']}",
        "regime_label": regime_label,
        "created_at": created_at,
        "source_factory_label": str(candidate["factory_label"]),
        "source_candidate_id": str(candidate["candidate_id"]),
        "strategy_id": str(candidate["strategy_id"]),
        "symbol": symbol,
        "candidate_status": str(candidate["candidate_status"]),
        "promotion_eligible": safe_int(candidate["promotion_eligible"]),
        "alpha_score": round8(safe_float(candidate["alpha_score"])),
        "market_risk_state": market_risk_state,
        "data_quality_score": round8(data_quality),
        "candidate_gate_status": gate_status,
        "gate_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "research_role": "DATA_QUALITY_CANDIDATE_REGIME_GATE_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
        },
    }


def build_candidate_gates(
    regime_label: str,
    created_at: str,
    candidates: list[sqlite3.Row],
    symbol_reports: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_symbol = {report["symbol"]: report for report in symbol_reports}
    gates = [gate_candidate(regime_label, created_at, candidate, by_symbol) for candidate in candidates]

    gates.sort(
        key=lambda item: (
            item["candidate_gate_status"] == GATE_PASS,
            item["alpha_score"],
        ),
        reverse=True,
    )

    return gates


def safety_breach_count(symbol_reports: list[dict[str, Any]], gates: list[dict[str, Any]]) -> int:
    count = 0

    for row in [*symbol_reports, *gates]:
        if row["live_trading"] != LIVE_TRADING_STATUS:
            count += 1
        if safe_int(row["live_order_sent"]) != LIVE_ORDER_SENT_VALUE:
            count += 1
        if row["capital_deployment"] != CAPITAL_DEPLOYMENT_STATUS:
            count += 1

    return count


def persist_symbol_reports(db_path: str | Path, symbol_reports: list[dict[str, Any]]) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for report in symbol_reports:
            conn.execute(
                """
                INSERT OR REPLACE INTO data_quality_regime_symbol_reports (
                    symbol_report_id,
                    regime_label,
                    created_at,
                    source_dataset_label,
                    symbol,
                    funding_record_count,
                    basis_observation_count,
                    missing_funding_count,
                    outlier_count,
                    outlier_ratio,
                    average_funding_bps,
                    latest_funding_bps,
                    funding_positive_ratio,
                    funding_volatility_bps,
                    latest_basis_bps,
                    latest_spread_bps,
                    data_quality_score,
                    data_confidence,
                    funding_regime,
                    volatility_regime,
                    liquidity_regime,
                    basis_regime,
                    market_risk_state,
                    recommended_symbol_action,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report["symbol_report_id"],
                    report["regime_label"],
                    report["created_at"],
                    report["source_dataset_label"],
                    report["symbol"],
                    report["funding_record_count"],
                    report["basis_observation_count"],
                    report["missing_funding_count"],
                    report["outlier_count"],
                    str(report["outlier_ratio"]),
                    str(report["average_funding_bps"]),
                    str(report["latest_funding_bps"]),
                    str(report["funding_positive_ratio"]),
                    str(report["funding_volatility_bps"]),
                    str(report["latest_basis_bps"]),
                    str(report["latest_spread_bps"]),
                    str(report["data_quality_score"]),
                    report["data_confidence"],
                    report["funding_regime"],
                    report["volatility_regime"],
                    report["liquidity_regime"],
                    report["basis_regime"],
                    report["market_risk_state"],
                    report["recommended_symbol_action"],
                    report["live_trading"],
                    report["live_order_sent"],
                    report["capital_deployment"],
                    json.dumps(report["metadata"], sort_keys=True),
                ),
            )

        conn.commit()


def persist_candidate_gates(db_path: str | Path, gates: list[dict[str, Any]]) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for gate in gates:
            conn.execute(
                """
                INSERT OR REPLACE INTO data_quality_strategy_candidate_gates (
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
                    gate["gate_id"],
                    gate["regime_label"],
                    gate["created_at"],
                    gate["source_factory_label"],
                    gate["source_candidate_id"],
                    gate["strategy_id"],
                    gate["symbol"],
                    gate["candidate_status"],
                    gate["promotion_eligible"],
                    str(gate["alpha_score"]),
                    gate["market_risk_state"],
                    str(gate["data_quality_score"]),
                    gate["candidate_gate_status"],
                    gate["gate_reason"],
                    gate["live_trading"],
                    gate["live_order_sent"],
                    gate["capital_deployment"],
                    json.dumps(gate["metadata"], sort_keys=True),
                ),
            )

        conn.commit()


def summarize_engine(
    db_path: str | Path,
    regime_label: str,
    report_label: str,
    created_at: str,
    dataset_label: str,
    factory_label: str | None,
    requested_symbols: list[str] | None,
    symbol_reports: list[dict[str, Any]],
    gates: list[dict[str, Any]],
) -> dict[str, Any]:
    confidence_counts = Counter(report["data_confidence"] for report in symbol_reports)
    risk_counts = Counter(report["market_risk_state"] for report in symbol_reports)
    gate_counts = Counter(gate["candidate_gate_status"] for gate in gates)

    scores = [report["data_quality_score"] for report in symbol_reports]
    average_score = round8(statistics.mean(scores)) if scores else 0.0

    top_report = max(symbol_reports, key=lambda item: item["data_quality_score"], default=None)
    weakest_report = min(symbol_reports, key=lambda item: item["data_quality_score"], default=None)

    safety_count = safety_breach_count(symbol_reports, gates)

    if safety_count > 0 or gate_counts.get(GATE_SAFETY, 0) > 0:
        verdict = REPORT_SAFETY
        action = ACTION_STOP
    elif not symbol_reports:
        verdict = REPORT_MISSING
        action = ACTION_REFRESH
    elif risk_counts.get(RISK_DANGER, 0) > 0:
        verdict = REPORT_DANGER
        action = ACTION_FILTER
    elif risk_counts.get(RISK_CAUTION, 0) > 0:
        verdict = REPORT_CAUTION
        action = ACTION_FILTER
    else:
        verdict = REPORT_READY
        action = ACTION_USE

    return {
        "report_label": report_label,
        "regime_label": regime_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_dataset_label": dataset_label,
        "source_factory_label": factory_label,
        "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
        "symbol_count": len(symbol_reports),
        "high_confidence_count": confidence_counts.get(CONFIDENCE_HIGH, 0),
        "medium_confidence_count": confidence_counts.get(CONFIDENCE_MEDIUM, 0),
        "low_confidence_count": confidence_counts.get(CONFIDENCE_LOW, 0),
        "normal_risk_count": risk_counts.get(RISK_NORMAL, 0),
        "caution_risk_count": risk_counts.get(RISK_CAUTION, 0),
        "danger_risk_count": risk_counts.get(RISK_DANGER, 0),
        "candidate_gate_count": len(gates),
        "pass_gate_count": gate_counts.get(GATE_PASS, 0),
        "watch_gate_count": gate_counts.get(GATE_WATCH, 0),
        "block_gate_count": gate_counts.get(GATE_BLOCK, 0),
        "safety_gate_count": gate_counts.get(GATE_SAFETY, 0),
        "safety_breach_count": safety_count,
        "top_symbol": top_report["symbol"] if top_report else None,
        "weakest_symbol": weakest_report["symbol"] if weakest_report else None,
        "average_data_quality_score": average_score,
        "confidence_counts": dict(confidence_counts),
        "risk_counts": dict(risk_counts),
        "candidate_gate_counts": dict(gate_counts),
        "symbol_reports": symbol_reports,
        "candidate_gates": gates[:20],
        "global_verdict": verdict,
        "recommended_action": action,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    symbol_lines = []

    for report in summary["symbol_reports"]:
        symbol_lines.append(
            "- "
            + f"{report['symbol']}: "
            + f"quality={report['data_quality_score']}, "
            + f"confidence={report['data_confidence']}, "
            + f"risk={report['market_risk_state']}, "
            + f"funding={report['funding_regime']}, "
            + f"vol={report['volatility_regime']}, "
            + f"liquidity={report['liquidity_regime']}, "
            + f"action={report['recommended_symbol_action']}"
        )

    gate_lines = []

    for gate in summary["candidate_gates"][:10]:
        gate_lines.append(
            "- "
            + f"{gate['strategy_id']} {gate['symbol']}: "
            + f"gate={gate['candidate_gate_status']}, "
            + f"risk={gate['market_risk_state']}, "
            + f"quality={gate['data_quality_score']}, "
            + f"reason={gate['gate_reason']}"
        )

    symbol_markdown = "\n".join(symbol_lines) or "- None"
    gate_markdown = "\n".join(gate_lines) or "- None"

    return f"""# DeltaGrid Mission 60 Data Quality and Regime Intelligence Report

Report label: {summary['report_label']}
Regime label: {summary['regime_label']}
Created at: {summary['created_at']}
Source dataset label: {summary['source_dataset_label']}
Source factory label: {summary['source_factory_label']}

## Regime Summary

Symbol count: {summary['symbol_count']}
High confidence count: {summary['high_confidence_count']}
Medium confidence count: {summary['medium_confidence_count']}
Low confidence count: {summary['low_confidence_count']}

Normal risk count: {summary['normal_risk_count']}
Caution risk count: {summary['caution_risk_count']}
Danger risk count: {summary['danger_risk_count']}

Candidate gate count: {summary['candidate_gate_count']}
Pass gate count: {summary['pass_gate_count']}
Watch gate count: {summary['watch_gate_count']}
Block gate count: {summary['block_gate_count']}
Safety gate count: {summary['safety_gate_count']}
Safety breach count: {summary['safety_breach_count']}

Top symbol: {summary['top_symbol']}
Weakest symbol: {summary['weakest_symbol']}
Average data quality score: {summary['average_data_quality_score']}

## Symbol Regimes

{symbol_markdown}

## Candidate Gates

{gate_markdown}

## Verdict

Global verdict: {summary['global_verdict']}
Recommended action: {summary['recommended_action']}

## Safety Statement

Live trading remains disabled.
Capital deployment remains blocked.
No private keys were read.
No signatures were produced.
No exchange orders were sent.
No real capital was used.
No paid APIs were used.
"""


def persist_report(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO data_quality_regime_intelligence_reports (
                report_label,
                regime_label,
                created_at,
                source_dataset_label,
                source_factory_label,
                requested_symbol_count,
                symbol_count,
                high_confidence_count,
                medium_confidence_count,
                low_confidence_count,
                normal_risk_count,
                caution_risk_count,
                danger_risk_count,
                candidate_gate_count,
                pass_gate_count,
                watch_gate_count,
                block_gate_count,
                safety_gate_count,
                safety_breach_count,
                top_symbol,
                weakest_symbol,
                average_data_quality_score,
                global_verdict,
                recommended_action,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["report_label"],
                summary["regime_label"],
                summary["created_at"],
                summary["source_dataset_label"],
                summary["source_factory_label"],
                summary["requested_symbol_count"],
                summary["symbol_count"],
                summary["high_confidence_count"],
                summary["medium_confidence_count"],
                summary["low_confidence_count"],
                summary["normal_risk_count"],
                summary["caution_risk_count"],
                summary["danger_risk_count"],
                summary["candidate_gate_count"],
                summary["pass_gate_count"],
                summary["watch_gate_count"],
                summary["block_gate_count"],
                summary["safety_gate_count"],
                summary["safety_breach_count"],
                summary["top_symbol"],
                summary["weakest_symbol"],
                str(summary["average_data_quality_score"]),
                summary["global_verdict"],
                summary["recommended_action"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.commit()


def run_data_quality_regime_intelligence_engine(
    db_path: str | Path = "offchain/deltagrid.db",
    regime_label: str | None = None,
    report_label: str | None = None,
    dataset_label: str = "mission50-final-check",
    factory_label: str | None = None,
    symbols: str | list[str] | tuple[str, ...] | None = None,
    lookback_records: int = 100,
    min_funding_records: int = 20,
    max_acceptable_spread_bps: float = 1.0,
) -> dict[str, Any]:
    db = Path(db_path)
    label = regime_label or new_regime_label()
    report = report_label or new_report_label()
    created_at = utc_now()

    if lookback_records <= 0:
        raise ValueError("lookback_records must be positive")

    if min_funding_records <= 0:
        raise ValueError("min_funding_records must be positive")

    if max_acceptable_spread_bps <= 0:
        raise ValueError("max_acceptable_spread_bps must be positive")

    requested_symbols = parse_symbols(symbols)

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        funding_by_symbol = load_funding_rows(
            conn=conn,
            dataset_label=dataset_label,
            symbols=requested_symbols,
            lookback_records=lookback_records,
        )
        basis_by_symbol = load_basis_rows(
            conn=conn,
            dataset_label=dataset_label,
            symbols=requested_symbols,
        )
        strategy_candidates = load_strategy_candidates(
            conn=conn,
            factory_label=factory_label,
            symbols=requested_symbols,
        )

    symbol_reports = build_symbol_reports(
        regime_label=label,
        created_at=created_at,
        dataset_label=dataset_label,
        funding_by_symbol=funding_by_symbol,
        basis_by_symbol=basis_by_symbol,
        requested_symbols=requested_symbols,
        min_funding_records=min_funding_records,
        max_acceptable_spread_bps=max_acceptable_spread_bps,
    )

    candidate_gates = build_candidate_gates(
        regime_label=label,
        created_at=created_at,
        candidates=strategy_candidates,
        symbol_reports=symbol_reports,
    )

    persist_symbol_reports(db, symbol_reports)
    persist_candidate_gates(db, candidate_gates)

    summary = summarize_engine(
        db_path=db,
        regime_label=label,
        report_label=report,
        created_at=created_at,
        dataset_label=dataset_label,
        factory_label=factory_label,
        requested_symbols=requested_symbols,
        symbol_reports=symbol_reports,
        gates=candidate_gates,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_report(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeltaGrid data quality and regime intelligence engine."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--regime-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--dataset-label", default="mission50-final-check")
    parser.add_argument("--factory-label", default=None)
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--lookback-records", type=int, default=100)
    parser.add_argument("--min-funding-records", type=int, default=20)
    parser.add_argument("--max-acceptable-spread-bps", type=float, default=1.0)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_data_quality_regime_intelligence_engine(
        db_path=args.db,
        regime_label=args.regime_label,
        report_label=args.report_label,
        dataset_label=args.dataset_label,
        factory_label=args.factory_label,
        symbols=args.symbols,
        lookback_records=args.lookback_records,
        min_funding_records=args.min_funding_records,
        max_acceptable_spread_bps=args.max_acceptable_spread_bps,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
