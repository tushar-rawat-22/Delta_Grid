"""
Mission 59: Multi-Strategy Research Factory.

This module builds a multi-strategy shadow research factory.

It scans public funding/basis data and produces strategy candidates for:

1. funding/basis carry
2. funding momentum
3. basis mean reversion
4. volatility regime
5. relative strength

It is a research layer, not an execution layer.

It never:
- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- requires paid APIs
- requires real capital
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

STRATEGY_REGISTRY_TABLE = "multi_strategy_research_registry"
STRATEGY_CANDIDATES_TABLE = "multi_strategy_research_candidates"
STRATEGY_REPORTS_TABLE = "multi_strategy_research_factory_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

STRATEGY_FUNDING_BASIS = "FUNDING_BASIS_CARRY"
STRATEGY_FUNDING_MOMENTUM = "FUNDING_RATE_MOMENTUM"
STRATEGY_BASIS_MEAN_REVERSION = "BASIS_MEAN_REVERSION"
STRATEGY_VOLATILITY_REGIME = "VOLATILITY_REGIME_FILTER"
STRATEGY_RELATIVE_STRENGTH = "CROSS_SYMBOL_RELATIVE_STRENGTH"

CANDIDATE_PROMOTION_SHORTLIST = "STRATEGY_CANDIDATE_PROMOTION_SHORTLIST_SHADOW_ONLY"
CANDIDATE_WATCHLIST = "STRATEGY_CANDIDATE_WATCHLIST_SHADOW_ONLY"
CANDIDATE_REJECT = "STRATEGY_CANDIDATE_REJECTED_SHADOW_ONLY"
CANDIDATE_DATA_INSUFFICIENT = "STRATEGY_CANDIDATE_DATA_INSUFFICIENT"
CANDIDATE_SAFETY_BLOCKED = "STRATEGY_CANDIDATE_SAFETY_BLOCKED"

FACTORY_READY = "MULTI_STRATEGY_FACTORY_READY_SHADOW_ONLY"
FACTORY_WATCHLIST_ONLY = "MULTI_STRATEGY_FACTORY_WATCHLIST_ONLY_SHADOW_ONLY"
FACTORY_NO_CANDIDATES = "MULTI_STRATEGY_FACTORY_NO_CANDIDATES"
FACTORY_DATA_MISSING = "MULTI_STRATEGY_FACTORY_DATA_MISSING"
FACTORY_SAFETY_BREACH = "MULTI_STRATEGY_FACTORY_SAFETY_BREACH_BLOCKED"

RECOMMEND_PROMOTION_REVIEW = "REVIEW_PROMOTION_SHORTLIST_IN_SHADOW_RESEARCH_BOARD"
RECOMMEND_CONTINUE_RESEARCH = "CONTINUE_MULTI_STRATEGY_SHADOW_RESEARCH"
RECOMMEND_REFRESH_DATA = "REFRESH_PUBLIC_DATA_AND_RERUN_FACTORY"
RECOMMEND_SAFETY_REVIEW = "STOP_AND_REVIEW_FACTORY_SAFETY_STATE"

STRATEGY_REGISTRY = [
    {
        "strategy_id": STRATEGY_FUNDING_BASIS,
        "strategy_family": "carry",
        "description": "Ranks symbols by positive funding carry adjusted for basis and spread.",
    },
    {
        "strategy_id": STRATEGY_FUNDING_MOMENTUM,
        "strategy_family": "momentum",
        "description": "Detects improving funding-rate trend using recent funding history.",
    },
    {
        "strategy_id": STRATEGY_BASIS_MEAN_REVERSION,
        "strategy_family": "mean_reversion",
        "description": "Detects large basis dislocation with acceptable spread.",
    },
    {
        "strategy_id": STRATEGY_VOLATILITY_REGIME,
        "strategy_family": "risk_filter",
        "description": "Classifies funding volatility and spread regime for risk filtering.",
    },
    {
        "strategy_id": STRATEGY_RELATIVE_STRENGTH,
        "strategy_family": "cross_sectional",
        "description": "Ranks symbols against each other by funding, basis, and spread quality.",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_factory_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission59-factory-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission59-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
            raise ValueError(f"Only USDT perpetual symbols are supported for Mission 59: {symbol}")

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
            CREATE TABLE IF NOT EXISTS multi_strategy_research_registry (
                registry_id TEXT PRIMARY KEY,
                factory_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                strategy_family TEXT NOT NULL,
                description TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS multi_strategy_research_candidates (
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

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS multi_strategy_research_factory_reports (
                report_label TEXT PRIMARY KEY,
                factory_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_dataset_label TEXT NOT NULL,
                requested_symbol_count INTEGER NOT NULL,
                symbol_count INTEGER NOT NULL,
                strategy_count INTEGER NOT NULL,
                candidate_count INTEGER NOT NULL,
                promotion_shortlist_count INTEGER NOT NULL,
                watchlist_count INTEGER NOT NULL,
                rejected_count INTEGER NOT NULL,
                data_insufficient_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                top_strategy_id TEXT,
                top_symbol TEXT,
                top_alpha_score TEXT NOT NULL,
                average_alpha_score TEXT NOT NULL,
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


def load_latest_basis_rows(
    conn: sqlite3.Connection,
    dataset_label: str,
    symbols: list[str] | None,
) -> dict[str, sqlite3.Row]:
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
        ORDER BY created_at DESC, symbol ASC
    """

    rows = conn.execute(query, params).fetchall()
    latest: dict[str, sqlite3.Row] = {}

    for row in rows:
        symbol = str(row["symbol"])
        if symbol not in latest:
            latest[symbol] = row

    return latest


def funding_metrics(rows: list[sqlite3.Row]) -> dict[str, float]:
    values = [safe_float(row["funding_rate_bps"]) for row in rows]

    if not values:
        return {
            "funding_count": 0,
            "average_funding_bps": 0.0,
            "latest_funding_bps": 0.0,
            "funding_positive_ratio": 0.0,
            "funding_trend_bps": 0.0,
            "funding_volatility_bps": 0.0,
        }

    latest = values[0]
    average = statistics.mean(values)
    positive_ratio = sum(1 for item in values if item > 0) / len(values)

    recent_window = values[: min(8, len(values))]
    older_window = values[min(8, len(values)) : min(16, len(values))]

    recent_average = statistics.mean(recent_window) if recent_window else average
    older_average = statistics.mean(older_window) if older_window else average
    trend = recent_average - older_average

    volatility = statistics.pstdev(values) if len(values) > 1 else 0.0

    return {
        "funding_count": len(values),
        "average_funding_bps": round8(average),
        "latest_funding_bps": round8(latest),
        "funding_positive_ratio": round8(positive_ratio),
        "funding_trend_bps": round8(trend),
        "funding_volatility_bps": round8(volatility),
    }


def basis_metrics(row: sqlite3.Row | None) -> dict[str, float]:
    if row is None:
        return {
            "latest_basis_bps": 0.0,
            "latest_spread_bps": 999.0,
            "basis_available": 0.0,
        }

    return {
        "latest_basis_bps": round8(safe_float(row["basis_bps"])),
        "latest_spread_bps": round8(safe_float(row["spread_bps"])),
        "basis_available": 1.0,
    }


def build_symbol_metrics(
    funding_by_symbol: dict[str, list[sqlite3.Row]],
    basis_by_symbol: dict[str, sqlite3.Row],
    symbols: list[str] | None,
) -> dict[str, dict[str, float]]:
    universe = set(funding_by_symbol.keys()) | set(basis_by_symbol.keys())

    if symbols:
        universe = set(symbols)

    output: dict[str, dict[str, float]] = {}

    for symbol in sorted(universe):
        f = funding_metrics(funding_by_symbol.get(symbol, []))
        b = basis_metrics(basis_by_symbol.get(symbol))
        output[symbol] = {**f, **b}

    return output


def normalize_rank_scores(values_by_symbol: dict[str, float]) -> dict[str, float]:
    if not values_by_symbol:
        return {}

    values = list(values_by_symbol.values())
    minimum = min(values)
    maximum = max(values)

    if maximum == minimum:
        return {symbol: 50.0 for symbol in values_by_symbol}

    return {
        symbol: round8(((value - minimum) / (maximum - minimum)) * 100.0)
        for symbol, value in values_by_symbol.items()
    }


def status_from_scores(
    alpha_score: float,
    confidence_score: float,
    risk_score: float,
    data_quality_score: float,
    min_promotion_score: float,
    min_watchlist_score: float,
) -> tuple[str, int, str]:
    if data_quality_score < 40:
        return CANDIDATE_DATA_INSUFFICIENT, 0, "Insufficient public data quality for strategy evaluation."

    if risk_score >= 80:
        return CANDIDATE_REJECT, 0, "Risk score too high for shadow promotion shortlist."

    if alpha_score >= min_promotion_score and confidence_score >= 60 and risk_score <= 70:
        return CANDIDATE_PROMOTION_SHORTLIST, 1, "Candidate passes shadow promotion shortlist thresholds."

    if alpha_score >= min_watchlist_score and confidence_score >= 40 and risk_score <= 80:
        return CANDIDATE_WATCHLIST, 0, "Candidate has research value but does not pass promotion shortlist thresholds."

    return CANDIDATE_REJECT, 0, "Candidate score below watchlist threshold."


def base_quality_score(metrics: dict[str, float], min_funding_records: int) -> float:
    funding_count = safe_float(metrics.get("funding_count", 0))
    basis_available = safe_float(metrics.get("basis_available", 0))
    funding_component = min(70.0, (funding_count / max(1, min_funding_records)) * 70.0)
    basis_component = 30.0 if basis_available >= 1 else 0.0
    return round8(min(100.0, funding_component + basis_component))


def funding_basis_candidate(
    factory_label: str,
    created_at: str,
    dataset_label: str,
    symbol: str,
    metrics: dict[str, float],
    min_promotion_score: float,
    min_watchlist_score: float,
    min_funding_records: int,
) -> dict[str, Any]:
    average_funding = metrics["average_funding_bps"]
    positive_ratio = metrics["funding_positive_ratio"]
    spread = metrics["latest_spread_bps"]
    basis = metrics["latest_basis_bps"]
    volatility = metrics["funding_volatility_bps"]

    carry_component = average_funding * 70.0
    consistency_component = positive_ratio * 25.0
    basis_component = max(-15.0, min(15.0, -basis * 0.7))
    spread_penalty = spread * 8.0
    volatility_penalty = volatility * 4.0

    alpha = carry_component + consistency_component + basis_component - spread_penalty - volatility_penalty
    confidence = positive_ratio * 100.0
    risk = min(100.0, spread * 20.0 + volatility * 12.0)
    data_quality = base_quality_score(metrics, min_funding_records)

    status, promotion, reason = status_from_scores(
        alpha,
        confidence,
        risk,
        data_quality,
        min_promotion_score,
        min_watchlist_score,
    )

    if average_funding <= 0:
        status = CANDIDATE_REJECT
        promotion = 0
        reason = "Average funding is non-positive."

    return make_candidate(
        factory_label,
        created_at,
        dataset_label,
        STRATEGY_FUNDING_BASIS,
        "carry",
        symbol,
        alpha,
        confidence,
        risk,
        data_quality,
        metrics,
        status,
        promotion,
        reason,
    )


def funding_momentum_candidate(
    factory_label: str,
    created_at: str,
    dataset_label: str,
    symbol: str,
    metrics: dict[str, float],
    min_promotion_score: float,
    min_watchlist_score: float,
    min_funding_records: int,
) -> dict[str, Any]:
    trend = metrics["funding_trend_bps"]
    latest = metrics["latest_funding_bps"]
    positive_ratio = metrics["funding_positive_ratio"]
    volatility = metrics["funding_volatility_bps"]
    spread = metrics["latest_spread_bps"]

    alpha = trend * 120.0 + latest * 30.0 + positive_ratio * 15.0 - volatility * 5.0 - spread * 5.0
    confidence = min(100.0, max(0.0, 50.0 + trend * 80.0 + positive_ratio * 25.0))
    risk = min(100.0, volatility * 15.0 + spread * 15.0)
    data_quality = base_quality_score(metrics, min_funding_records)

    status, promotion, reason = status_from_scores(
        alpha,
        confidence,
        risk,
        data_quality,
        min_promotion_score,
        min_watchlist_score,
    )

    if latest <= 0 or trend <= -0.05:
        status = CANDIDATE_REJECT
        promotion = 0
        reason = "Latest funding or trend is not supportive."

    return make_candidate(
        factory_label,
        created_at,
        dataset_label,
        STRATEGY_FUNDING_MOMENTUM,
        "momentum",
        symbol,
        alpha,
        confidence,
        risk,
        data_quality,
        metrics,
        status,
        promotion,
        reason,
    )


def basis_mean_reversion_candidate(
    factory_label: str,
    created_at: str,
    dataset_label: str,
    symbol: str,
    metrics: dict[str, float],
    min_promotion_score: float,
    min_watchlist_score: float,
    min_funding_records: int,
) -> dict[str, Any]:
    basis = metrics["latest_basis_bps"]
    spread = metrics["latest_spread_bps"]
    positive_ratio = metrics["funding_positive_ratio"]
    volatility = metrics["funding_volatility_bps"]

    dislocation = abs(basis)
    alpha = dislocation * 12.0 + positive_ratio * 10.0 - spread * 18.0 - volatility * 5.0
    confidence = min(100.0, dislocation * 12.0 + positive_ratio * 40.0)
    risk = min(100.0, spread * 25.0 + volatility * 12.0 + max(0.0, -metrics["average_funding_bps"]) * 20.0)
    data_quality = base_quality_score(metrics, min_funding_records)

    status, promotion, reason = status_from_scores(
        alpha,
        confidence,
        risk,
        data_quality,
        min_promotion_score,
        min_watchlist_score,
    )

    if dislocation < 1.0:
        status = CANDIDATE_REJECT
        promotion = 0
        reason = "Basis dislocation is too small for mean-reversion research."

    return make_candidate(
        factory_label,
        created_at,
        dataset_label,
        STRATEGY_BASIS_MEAN_REVERSION,
        "mean_reversion",
        symbol,
        alpha,
        confidence,
        risk,
        data_quality,
        metrics,
        status,
        promotion,
        reason,
    )


def volatility_regime_candidate(
    factory_label: str,
    created_at: str,
    dataset_label: str,
    symbol: str,
    metrics: dict[str, float],
    min_promotion_score: float,
    min_watchlist_score: float,
    min_funding_records: int,
) -> dict[str, Any]:
    volatility = metrics["funding_volatility_bps"]
    spread = metrics["latest_spread_bps"]
    positive_ratio = metrics["funding_positive_ratio"]
    average_funding = metrics["average_funding_bps"]

    stability_score = max(0.0, 100.0 - volatility * 30.0 - spread * 20.0)
    alpha = stability_score * 0.45 + positive_ratio * 20.0 + max(0.0, average_funding) * 25.0
    confidence = stability_score
    risk = min(100.0, volatility * 30.0 + spread * 20.0)
    data_quality = base_quality_score(metrics, min_funding_records)

    status, promotion, reason = status_from_scores(
        alpha,
        confidence,
        risk,
        data_quality,
        min_promotion_score,
        min_watchlist_score,
    )

    if risk > 70:
        status = CANDIDATE_REJECT
        promotion = 0
        reason = "Funding volatility or spread regime is too risky."

    return make_candidate(
        factory_label,
        created_at,
        dataset_label,
        STRATEGY_VOLATILITY_REGIME,
        "risk_filter",
        symbol,
        alpha,
        confidence,
        risk,
        data_quality,
        metrics,
        status,
        promotion,
        reason,
    )


def relative_strength_candidate(
    factory_label: str,
    created_at: str,
    dataset_label: str,
    symbol: str,
    metrics: dict[str, float],
    relative_score: float,
    min_promotion_score: float,
    min_watchlist_score: float,
    min_funding_records: int,
) -> dict[str, Any]:
    spread = metrics["latest_spread_bps"]
    positive_ratio = metrics["funding_positive_ratio"]
    volatility = metrics["funding_volatility_bps"]

    alpha = relative_score + positive_ratio * 15.0 - spread * 8.0 - volatility * 4.0
    confidence = min(100.0, relative_score * 0.7 + positive_ratio * 30.0)
    risk = min(100.0, spread * 15.0 + volatility * 12.0)
    data_quality = base_quality_score(metrics, min_funding_records)

    status, promotion, reason = status_from_scores(
        alpha,
        confidence,
        risk,
        data_quality,
        min_promotion_score,
        min_watchlist_score,
    )

    if relative_score < 35:
        status = CANDIDATE_REJECT
        promotion = 0
        reason = "Symbol is weak on cross-sectional relative strength."

    candidate = make_candidate(
        factory_label,
        created_at,
        dataset_label,
        STRATEGY_RELATIVE_STRENGTH,
        "cross_sectional",
        symbol,
        alpha,
        confidence,
        risk,
        data_quality,
        metrics,
        status,
        promotion,
        reason,
    )
    candidate["relative_strength_score"] = round8(relative_score)
    return candidate


def make_candidate(
    factory_label: str,
    created_at: str,
    dataset_label: str,
    strategy_id: str,
    strategy_family: str,
    symbol: str,
    alpha_score: float,
    confidence_score: float,
    risk_score: float,
    data_quality_score: float,
    metrics: dict[str, float],
    status: str,
    promotion_eligible: int,
    reason: str,
) -> dict[str, Any]:
    if data_quality_score < 40:
        status = CANDIDATE_DATA_INSUFFICIENT
        promotion_eligible = 0
        reason = "Insufficient public data quality for strategy evaluation."

    return {
        "candidate_id": f"{factory_label}-{strategy_id}-{symbol}",
        "factory_label": factory_label,
        "created_at": created_at,
        "source_dataset_label": dataset_label,
        "strategy_id": strategy_id,
        "strategy_family": strategy_family,
        "symbol": symbol,
        "rank": 0,
        "candidate_status": status,
        "promotion_eligible": promotion_eligible,
        "alpha_score": round8(alpha_score),
        "confidence_score": round8(confidence_score),
        "risk_score": round8(risk_score),
        "data_quality_score": round8(data_quality_score),
        "average_funding_bps": round8(metrics.get("average_funding_bps", 0.0)),
        "latest_funding_bps": round8(metrics.get("latest_funding_bps", 0.0)),
        "funding_positive_ratio": round8(metrics.get("funding_positive_ratio", 0.0)),
        "funding_trend_bps": round8(metrics.get("funding_trend_bps", 0.0)),
        "latest_basis_bps": round8(metrics.get("latest_basis_bps", 0.0)),
        "latest_spread_bps": round8(metrics.get("latest_spread_bps", 999.0)),
        "funding_volatility_bps": round8(metrics.get("funding_volatility_bps", 0.0)),
        "relative_strength_score": round8(metrics.get("relative_strength_score", 0.0)),
        "rejection_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "research_role": "MULTI_STRATEGY_FACTORY_SHADOW_RESEARCH_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
        },
    }


def build_candidates(
    factory_label: str,
    created_at: str,
    dataset_label: str,
    symbol_metrics: dict[str, dict[str, float]],
    min_promotion_score: float,
    min_watchlist_score: float,
    min_funding_records: int,
) -> list[dict[str, Any]]:
    relative_input = {
        symbol: metrics["average_funding_bps"] * 70.0
        + metrics["funding_positive_ratio"] * 20.0
        - metrics["latest_spread_bps"] * 8.0
        - abs(metrics["latest_basis_bps"]) * 0.5
        for symbol, metrics in symbol_metrics.items()
    }
    relative_scores = normalize_rank_scores(relative_input)

    candidates: list[dict[str, Any]] = []

    for symbol, metrics in symbol_metrics.items():
        enriched = dict(metrics)
        enriched["relative_strength_score"] = relative_scores.get(symbol, 0.0)

        candidates.append(
            funding_basis_candidate(
                factory_label,
                created_at,
                dataset_label,
                symbol,
                enriched,
                min_promotion_score,
                min_watchlist_score,
                min_funding_records,
            )
        )
        candidates.append(
            funding_momentum_candidate(
                factory_label,
                created_at,
                dataset_label,
                symbol,
                enriched,
                min_promotion_score,
                min_watchlist_score,
                min_funding_records,
            )
        )
        candidates.append(
            basis_mean_reversion_candidate(
                factory_label,
                created_at,
                dataset_label,
                symbol,
                enriched,
                min_promotion_score,
                min_watchlist_score,
                min_funding_records,
            )
        )
        candidates.append(
            volatility_regime_candidate(
                factory_label,
                created_at,
                dataset_label,
                symbol,
                enriched,
                min_promotion_score,
                min_watchlist_score,
                min_funding_records,
            )
        )
        candidates.append(
            relative_strength_candidate(
                factory_label,
                created_at,
                dataset_label,
                symbol,
                enriched,
                relative_scores.get(symbol, 0.0),
                min_promotion_score,
                min_watchlist_score,
                min_funding_records,
            )
        )

    candidates.sort(
        key=lambda item: (
            item["promotion_eligible"],
            item["alpha_score"],
            item["confidence_score"],
            -item["risk_score"],
        ),
        reverse=True,
    )

    for index, candidate in enumerate(candidates, start=1):
        candidate["rank"] = index

    return candidates


def persist_registry(db_path: str | Path, factory_label: str, created_at: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for item in STRATEGY_REGISTRY:
            conn.execute(
                """
                INSERT OR REPLACE INTO multi_strategy_research_registry (
                    registry_id,
                    factory_label,
                    created_at,
                    strategy_id,
                    strategy_family,
                    description,
                    live_trading,
                    live_order_sent,
                    capital_deployment
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{factory_label}-{item['strategy_id']}",
                    factory_label,
                    created_at,
                    item["strategy_id"],
                    item["strategy_family"],
                    item["description"],
                    LIVE_TRADING_STATUS,
                    LIVE_ORDER_SENT_VALUE,
                    CAPITAL_DEPLOYMENT_STATUS,
                ),
            )

        conn.commit()


def persist_candidates(db_path: str | Path, candidates: list[dict[str, Any]]) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for candidate in candidates:
            conn.execute(
                """
                INSERT OR REPLACE INTO multi_strategy_research_candidates (
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
                    candidate["candidate_id"],
                    candidate["factory_label"],
                    candidate["created_at"],
                    candidate["source_dataset_label"],
                    candidate["strategy_id"],
                    candidate["strategy_family"],
                    candidate["symbol"],
                    candidate["rank"],
                    candidate["candidate_status"],
                    candidate["promotion_eligible"],
                    str(candidate["alpha_score"]),
                    str(candidate["confidence_score"]),
                    str(candidate["risk_score"]),
                    str(candidate["data_quality_score"]),
                    str(candidate["average_funding_bps"]),
                    str(candidate["latest_funding_bps"]),
                    str(candidate["funding_positive_ratio"]),
                    str(candidate["funding_trend_bps"]),
                    str(candidate["latest_basis_bps"]),
                    str(candidate["latest_spread_bps"]),
                    str(candidate["funding_volatility_bps"]),
                    str(candidate["relative_strength_score"]),
                    candidate["rejection_reason"],
                    candidate["live_trading"],
                    candidate["live_order_sent"],
                    candidate["capital_deployment"],
                    json.dumps(candidate["metadata"], sort_keys=True),
                ),
            )

        conn.commit()


def safety_breach_count(candidates: list[dict[str, Any]]) -> int:
    return sum(
        1
        for candidate in candidates
        if candidate["live_trading"] != LIVE_TRADING_STATUS
        or int(candidate["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
        or candidate["capital_deployment"] != CAPITAL_DEPLOYMENT_STATUS
    )


def summarize_factory(
    db_path: str | Path,
    factory_label: str,
    report_label: str,
    created_at: str,
    dataset_label: str,
    requested_symbols: list[str] | None,
    symbol_metrics: dict[str, dict[str, float]],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    status_counts = Counter(candidate["candidate_status"] for candidate in candidates)
    strategy_counts = Counter(candidate["strategy_id"] for candidate in candidates)
    symbol_counts = Counter(candidate["symbol"] for candidate in candidates)

    promotion_count = status_counts.get(CANDIDATE_PROMOTION_SHORTLIST, 0)
    watchlist_count = status_counts.get(CANDIDATE_WATCHLIST, 0)
    rejected_count = status_counts.get(CANDIDATE_REJECT, 0)
    data_insufficient_count = status_counts.get(CANDIDATE_DATA_INSUFFICIENT, 0)
    safety_count = safety_breach_count(candidates)

    top_candidate = candidates[0] if candidates else None
    average_alpha = round8(statistics.mean([candidate["alpha_score"] for candidate in candidates])) if candidates else 0.0

    if safety_count > 0:
        verdict = FACTORY_SAFETY_BREACH
        action = RECOMMEND_SAFETY_REVIEW
    elif not symbol_metrics:
        verdict = FACTORY_DATA_MISSING
        action = RECOMMEND_REFRESH_DATA
    elif not candidates:
        verdict = FACTORY_NO_CANDIDATES
        action = RECOMMEND_REFRESH_DATA
    elif promotion_count > 0:
        verdict = FACTORY_READY
        action = RECOMMEND_PROMOTION_REVIEW
    else:
        verdict = FACTORY_WATCHLIST_ONLY
        action = RECOMMEND_CONTINUE_RESEARCH

    return {
        "report_label": report_label,
        "factory_label": factory_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_dataset_label": dataset_label,
        "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
        "symbol_count": len(symbol_metrics),
        "symbols": sorted(symbol_metrics.keys()),
        "strategy_count": len(STRATEGY_REGISTRY),
        "candidate_count": len(candidates),
        "promotion_shortlist_count": promotion_count,
        "watchlist_count": watchlist_count,
        "rejected_count": rejected_count,
        "data_insufficient_count": data_insufficient_count,
        "safety_breach_count": safety_count,
        "candidate_status_counts": dict(status_counts),
        "strategy_candidate_counts": dict(strategy_counts),
        "symbol_candidate_counts": dict(symbol_counts),
        "top_strategy_id": top_candidate["strategy_id"] if top_candidate else None,
        "top_symbol": top_candidate["symbol"] if top_candidate else None,
        "top_alpha_score": top_candidate["alpha_score"] if top_candidate else 0.0,
        "average_alpha_score": average_alpha,
        "top_candidates": candidates[:10],
        "symbol_metrics": symbol_metrics,
        "global_verdict": verdict,
        "recommended_action": action,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    candidate_lines = []

    for candidate in summary["top_candidates"]:
        candidate_lines.append(
            "- "
            + f"rank={candidate['rank']} "
            + f"{candidate['strategy_id']} {candidate['symbol']}: "
            + f"status={candidate['candidate_status']}, "
            + f"alpha={candidate['alpha_score']}, "
            + f"confidence={candidate['confidence_score']}, "
            + f"risk={candidate['risk_score']}, "
            + f"reason={candidate['rejection_reason']}"
        )

    candidates_markdown = "\n".join(candidate_lines) or "- None"

    return f"""# DeltaGrid Mission 59 Multi-Strategy Research Factory Report

Report label: {summary['report_label']}
Factory label: {summary['factory_label']}
Created at: {summary['created_at']}
Source dataset label: {summary['source_dataset_label']}

## Factory Summary

Symbol count: {summary['symbol_count']}
Strategy count: {summary['strategy_count']}
Candidate count: {summary['candidate_count']}

Promotion shortlist count: {summary['promotion_shortlist_count']}
Watchlist count: {summary['watchlist_count']}
Rejected count: {summary['rejected_count']}
Data insufficient count: {summary['data_insufficient_count']}
Safety breach count: {summary['safety_breach_count']}

Top strategy: {summary['top_strategy_id']}
Top symbol: {summary['top_symbol']}
Top alpha score: {summary['top_alpha_score']}
Average alpha score: {summary['average_alpha_score']}

## Top Candidates

{candidates_markdown}

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
            INSERT OR REPLACE INTO multi_strategy_research_factory_reports (
                report_label,
                factory_label,
                created_at,
                source_dataset_label,
                requested_symbol_count,
                symbol_count,
                strategy_count,
                candidate_count,
                promotion_shortlist_count,
                watchlist_count,
                rejected_count,
                data_insufficient_count,
                safety_breach_count,
                top_strategy_id,
                top_symbol,
                top_alpha_score,
                average_alpha_score,
                global_verdict,
                recommended_action,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["report_label"],
                summary["factory_label"],
                summary["created_at"],
                summary["source_dataset_label"],
                summary["requested_symbol_count"],
                summary["symbol_count"],
                summary["strategy_count"],
                summary["candidate_count"],
                summary["promotion_shortlist_count"],
                summary["watchlist_count"],
                summary["rejected_count"],
                summary["data_insufficient_count"],
                summary["safety_breach_count"],
                summary["top_strategy_id"],
                summary["top_symbol"],
                str(summary["top_alpha_score"]),
                str(summary["average_alpha_score"]),
                summary["global_verdict"],
                summary["recommended_action"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.commit()


def run_multi_strategy_research_factory(
    db_path: str | Path = "offchain/deltagrid.db",
    factory_label: str | None = None,
    report_label: str | None = None,
    dataset_label: str = "mission50-final-check",
    symbols: str | list[str] | tuple[str, ...] | None = None,
    lookback_records: int = 100,
    min_funding_records: int = 20,
    min_promotion_score: float = 60.0,
    min_watchlist_score: float = 25.0,
) -> dict[str, Any]:
    db = Path(db_path)
    label = factory_label or new_factory_label()
    report = report_label or new_report_label()
    created_at = utc_now()

    if lookback_records <= 0:
        raise ValueError("lookback_records must be positive")

    if min_funding_records <= 0:
        raise ValueError("min_funding_records must be positive")

    requested_symbols = parse_symbols(symbols)

    ensure_schema(db)
    persist_registry(db, label, created_at)

    if not db.exists():
        summary = summarize_factory(
            db_path=db,
            factory_label=label,
            report_label=report,
            created_at=created_at,
            dataset_label=dataset_label,
            requested_symbols=requested_symbols,
            symbol_metrics={},
            candidates=[],
        )
        summary["markdown_report"] = build_markdown_report(summary)
        persist_report(db, summary, summary["markdown_report"])
        return summary

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        funding_by_symbol = load_funding_rows(
            conn=conn,
            dataset_label=dataset_label,
            symbols=requested_symbols,
            lookback_records=lookback_records,
        )
        basis_by_symbol = load_latest_basis_rows(
            conn=conn,
            dataset_label=dataset_label,
            symbols=requested_symbols,
        )

    symbol_metrics = build_symbol_metrics(
        funding_by_symbol=funding_by_symbol,
        basis_by_symbol=basis_by_symbol,
        symbols=requested_symbols,
    )

    candidates = build_candidates(
        factory_label=label,
        created_at=created_at,
        dataset_label=dataset_label,
        symbol_metrics=symbol_metrics,
        min_promotion_score=min_promotion_score,
        min_watchlist_score=min_watchlist_score,
        min_funding_records=min_funding_records,
    )

    persist_candidates(db, candidates)

    summary = summarize_factory(
        db_path=db,
        factory_label=label,
        report_label=report,
        created_at=created_at,
        dataset_label=dataset_label,
        requested_symbols=requested_symbols,
        symbol_metrics=symbol_metrics,
        candidates=candidates,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_report(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeltaGrid multi-strategy shadow research factory."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--factory-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--dataset-label", default="mission50-final-check")
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--lookback-records", type=int, default=100)
    parser.add_argument("--min-funding-records", type=int, default=20)
    parser.add_argument("--min-promotion-score", type=float, default=60.0)
    parser.add_argument("--min-watchlist-score", type=float, default=25.0)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_multi_strategy_research_factory(
        db_path=args.db,
        factory_label=args.factory_label,
        report_label=args.report_label,
        dataset_label=args.dataset_label,
        symbols=args.symbols,
        lookback_records=args.lookback_records,
        min_funding_records=args.min_funding_records,
        min_promotion_score=args.min_promotion_score,
        min_watchlist_score=args.min_watchlist_score,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
