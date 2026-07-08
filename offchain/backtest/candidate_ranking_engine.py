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

from backtest.funding_basis_model import (
    ensure_schema as ensure_funding_basis_schema,
    resolve_db_path,
    to_decimal,
)

from backtest.multi_symbol_funding_scanner import (
    ensure_schema as ensure_multi_symbol_scan_schema,
)

from backtest.funding_walk_forward_validation import (
    ensure_schema as ensure_walk_forward_schema,
)

from backtest.liquidation_leverage_risk_model import (
    ensure_schema as ensure_liquidation_risk_schema,
)

from backtest.execution_cost_slippage_simulator import (
    ensure_schema as ensure_execution_cost_schema,
)


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")


def safe_decimal(value, default="0"):
    if value is None:
        return Decimal(default)

    return to_decimal(value)


def clamp(value, low, high):
    value = safe_decimal(value)
    low = safe_decimal(low)
    high = safe_decimal(high)

    if value < low:
        return low

    if value > high:
        return high

    return value


def ensure_schema(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS candidate_ranking_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        source_scan_run_label TEXT NOT NULL,
        symbol TEXT NOT NULL,
        scanner_final_verdict TEXT NOT NULL,
        scanner_recommended_action TEXT NOT NULL,
        annualized_funding_rate_pct TEXT NOT NULL,
        net_expected_edge_pct TEXT NOT NULL,
        edge_to_cost_ratio TEXT NOT NULL,
        liquidity_score TEXT NOT NULL,
        funding_score TEXT NOT NULL,
        basis_risk_penalty TEXT NOT NULL,
        scanner_score TEXT NOT NULL,
        walk_forward_verdict TEXT NOT NULL,
        walk_forward_score TEXT NOT NULL,
        liquidation_verdict TEXT NOT NULL,
        max_safe_leverage TEXT NOT NULL,
        execution_cost_verdict TEXT NOT NULL,
        combined_cost_pct TEXT NOT NULL,
        net_execution_edge_pct TEXT NOT NULL,
        rejection_reasons_json TEXT NOT NULL,
        composite_score TEXT NOT NULL,
        final_verdict TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS candidate_ranking_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        source_scan_run_label TEXT NOT NULL,
        candidates_seen INTEGER NOT NULL,
        ranked_count INTEGER NOT NULL,
        go_count INTEGER NOT NULL,
        no_go_count INTEGER NOT NULL,
        best_result_id INTEGER,
        best_symbol TEXT,
        best_composite_score TEXT NOT NULL,
        global_verdict TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def prepare_database(db_path):
    db_path = resolve_db_path(db_path)

    init_market_database(db_path)
    ensure_funding_basis_schema(db_path)
    ensure_multi_symbol_scan_schema(db_path)
    ensure_walk_forward_schema(db_path)
    ensure_liquidation_risk_schema(db_path)
    ensure_execution_cost_schema(db_path)
    ensure_schema(db_path)

    return db_path


def load_scan_results(db_path, scan_run_label):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    rows = cur.execute("""
    SELECT
        id,
        symbol,
        annualized_funding_rate_pct,
        basis_pct,
        quote_volume_24h,
        open_interest_value_usd,
        expected_funding_edge_pct,
        combined_cost_proxy_pct,
        net_expected_edge_pct,
        edge_to_cost_ratio,
        liquidity_score,
        funding_score,
        basis_risk_penalty,
        scanner_score,
        final_verdict,
        recommended_action
    FROM multi_symbol_funding_scan_results
    WHERE run_label = ?
    ORDER BY CAST(scanner_score AS REAL) DESC
    """, (
        scan_run_label,
    )).fetchall()

    conn.close()

    results = []

    for row in rows:
        results.append({
            "scan_result_id": row[0],
            "symbol": row[1],
            "annualized_funding_rate_pct": safe_decimal(row[2]),
            "basis_pct": safe_decimal(row[3]),
            "quote_volume_24h": safe_decimal(row[4]),
            "open_interest_value_usd": safe_decimal(row[5]),
            "expected_funding_edge_pct": safe_decimal(row[6]),
            "combined_cost_proxy_pct": safe_decimal(row[7]),
            "net_expected_edge_pct": safe_decimal(row[8]),
            "edge_to_cost_ratio": safe_decimal(row[9]),
            "liquidity_score": safe_decimal(row[10]),
            "funding_score": safe_decimal(row[11]),
            "basis_risk_penalty": safe_decimal(row[12]),
            "scanner_score": safe_decimal(row[13]),
            "scanner_final_verdict": row[14],
            "scanner_recommended_action": row[15],
        })

    return results


def load_walk_forward_context(db_path, symbol, walk_forward_run_label):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    row = cur.execute("""
    SELECT
        final_verdict,
        stability_score,
        total_trades,
        avg_net_return_pct,
        recommended_action
    FROM funding_walk_forward_summary
    WHERE run_label = ?
    AND symbol = ?
    ORDER BY CAST(stability_score AS REAL) DESC
    LIMIT 1
    """, (
        walk_forward_run_label,
        symbol.upper(),
    )).fetchone()

    conn.close()

    if row is None:
        return {
            "walk_forward_verdict": "MISSING_WALK_FORWARD",
            "walk_forward_score": Decimal("0"),
            "walk_forward_total_trades": 0,
            "walk_forward_avg_net_return_pct": Decimal("0"),
            "walk_forward_action": "RUN_WALK_FORWARD_VALIDATION",
        }

    return {
        "walk_forward_verdict": row[0],
        "walk_forward_score": safe_decimal(row[1]),
        "walk_forward_total_trades": int(row[2]),
        "walk_forward_avg_net_return_pct": safe_decimal(row[3]),
        "walk_forward_action": row[4],
    }


def load_liquidation_context(db_path, symbol, liquidation_run_label):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    row = cur.execute("""
    SELECT
        global_verdict,
        recommended_action,
        best_max_safe_leverage,
        worst_buffer_after_stress_pct,
        worst_total_stress_loss_pct
    FROM liquidation_leverage_risk_summary
    WHERE run_label = ?
    AND symbol = ?
    ORDER BY id DESC
    LIMIT 1
    """, (
        liquidation_run_label,
        symbol.upper(),
    )).fetchone()

    conn.close()

    if row is None:
        return {
            "liquidation_verdict": "MISSING_LIQUIDATION_RISK",
            "liquidation_action": "RUN_LIQUIDATION_RISK_MODEL",
            "max_safe_leverage": Decimal("0"),
            "worst_buffer_after_stress_pct": Decimal("0"),
            "worst_total_stress_loss_pct": Decimal("0"),
        }

    return {
        "liquidation_verdict": row[0],
        "liquidation_action": row[1],
        "max_safe_leverage": safe_decimal(row[2]),
        "worst_buffer_after_stress_pct": safe_decimal(row[3]),
        "worst_total_stress_loss_pct": safe_decimal(row[4]),
    }


def load_execution_cost_context(db_path, symbol, execution_cost_run_label):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    row = cur.execute("""
    SELECT
        global_verdict,
        recommended_action,
        best_net_expected_edge_pct,
        lowest_combined_cost_pct,
        highest_combined_cost_pct
    FROM execution_cost_slippage_summary
    WHERE run_label = ?
    AND symbol = ?
    ORDER BY id DESC
    LIMIT 1
    """, (
        execution_cost_run_label,
        symbol.upper(),
    )).fetchone()

    conn.close()

    if row is None:
        return {
            "execution_cost_verdict": "MISSING_EXECUTION_COST",
            "execution_cost_action": "RUN_EXECUTION_COST_MODEL",
            "net_execution_edge_pct": Decimal("0"),
            "combined_cost_pct": Decimal("0"),
            "highest_combined_cost_pct": Decimal("0"),
        }

    return {
        "execution_cost_verdict": row[0],
        "execution_cost_action": row[1],
        "net_execution_edge_pct": safe_decimal(row[2]),
        "combined_cost_pct": safe_decimal(row[3]),
        "highest_combined_cost_pct": safe_decimal(row[4]),
    }


def risk_gate_passes_liquidation(verdict):
    return verdict == "LIQUIDATION_LEVERAGE_RISK_ACCEPTABLE_NO_LIVE_TRADING"


def cost_gate_passes_execution(verdict):
    return verdict == "EXECUTION_COST_ACCEPTABLE_NO_LIVE_TRADING"


def walk_forward_gate_passes(verdict):
    return verdict == "GO_FOR_RESEARCH"


def rejection_reasons(
    candidate,
    walk_forward,
    liquidation,
    execution_cost,
    min_net_expected_edge_pct,
    min_edge_to_cost_ratio,
    min_composite_score,
    require_walk_forward,
    require_liquidation,
    require_execution_cost,
):
    reasons = []

    if candidate["scanner_final_verdict"] != "GO_FOR_RESEARCH":
        reasons.append(candidate["scanner_final_verdict"])

    if candidate["net_expected_edge_pct"] < min_net_expected_edge_pct:
        reasons.append("NET_EDGE_BELOW_REQUIRED_THRESHOLD")

    if candidate["edge_to_cost_ratio"] < min_edge_to_cost_ratio:
        reasons.append("EDGE_TO_COST_RATIO_TOO_LOW")

    if walk_forward["walk_forward_verdict"] == "MISSING_WALK_FORWARD":
        reasons.append("MISSING_WALK_FORWARD_CONTEXT")
    elif not walk_forward_gate_passes(walk_forward["walk_forward_verdict"]):
        reasons.append(walk_forward["walk_forward_verdict"])

    if liquidation["liquidation_verdict"] == "MISSING_LIQUIDATION_RISK":
        reasons.append("MISSING_LIQUIDATION_RISK_CONTEXT")
    elif not risk_gate_passes_liquidation(liquidation["liquidation_verdict"]):
        reasons.append(liquidation["liquidation_verdict"])

    if execution_cost["execution_cost_verdict"] == "MISSING_EXECUTION_COST":
        reasons.append("MISSING_EXECUTION_COST_CONTEXT")
    elif not cost_gate_passes_execution(execution_cost["execution_cost_verdict"]):
        reasons.append(execution_cost["execution_cost_verdict"])

    if require_walk_forward and walk_forward["walk_forward_verdict"] == "MISSING_WALK_FORWARD":
        reasons.append("REQUIRED_WALK_FORWARD_GATE_MISSING")

    if require_liquidation and liquidation["liquidation_verdict"] == "MISSING_LIQUIDATION_RISK":
        reasons.append("REQUIRED_LIQUIDATION_GATE_MISSING")

    if require_execution_cost and execution_cost["execution_cost_verdict"] == "MISSING_EXECUTION_COST":
        reasons.append("REQUIRED_EXECUTION_COST_GATE_MISSING")

    return reasons


def compute_composite_score(candidate, walk_forward, liquidation, execution_cost):
    scanner_component = clamp(
        candidate["scanner_score"],
        Decimal("0"),
        Decimal("120"),
    ) * Decimal("0.35")

    net_edge_component = clamp(
        candidate["net_expected_edge_pct"] * Decimal("200"),
        Decimal("-40"),
        Decimal("40"),
    )

    edge_cost_component = clamp(
        candidate["edge_to_cost_ratio"] * Decimal("15"),
        Decimal("0"),
        Decimal("45"),
    )

    liquidity_component = clamp(
        candidate["liquidity_score"] * Decimal("0.25"),
        Decimal("0"),
        Decimal("20"),
    )

    funding_component = clamp(
        abs(candidate["annualized_funding_rate_pct"]) * Decimal("1.25"),
        Decimal("0"),
        Decimal("35"),
    )

    basis_penalty = clamp(
        candidate["basis_risk_penalty"],
        Decimal("0"),
        Decimal("60"),
    )

    if walk_forward_gate_passes(walk_forward["walk_forward_verdict"]):
        walk_forward_component = Decimal("15")
    elif walk_forward["walk_forward_verdict"] == "MISSING_WALK_FORWARD":
        walk_forward_component = Decimal("-5")
    else:
        walk_forward_component = Decimal("-25")

    if risk_gate_passes_liquidation(liquidation["liquidation_verdict"]):
        liquidation_component = Decimal("15")
    elif liquidation["liquidation_verdict"] == "MISSING_LIQUIDATION_RISK":
        liquidation_component = Decimal("-5")
    else:
        liquidation_component = Decimal("-25")

    if cost_gate_passes_execution(execution_cost["execution_cost_verdict"]):
        execution_component = Decimal("15")
    elif execution_cost["execution_cost_verdict"] == "MISSING_EXECUTION_COST":
        execution_component = Decimal("-5")
    else:
        execution_component = Decimal("-25")

    return (
        scanner_component
        + net_edge_component
        + edge_cost_component
        + liquidity_component
        + funding_component
        + walk_forward_component
        + liquidation_component
        + execution_component
        - basis_penalty
    )


def final_candidate_verdict(
    candidate,
    walk_forward,
    liquidation,
    execution_cost,
    composite_score,
    min_net_expected_edge_pct,
    min_edge_to_cost_ratio,
    min_composite_score,
    require_walk_forward,
    require_liquidation,
    require_execution_cost,
):
    if candidate["scanner_final_verdict"] != "GO_FOR_RESEARCH":
        return "NO_GO_SCANNER_REJECTED"

    if candidate["net_expected_edge_pct"] < min_net_expected_edge_pct:
        return "NO_GO_NET_EDGE_TOO_SMALL"

    if candidate["edge_to_cost_ratio"] < min_edge_to_cost_ratio:
        return "NO_GO_EDGE_BELOW_COST"

    if require_walk_forward and not walk_forward_gate_passes(walk_forward["walk_forward_verdict"]):
        return "NO_GO_WALK_FORWARD_GATE"

    if require_liquidation and not risk_gate_passes_liquidation(liquidation["liquidation_verdict"]):
        return "NO_GO_LIQUIDATION_GATE"

    if require_execution_cost and not cost_gate_passes_execution(execution_cost["execution_cost_verdict"]):
        return "NO_GO_EXECUTION_COST_GATE"

    if composite_score < min_composite_score:
        return "NO_GO_LOW_COMPOSITE_SCORE"

    return "GO_FOR_RESEARCH_RANKED"


def recommended_action(verdict):
    if verdict == "GO_FOR_RESEARCH_RANKED":
        return "PROMOTE_TO_PAPER_TRADING_CANDIDATE_SET"

    if verdict == "NO_GO_SCANNER_REJECTED":
        return "WAIT_FOR_SCANNER_GO_SIGNAL"

    if verdict == "NO_GO_NET_EDGE_TOO_SMALL":
        return "WAIT_FOR_STRONGER_AFTER_COST_EDGE"

    if verdict == "NO_GO_EDGE_BELOW_COST":
        return "WAIT_FOR_BETTER_EDGE_TO_COST_RATIO"

    if verdict == "NO_GO_WALK_FORWARD_GATE":
        return "REWORK_OR_VALIDATE_WALK_FORWARD_STABILITY"

    if verdict == "NO_GO_LIQUIDATION_GATE":
        return "LOWER_LEVERAGE_OR_REWORK_RISK_ASSUMPTIONS"

    if verdict == "NO_GO_EXECUTION_COST_GATE":
        return "WAIT_FOR_BETTER_LIQUIDITY_OR_LOWER_COSTS"

    if verdict == "NO_GO_LOW_COMPOSITE_SCORE":
        return "KEEP_ON_WATCHLIST"

    return "OBSERVE_ONLY"


def evaluate_candidate(
    candidate,
    walk_forward,
    liquidation,
    execution_cost,
    min_net_expected_edge_pct,
    min_edge_to_cost_ratio,
    min_composite_score,
    require_walk_forward,
    require_liquidation,
    require_execution_cost,
):
    composite = compute_composite_score(
        candidate=candidate,
        walk_forward=walk_forward,
        liquidation=liquidation,
        execution_cost=execution_cost,
    )

    verdict = final_candidate_verdict(
        candidate=candidate,
        walk_forward=walk_forward,
        liquidation=liquidation,
        execution_cost=execution_cost,
        composite_score=composite,
        min_net_expected_edge_pct=min_net_expected_edge_pct,
        min_edge_to_cost_ratio=min_edge_to_cost_ratio,
        min_composite_score=min_composite_score,
        require_walk_forward=require_walk_forward,
        require_liquidation=require_liquidation,
        require_execution_cost=require_execution_cost,
    )

    reasons = rejection_reasons(
        candidate=candidate,
        walk_forward=walk_forward,
        liquidation=liquidation,
        execution_cost=execution_cost,
        min_net_expected_edge_pct=min_net_expected_edge_pct,
        min_edge_to_cost_ratio=min_edge_to_cost_ratio,
        min_composite_score=min_composite_score,
        require_walk_forward=require_walk_forward,
        require_liquidation=require_liquidation,
        require_execution_cost=require_execution_cost,
    )

    if composite < min_composite_score:
        reasons.append("COMPOSITE_SCORE_BELOW_REQUIRED_THRESHOLD")

    return {
        "symbol": candidate["symbol"],
        "scanner_final_verdict": candidate["scanner_final_verdict"],
        "scanner_recommended_action": candidate["scanner_recommended_action"],
        "annualized_funding_rate_pct": candidate["annualized_funding_rate_pct"],
        "net_expected_edge_pct": candidate["net_expected_edge_pct"],
        "edge_to_cost_ratio": candidate["edge_to_cost_ratio"],
        "liquidity_score": candidate["liquidity_score"],
        "funding_score": candidate["funding_score"],
        "basis_risk_penalty": candidate["basis_risk_penalty"],
        "scanner_score": candidate["scanner_score"],
        "walk_forward_verdict": walk_forward["walk_forward_verdict"],
        "walk_forward_score": walk_forward["walk_forward_score"],
        "liquidation_verdict": liquidation["liquidation_verdict"],
        "max_safe_leverage": liquidation["max_safe_leverage"],
        "execution_cost_verdict": execution_cost["execution_cost_verdict"],
        "combined_cost_pct": execution_cost["combined_cost_pct"],
        "net_execution_edge_pct": execution_cost["net_execution_edge_pct"],
        "rejection_reasons": reasons,
        "composite_score": composite,
        "final_verdict": verdict,
        "recommended_action": recommended_action(verdict),
    }


def insert_ranking_result(
    db_path,
    run_label,
    source_scan_run_label,
    result,
    assumptions,
):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO candidate_ranking_results (
        run_label,
        source_scan_run_label,
        symbol,
        scanner_final_verdict,
        scanner_recommended_action,
        annualized_funding_rate_pct,
        net_expected_edge_pct,
        edge_to_cost_ratio,
        liquidity_score,
        funding_score,
        basis_risk_penalty,
        scanner_score,
        walk_forward_verdict,
        walk_forward_score,
        liquidation_verdict,
        max_safe_leverage,
        execution_cost_verdict,
        combined_cost_pct,
        net_execution_edge_pct,
        rejection_reasons_json,
        composite_score,
        final_verdict,
        recommended_action,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_label,
        source_scan_run_label,
        result["symbol"],
        result["scanner_final_verdict"],
        result["scanner_recommended_action"],
        format(result["annualized_funding_rate_pct"], "f"),
        format(result["net_expected_edge_pct"], "f"),
        format(result["edge_to_cost_ratio"], "f"),
        format(result["liquidity_score"], "f"),
        format(result["funding_score"], "f"),
        format(result["basis_risk_penalty"], "f"),
        format(result["scanner_score"], "f"),
        result["walk_forward_verdict"],
        format(result["walk_forward_score"], "f"),
        result["liquidation_verdict"],
        format(result["max_safe_leverage"], "f"),
        result["execution_cost_verdict"],
        format(result["combined_cost_pct"], "f"),
        format(result["net_execution_edge_pct"], "f"),
        json.dumps(result["rejection_reasons"]),
        format(result["composite_score"], "f"),
        result["final_verdict"],
        result["recommended_action"],
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def summarize_ranked_results(ranked_results, candidates_seen):
    go_results = [
        item
        for item in ranked_results
        if item["final_verdict"] == "GO_FOR_RESEARCH_RANKED"
    ]

    best = ranked_results[0] if ranked_results else None

    if go_results:
        global_verdict = "RANKED_CANDIDATES_FOUND_NO_LIVE_TRADING"
        action = "PROMOTE_TO_PAPER_TRADING_ENGINE"
    else:
        global_verdict = "NO_RANKED_CANDIDATES_NO_LIVE_TRADING"
        action = "KEEP_SCANNING_AND_WAIT_FOR_STRONGER_EDGE"

    return {
        "candidates_seen": int(candidates_seen),
        "ranked_count": len(ranked_results),
        "go_count": len(go_results),
        "no_go_count": len(ranked_results) - len(go_results),
        "best_result_id": None if best is None else best["id"],
        "best_symbol": None if best is None else best["symbol"],
        "best_composite_score": Decimal("0") if best is None else best["composite_score"],
        "global_verdict": global_verdict,
        "recommended_action": action,
    }


def insert_summary(
    db_path,
    run_label,
    source_scan_run_label,
    summary,
    assumptions,
):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO candidate_ranking_summary (
        run_label,
        source_scan_run_label,
        candidates_seen,
        ranked_count,
        go_count,
        no_go_count,
        best_result_id,
        best_symbol,
        best_composite_score,
        global_verdict,
        recommended_action,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_label,
        source_scan_run_label,
        summary["candidates_seen"],
        summary["ranked_count"],
        summary["go_count"],
        summary["no_go_count"],
        summary["best_result_id"],
        summary["best_symbol"],
        format(summary["best_composite_score"], "f"),
        summary["global_verdict"],
        summary["recommended_action"],
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def clean_decimal_dict(item):
    cleaned = {}

    for key, value in item.items():
        if isinstance(value, Decimal):
            cleaned[key] = format(value, "f")
        else:
            cleaned[key] = value

    return cleaned


def run_candidate_ranking_engine(
    db_path,
    scan_run_label,
    walk_forward_run_label,
    liquidation_run_label,
    execution_cost_run_label,
    run_label,
    min_net_expected_edge_pct,
    min_edge_to_cost_ratio,
    min_composite_score,
    require_walk_forward,
    require_liquidation,
    require_execution_cost,
):
    db_path = prepare_database(db_path)

    assumptions = {
        "research_only": True,
        "no_private_keys": True,
        "no_signing": True,
        "no_real_trades": True,
        "no_order_execution": True,
        "run_label": run_label,
        "scan_run_label": scan_run_label,
        "walk_forward_run_label": walk_forward_run_label,
        "liquidation_run_label": liquidation_run_label,
        "execution_cost_run_label": execution_cost_run_label,
        "min_net_expected_edge_pct": format(to_decimal(min_net_expected_edge_pct), "f"),
        "min_edge_to_cost_ratio": format(to_decimal(min_edge_to_cost_ratio), "f"),
        "min_composite_score": format(to_decimal(min_composite_score), "f"),
        "require_walk_forward": bool(require_walk_forward),
        "require_liquidation": bool(require_liquidation),
        "require_execution_cost": bool(require_execution_cost),
    }

    scan_results = load_scan_results(
        db_path=db_path,
        scan_run_label=scan_run_label,
    )

    results = []

    for candidate in scan_results:
        walk_forward = load_walk_forward_context(
            db_path=db_path,
            symbol=candidate["symbol"],
            walk_forward_run_label=walk_forward_run_label,
        )

        liquidation = load_liquidation_context(
            db_path=db_path,
            symbol=candidate["symbol"],
            liquidation_run_label=liquidation_run_label,
        )

        execution_cost = load_execution_cost_context(
            db_path=db_path,
            symbol=candidate["symbol"],
            execution_cost_run_label=execution_cost_run_label,
        )

        result = evaluate_candidate(
            candidate=candidate,
            walk_forward=walk_forward,
            liquidation=liquidation,
            execution_cost=execution_cost,
            min_net_expected_edge_pct=to_decimal(min_net_expected_edge_pct),
            min_edge_to_cost_ratio=to_decimal(min_edge_to_cost_ratio),
            min_composite_score=to_decimal(min_composite_score),
            require_walk_forward=bool(require_walk_forward),
            require_liquidation=bool(require_liquidation),
            require_execution_cost=bool(require_execution_cost),
        )

        row_id = insert_ranking_result(
            db_path=db_path,
            run_label=run_label,
            source_scan_run_label=scan_run_label,
            result=result,
            assumptions=assumptions,
        )

        results.append({
            "id": row_id,
            **result,
        })

    ranked = sorted(
        results,
        key=lambda item: (
            item["final_verdict"] == "GO_FOR_RESEARCH_RANKED",
            item["composite_score"],
            item["net_expected_edge_pct"],
            item["edge_to_cost_ratio"],
        ),
        reverse=True,
    )

    summary = summarize_ranked_results(
        ranked_results=ranked,
        candidates_seen=len(scan_results),
    )

    summary_id = insert_summary(
        db_path=db_path,
        run_label=run_label,
        source_scan_run_label=scan_run_label,
        summary=summary,
        assumptions=assumptions,
    )

    return {
        "run_label": run_label,
        "source_scan_run_label": scan_run_label,
        "summary_id": summary_id,
        "candidates_seen": len(scan_results),
        "ranked_count": len(ranked),
        "go_count": summary["go_count"],
        "no_go_count": summary["no_go_count"],
        "best_symbol": summary["best_symbol"],
        "best_composite_score": format(summary["best_composite_score"], "f"),
        "top_ranked_candidates": [
            clean_decimal_dict(item)
            for item in ranked[:10]
        ],
        "global_verdict": summary["global_verdict"],
        "recommended_action": summary["recommended_action"],
    }


def parse_bool(value):
    text = str(value).strip().lower()

    return text in {"1", "true", "yes", "y", "on"}


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--scan-run-label", default="mission_29_multi_symbol_funding_scanner")
    parser.add_argument("--walk-forward-run-label", default="mission_26_funding_walk_forward_validation")
    parser.add_argument("--liquidation-run-label", default="mission_27_liquidation_leverage_risk_model")
    parser.add_argument("--execution-cost-run-label", default="mission_28_execution_cost_slippage_simulator")
    parser.add_argument("--run-label", default="mission_30_candidate_ranking_engine")
    parser.add_argument("--min-net-expected-edge-pct", default="0.02")
    parser.add_argument("--min-edge-to-cost-ratio", default="1.50")
    parser.add_argument("--min-composite-score", default="75")
    parser.add_argument("--require-walk-forward", default="false")
    parser.add_argument("--require-liquidation", default="false")
    parser.add_argument("--require-execution-cost", default="false")

    args = parser.parse_args()

    print("DeltaGrid Candidate Ranking Engine")
    print("Mode: research-only")
    print("No private keys. No signing. No real trades.")

    result = run_candidate_ranking_engine(
        db_path=args.db_path,
        scan_run_label=args.scan_run_label,
        walk_forward_run_label=args.walk_forward_run_label,
        liquidation_run_label=args.liquidation_run_label,
        execution_cost_run_label=args.execution_cost_run_label,
        run_label=args.run_label,
        min_net_expected_edge_pct=Decimal(args.min_net_expected_edge_pct),
        min_edge_to_cost_ratio=Decimal(args.min_edge_to_cost_ratio),
        min_composite_score=Decimal(args.min_composite_score),
        require_walk_forward=parse_bool(args.require_walk_forward),
        require_liquidation=parse_bool(args.require_liquidation),
        require_execution_cost=parse_bool(args.require_execution_cost),
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
