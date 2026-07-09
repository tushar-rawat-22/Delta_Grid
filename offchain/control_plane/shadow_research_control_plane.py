"""
Mission 58: Shadow Research Control Plane and Documentation Registry.

This module orchestrates a full shadow research cycle:

1. dataset reuse / public data orchestration stage
2. shadow ledger tracking update
3. shadow tracking performance report
4. shadow tracking alert and invalidation routing
5. documentation registry check

It is a control plane, not an execution layer.

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
import sqlite3
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from offchain.backtest.shadow_ledger_tracking_updater import run_shadow_ledger_tracking_updater
from offchain.backtest.shadow_tracking_performance_reporter import run_shadow_tracking_performance_reporter
from offchain.backtest.shadow_tracking_alert_invalidation_router import (
    run_shadow_tracking_alert_invalidation_router,
)


CYCLES_TABLE = "shadow_research_control_plane_cycles"
STAGES_TABLE = "shadow_research_control_plane_stage_runs"
DOCS_REGISTRY_TABLE = "shadow_research_documentation_registry"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

STAGE_COMPLETED = "CONTROL_STAGE_COMPLETED"
STAGE_ATTENTION = "CONTROL_STAGE_NEEDS_ATTENTION"
STAGE_BLOCKED = "CONTROL_STAGE_BLOCKED"

DATA_REFRESH_REUSED = "DATA_REFRESH_REUSED_EXISTING_PUBLIC_DATASET"
DATA_REFRESH_SKIPPED = "DATA_REFRESH_SKIPPED_NO_DATASET_LABEL"

CONTROL_CONTINUE = "CONTROL_PLANE_CYCLE_CONTINUE_SHADOW_ONLY"
CONTROL_WARNING = "CONTROL_PLANE_CYCLE_WARNING_SHADOW_ONLY"
CONTROL_INVALIDATION = "CONTROL_PLANE_CYCLE_INVALIDATION_REQUIRED_SHADOW_ONLY"
CONTROL_REFRESH_DATA = "CONTROL_PLANE_CYCLE_REFRESH_DATA_REQUIRED_SHADOW_ONLY"
CONTROL_SAFETY_BREACH = "CONTROL_PLANE_CYCLE_SAFETY_BREACH_BLOCKED"
CONTROL_NEEDS_ATTENTION = "CONTROL_PLANE_CYCLE_NEEDS_ATTENTION_SHADOW_ONLY"

RECOMMEND_CONTINUE = "CONTINUE_SHADOW_RESEARCH_CYCLE_ONLY"
RECOMMEND_WARN = "CONTINUE_WITH_TIGHTER_SHADOW_THRESHOLDS"
RECOMMEND_INVALIDATE = "INVALIDATE_OR_REVIEW_SHADOW_OBSERVATIONS_NO_TRADING"
RECOMMEND_REFRESH = "REFRESH_PUBLIC_DATA_AND_RERUN_CONTROL_PLANE"
RECOMMEND_SAFETY = "STOP_AND_REVIEW_CONTROL_PLANE_SAFETY_STATE"
RECOMMEND_ATTENTION = "REVIEW_CONTROL_PLANE_STAGE_FAILURES"

DOC_REQUIRED = [
    {
        "path": "docs/ROADMAP.md",
        "category": "roadmap",
        "required_marker": "Mission 58: Shadow Research Control Plane",
    },
    {
        "path": "docs/MISSION_INDEX.md",
        "category": "mission-index",
        "required_marker": "Mission 58",
    },
    {
        "path": "docs/ARCHITECTURE_STATE.md",
        "category": "architecture",
        "required_marker": "Shadow Research Control Plane",
    },
    {
        "path": "docs/RISK_POLICY.md",
        "category": "risk",
        "required_marker": "Live Trading Remains Blocked",
    },
    {
        "path": "docs/RESEARCH_POLICY.md",
        "category": "research",
        "required_marker": "Research-First Operating Model",
    },
    {
        "path": "docs/SAFETY_INVARIANTS.md",
        "category": "safety",
        "required_marker": "Non-Negotiable Safety Invariants",
    },
    {
        "path": "docs/DOCUMENTATION_REGISTRY.md",
        "category": "documentation",
        "required_marker": "Mission 58 Documentation Registry",
    },
    {
        "path": "docs/PROJECT_SOURCE_OF_TRUTH.md",
        "category": "source-of-truth",
        "required_marker": "Mission 58 Completion Record",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_cycle_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission58-control-plane-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission58-report-{stamp}-{uuid.uuid4().hex[:8]}"


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def safe_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, default=str)


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
            raise ValueError(f"Only USDT perpetual symbols are supported for Mission 58: {symbol}")

        if not symbol.replace("_", "").isalnum():
            raise ValueError(f"Invalid symbol: {symbol}")

        if symbol not in symbols:
            symbols.append(symbol)

    if not symbols:
        raise ValueError("At least one symbol is required when symbols are supplied")

    return symbols


def ensure_schema(db_path: str | Path) -> None:
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_research_control_plane_cycles (
                report_label TEXT PRIMARY KEY,
                cycle_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                symbols_csv TEXT NOT NULL,
                stage_count INTEGER NOT NULL,
                completed_stage_count INTEGER NOT NULL,
                attention_stage_count INTEGER NOT NULL,
                blocked_stage_count INTEGER NOT NULL,
                documentation_registry_count INTEGER NOT NULL,
                documentation_ready_count INTEGER NOT NULL,
                tracking_update_count INTEGER NOT NULL,
                active_tracking_count INTEGER NOT NULL,
                performance_active_count INTEGER NOT NULL,
                route_count INTEGER NOT NULL,
                continue_route_count INTEGER NOT NULL,
                warning_route_count INTEGER NOT NULL,
                invalidation_route_count INTEGER NOT NULL,
                refresh_data_route_count INTEGER NOT NULL,
                safety_block_route_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                top_symbol TEXT,
                control_plane_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_research_control_plane_stage_runs (
                stage_run_id TEXT PRIMARY KEY,
                cycle_label TEXT NOT NULL,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                stage_order INTEGER NOT NULL,
                stage_name TEXT NOT NULL,
                stage_status TEXT NOT NULL,
                stage_verdict TEXT NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                input_json TEXT NOT NULL,
                output_json TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_research_documentation_registry (
                registry_id TEXT PRIMARY KEY,
                cycle_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                document_path TEXT NOT NULL,
                document_category TEXT NOT NULL,
                required_marker TEXT NOT NULL,
                document_exists INTEGER NOT NULL,
                marker_found INTEGER NOT NULL,
                registry_status TEXT NOT NULL
            )
            """
        )

        conn.commit()


def stage_status_from_verdict(verdict: str, safety_breach_count: int) -> str:
    if safety_breach_count > 0 or "SAFETY" in verdict:
        return STAGE_BLOCKED

    completed_verdicts = {
        DATA_REFRESH_REUSED,
        "DOCUMENTATION_REGISTRY_READY",
    }

    if verdict in completed_verdicts:
        return STAGE_COMPLETED

    attention_terms = [
        "MISSING",
        "NO_",
        "INVALIDATED",
        "WARNING",
        "REFRESH",
        "NEEDS_ATTENTION",
        "DETERIORATING",
        "INCOMPLETE",
    ]

    if any(term in verdict for term in attention_terms):
        if "CONTINUE" not in verdict and "ACTIVE" not in verdict and "STRONG" not in verdict:
            return STAGE_ATTENTION

    return STAGE_COMPLETED


def make_stage(
    cycle_label: str,
    report_label: str,
    created_at: str,
    stage_order: int,
    stage_name: str,
    stage_verdict: str,
    input_payload: dict[str, Any],
    output_payload: dict[str, Any],
) -> dict[str, Any]:
    safety_breach_count = safe_int(output_payload.get("safety_breach_count", 0))
    stage_status = stage_status_from_verdict(stage_verdict, safety_breach_count)

    return {
        "stage_run_id": f"{cycle_label}-{stage_order:02d}-{stage_name}",
        "cycle_label": cycle_label,
        "report_label": report_label,
        "created_at": created_at,
        "stage_order": stage_order,
        "stage_name": stage_name,
        "stage_status": stage_status,
        "stage_verdict": stage_verdict,
        "safety_breach_count": safety_breach_count,
        "input": input_payload,
        "output": output_payload,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
    }


def build_data_reuse_stage(
    cycle_label: str,
    report_label: str,
    created_at: str,
    market_dataset_label: str | None,
) -> dict[str, Any]:
    if market_dataset_label:
        verdict = DATA_REFRESH_REUSED
        output = {
            "data_stage_mode": "REUSE_EXISTING_PUBLIC_DATASET",
            "market_dataset_label": market_dataset_label,
            "safety_breach_count": 0,
            "note": "Mission 58 control plane reuses an existing public dataset label by default.",
        }
    else:
        verdict = DATA_REFRESH_SKIPPED
        output = {
            "data_stage_mode": "SKIPPED_NO_MARKET_DATASET_LABEL",
            "market_dataset_label": None,
            "safety_breach_count": 0,
            "note": "No market dataset label supplied. Downstream stages may request data refresh.",
        }

    return make_stage(
        cycle_label=cycle_label,
        report_label=report_label,
        created_at=created_at,
        stage_order=1,
        stage_name="public_data_orchestration",
        stage_verdict=verdict,
        input_payload={"market_dataset_label": market_dataset_label},
        output_payload=output,
    )


def build_documentation_registry(
    cycle_label: str,
    created_at: str,
    docs_root: str | Path,
) -> list[dict[str, Any]]:
    root = Path(docs_root)
    records: list[dict[str, Any]] = []

    for item in DOC_REQUIRED:
        doc_path = Path(item["path"])
        if root.name == "docs" and str(doc_path).startswith("docs/"):
            candidate = root / doc_path.relative_to("docs")
        else:
            candidate = root / doc_path

        exists = candidate.exists()
        text = candidate.read_text(encoding="utf-8") if exists else ""
        marker = str(item["required_marker"])
        marker_found = marker in text if exists else False

        status = "DOCUMENTATION_READY" if exists and marker_found else "DOCUMENTATION_INCOMPLETE"

        records.append(
            {
                "registry_id": f"{cycle_label}-{item['category']}",
                "cycle_label": cycle_label,
                "created_at": created_at,
                "document_path": item["path"],
                "document_category": item["category"],
                "required_marker": marker,
                "document_exists": 1 if exists else 0,
                "marker_found": 1 if marker_found else 0,
                "registry_status": status,
            }
        )

    return records


def persist_documentation_registry(db_path: str | Path, records: list[dict[str, Any]]) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for record in records:
            conn.execute(
                """
                INSERT OR REPLACE INTO shadow_research_documentation_registry (
                    registry_id,
                    cycle_label,
                    created_at,
                    document_path,
                    document_category,
                    required_marker,
                    document_exists,
                    marker_found,
                    registry_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["registry_id"],
                    record["cycle_label"],
                    record["created_at"],
                    record["document_path"],
                    record["document_category"],
                    record["required_marker"],
                    record["document_exists"],
                    record["marker_found"],
                    record["registry_status"],
                ),
            )

        conn.commit()


def persist_stage_runs(db_path: str | Path, stages: list[dict[str, Any]]) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for stage in stages:
            conn.execute(
                """
                INSERT OR REPLACE INTO shadow_research_control_plane_stage_runs (
                    stage_run_id,
                    cycle_label,
                    report_label,
                    created_at,
                    stage_order,
                    stage_name,
                    stage_status,
                    stage_verdict,
                    safety_breach_count,
                    input_json,
                    output_json,
                    live_trading,
                    live_order_sent,
                    capital_deployment
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stage["stage_run_id"],
                    stage["cycle_label"],
                    stage["report_label"],
                    stage["created_at"],
                    stage["stage_order"],
                    stage["stage_name"],
                    stage["stage_status"],
                    stage["stage_verdict"],
                    stage["safety_breach_count"],
                    safe_json(stage["input"]),
                    safe_json(stage["output"]),
                    stage["live_trading"],
                    stage["live_order_sent"],
                    stage["capital_deployment"],
                ),
            )

        conn.commit()


def decide_control_plane_verdict(router_result: dict[str, Any], stages: list[dict[str, Any]]) -> tuple[str, str]:
    safety_breach_count = sum(safe_int(stage["safety_breach_count"]) for stage in stages)
    blocked_stage_count = sum(1 for stage in stages if stage["stage_status"] == STAGE_BLOCKED)
    attention_stage_count = sum(1 for stage in stages if stage["stage_status"] == STAGE_ATTENTION)

    router_verdict = str(router_result.get("global_verdict", ""))

    if safety_breach_count > 0 or blocked_stage_count > 0:
        return CONTROL_SAFETY_BREACH, RECOMMEND_SAFETY

    if router_verdict == "ALERT_ROUTER_INVALIDATION_REQUIRED_SHADOW_ONLY":
        return CONTROL_INVALIDATION, RECOMMEND_INVALIDATE

    if router_verdict == "ALERT_ROUTER_WARNING_SHADOW_ONLY":
        return CONTROL_WARNING, RECOMMEND_WARN

    if router_verdict == "ALERT_ROUTER_REFRESH_DATA_SHADOW_ONLY":
        return CONTROL_REFRESH_DATA, RECOMMEND_REFRESH

    if router_verdict == "ALERT_ROUTER_CONTINUE_SHADOW_ONLY" and attention_stage_count == 0:
        return CONTROL_CONTINUE, RECOMMEND_CONTINUE

    if attention_stage_count > 0:
        return CONTROL_NEEDS_ATTENTION, RECOMMEND_ATTENTION

    return CONTROL_NEEDS_ATTENTION, RECOMMEND_ATTENTION


def summarize_control_plane(
    db_path: str | Path,
    cycle_label: str,
    report_label: str,
    created_at: str,
    symbols: list[str] | None,
    stages: list[dict[str, Any]],
    documentation_records: list[dict[str, Any]],
    tracking_result: dict[str, Any],
    performance_result: dict[str, Any],
    router_result: dict[str, Any],
) -> dict[str, Any]:
    stage_status_counts = Counter(stage["stage_status"] for stage in stages)

    documentation_ready_count = sum(
        1 for record in documentation_records if record["registry_status"] == "DOCUMENTATION_READY"
    )

    control_verdict, recommended_action = decide_control_plane_verdict(router_result, stages)

    safety_breach_count = sum(safe_int(stage["safety_breach_count"]) for stage in stages)
    safety_breach_count += safe_int(router_result.get("safety_breach_count", 0))

    return {
        "report_label": report_label,
        "cycle_label": cycle_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "symbols": symbols or [],
        "stage_count": len(stages),
        "completed_stage_count": stage_status_counts.get(STAGE_COMPLETED, 0),
        "attention_stage_count": stage_status_counts.get(STAGE_ATTENTION, 0),
        "blocked_stage_count": stage_status_counts.get(STAGE_BLOCKED, 0),
        "stage_status_counts": dict(stage_status_counts),
        "stages": stages,
        "documentation_registry_count": len(documentation_records),
        "documentation_ready_count": documentation_ready_count,
        "documentation_records": documentation_records,
        "tracking_update_count": safe_int(tracking_result.get("tracking_update_count", 0)),
        "active_tracking_count": safe_int(tracking_result.get("active_after_update_count", 0)),
        "tracking_global_verdict": tracking_result.get("global_verdict"),
        "performance_active_count": safe_int(performance_result.get("active_count", 0)),
        "performance_global_verdict": performance_result.get("global_verdict"),
        "average_updated_remaining_carry_bps": safe_float(
            performance_result.get("average_updated_remaining_carry_bps", 0.0)
        ),
        "average_carry_drift_bps": safe_float(performance_result.get("average_carry_drift_bps", 0.0)),
        "route_count": safe_int(router_result.get("route_count", 0)),
        "continue_route_count": safe_int(router_result.get("continue_route_count", 0)),
        "warning_route_count": safe_int(router_result.get("warning_route_count", 0)),
        "invalidation_route_count": safe_int(router_result.get("invalidation_route_count", 0)),
        "refresh_data_route_count": safe_int(router_result.get("refresh_data_route_count", 0)),
        "safety_block_route_count": safe_int(router_result.get("safety_block_route_count", 0)),
        "router_global_verdict": router_result.get("global_verdict"),
        "top_symbol": router_result.get("top_symbol") or performance_result.get("strongest_symbol"),
        "safety_breach_count": safety_breach_count,
        "control_plane_verdict": control_verdict,
        "recommended_action": recommended_action,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    stage_lines = []

    for stage in summary["stages"]:
        stage_lines.append(
            "- "
            + f"{stage['stage_order']}. {stage['stage_name']}: "
            + f"status={stage['stage_status']}, "
            + f"verdict={stage['stage_verdict']}, "
            + f"safety_breach_count={stage['safety_breach_count']}"
        )

    doc_lines = []

    for record in summary["documentation_records"]:
        doc_lines.append(
            "- "
            + f"{record['document_path']}: "
            + f"status={record['registry_status']}, "
            + f"marker_found={bool(record['marker_found'])}"
        )

    stages_markdown = "\n".join(stage_lines) or "- None"
    docs_markdown = "\n".join(doc_lines) or "- None"

    return f"""# DeltaGrid Mission 58 Shadow Research Control Plane Report

Report label: {summary['report_label']}
Cycle label: {summary['cycle_label']}
Created at: {summary['created_at']}
Symbols: {summary['symbols']}

## Control Plane Summary

Stage count: {summary['stage_count']}
Completed stage count: {summary['completed_stage_count']}
Attention stage count: {summary['attention_stage_count']}
Blocked stage count: {summary['blocked_stage_count']}

Tracking update count: {summary['tracking_update_count']}
Active tracking count: {summary['active_tracking_count']}
Performance active count: {summary['performance_active_count']}

Route count: {summary['route_count']}
Continue route count: {summary['continue_route_count']}
Warning route count: {summary['warning_route_count']}
Invalidation route count: {summary['invalidation_route_count']}
Refresh data route count: {summary['refresh_data_route_count']}
Safety block route count: {summary['safety_block_route_count']}
Safety breach count: {summary['safety_breach_count']}

Documentation registry count: {summary['documentation_registry_count']}
Documentation ready count: {summary['documentation_ready_count']}

Top symbol: {summary['top_symbol']}
Average updated remaining carry bps: {summary['average_updated_remaining_carry_bps']}
Average carry drift bps: {summary['average_carry_drift_bps']}

## Stage Runs

{stages_markdown}

## Documentation Registry

{docs_markdown}

## Verdict

Control plane verdict: {summary['control_plane_verdict']}
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


def persist_cycle_report(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO shadow_research_control_plane_cycles (
                report_label,
                cycle_label,
                created_at,
                symbols_csv,
                stage_count,
                completed_stage_count,
                attention_stage_count,
                blocked_stage_count,
                documentation_registry_count,
                documentation_ready_count,
                tracking_update_count,
                active_tracking_count,
                performance_active_count,
                route_count,
                continue_route_count,
                warning_route_count,
                invalidation_route_count,
                refresh_data_route_count,
                safety_block_route_count,
                safety_breach_count,
                top_symbol,
                control_plane_verdict,
                recommended_action,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["report_label"],
                summary["cycle_label"],
                summary["created_at"],
                ",".join(summary["symbols"]),
                summary["stage_count"],
                summary["completed_stage_count"],
                summary["attention_stage_count"],
                summary["blocked_stage_count"],
                summary["documentation_registry_count"],
                summary["documentation_ready_count"],
                summary["tracking_update_count"],
                summary["active_tracking_count"],
                summary["performance_active_count"],
                summary["route_count"],
                summary["continue_route_count"],
                summary["warning_route_count"],
                summary["invalidation_route_count"],
                summary["refresh_data_route_count"],
                summary["safety_block_route_count"],
                summary["safety_breach_count"],
                summary["top_symbol"],
                summary["control_plane_verdict"],
                summary["recommended_action"],
                safe_json(summary),
                markdown_report,
            ),
        )

        conn.commit()


def run_shadow_research_control_plane(
    db_path: str | Path = "offchain/deltagrid.db",
    cycle_label: str | None = None,
    report_label: str | None = None,
    bridge_label: str | None = None,
    market_dataset_label: str | None = None,
    symbols: str | list[str] | tuple[str, ...] | None = None,
    observed_funding_events_increment: int = 1,
    min_latest_funding_bps: float = 0.0,
    min_remaining_net_carry_bps: float = 0.25,
    max_spread_bps: float = 1.0,
    strong_carry_bps: float = 10.0,
    min_continue_carry_bps: float = 10.0,
    max_warning_spread_bps: float = 1.0,
    docs_root: str | Path = "docs",
) -> dict[str, Any]:
    db = Path(db_path)
    label = cycle_label or new_cycle_label()
    report = report_label or new_report_label()
    created_at = utc_now()

    requested_symbols = parse_symbols(symbols)

    ensure_schema(db)

    stages: list[dict[str, Any]] = []

    data_stage = build_data_reuse_stage(
        cycle_label=label,
        report_label=report,
        created_at=created_at,
        market_dataset_label=market_dataset_label,
    )
    stages.append(data_stage)

    tracking_update_label = f"{label}-tracking-update"
    tracking_report_label = f"{report}-tracking-update-report"

    tracking_result = run_shadow_ledger_tracking_updater(
        db_path=db,
        update_label=tracking_update_label,
        report_label=tracking_report_label,
        bridge_label=bridge_label,
        market_dataset_label=market_dataset_label,
        symbols=requested_symbols,
        observed_funding_events_increment=observed_funding_events_increment,
        min_latest_funding_bps=min_latest_funding_bps,
        min_remaining_net_carry_bps=min_remaining_net_carry_bps,
        max_spread_bps=max_spread_bps,
    )

    stages.append(
        make_stage(
            cycle_label=label,
            report_label=report,
            created_at=created_at,
            stage_order=2,
            stage_name="shadow_ledger_tracking_update",
            stage_verdict=str(tracking_result.get("global_verdict")),
            input_payload={
                "bridge_label": bridge_label,
                "market_dataset_label": market_dataset_label,
                "symbols": requested_symbols,
            },
            output_payload=tracking_result,
        )
    )

    performance_label = f"{label}-performance"
    performance_report_label = f"{report}-performance-report"

    performance_result = run_shadow_tracking_performance_reporter(
        db_path=db,
        performance_label=performance_label,
        report_label=performance_report_label,
        update_label=tracking_update_label,
        symbols=requested_symbols,
        strong_carry_bps=strong_carry_bps,
        min_funding_bps=min_latest_funding_bps,
        max_spread_bps=max_spread_bps,
    )

    stages.append(
        make_stage(
            cycle_label=label,
            report_label=report,
            created_at=created_at,
            stage_order=3,
            stage_name="shadow_tracking_performance_report",
            stage_verdict=str(performance_result.get("global_verdict")),
            input_payload={
                "update_label": tracking_update_label,
                "symbols": requested_symbols,
            },
            output_payload=performance_result,
        )
    )

    route_label = f"{label}-alert-router"
    route_report_label = f"{report}-alert-router-report"

    router_result = run_shadow_tracking_alert_invalidation_router(
        db_path=db,
        route_label=route_label,
        report_label=route_report_label,
        performance_label=performance_label,
        symbols=requested_symbols,
        min_continue_carry_bps=min_continue_carry_bps,
        max_warning_spread_bps=max_warning_spread_bps,
    )

    stages.append(
        make_stage(
            cycle_label=label,
            report_label=report,
            created_at=created_at,
            stage_order=4,
            stage_name="shadow_tracking_alert_router",
            stage_verdict=str(router_result.get("global_verdict")),
            input_payload={
                "performance_label": performance_label,
                "symbols": requested_symbols,
            },
            output_payload=router_result,
        )
    )

    documentation_records = build_documentation_registry(
        cycle_label=label,
        created_at=created_at,
        docs_root=docs_root,
    )

    documentation_ready_count = sum(
        1 for record in documentation_records if record["registry_status"] == "DOCUMENTATION_READY"
    )

    doc_stage_verdict = (
        "DOCUMENTATION_REGISTRY_READY"
        if documentation_ready_count == len(documentation_records)
        else "DOCUMENTATION_REGISTRY_INCOMPLETE"
    )

    stages.append(
        make_stage(
            cycle_label=label,
            report_label=report,
            created_at=created_at,
            stage_order=5,
            stage_name="documentation_registry_check",
            stage_verdict=doc_stage_verdict,
            input_payload={"docs_root": str(docs_root)},
            output_payload={
                "documentation_registry_count": len(documentation_records),
                "documentation_ready_count": documentation_ready_count,
                "safety_breach_count": 0,
            },
        )
    )

    persist_stage_runs(db, stages)
    persist_documentation_registry(db, documentation_records)

    summary = summarize_control_plane(
        db_path=db,
        cycle_label=label,
        report_label=report,
        created_at=created_at,
        symbols=requested_symbols,
        stages=stages,
        documentation_records=documentation_records,
        tracking_result=tracking_result,
        performance_result=performance_result,
        router_result=router_result,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_cycle_report(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeltaGrid shadow research control plane."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--cycle-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--bridge-label", default=None)
    parser.add_argument("--market-dataset-label", default=None)
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--observed-funding-events-increment", type=int, default=1)
    parser.add_argument("--min-latest-funding-bps", type=float, default=0.0)
    parser.add_argument("--min-remaining-net-carry-bps", type=float, default=0.25)
    parser.add_argument("--max-spread-bps", type=float, default=1.0)
    parser.add_argument("--strong-carry-bps", type=float, default=10.0)
    parser.add_argument("--min-continue-carry-bps", type=float, default=10.0)
    parser.add_argument("--max-warning-spread-bps", type=float, default=1.0)
    parser.add_argument("--docs-root", default="docs")
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_shadow_research_control_plane(
        db_path=args.db,
        cycle_label=args.cycle_label,
        report_label=args.report_label,
        bridge_label=args.bridge_label,
        market_dataset_label=args.market_dataset_label,
        symbols=args.symbols,
        observed_funding_events_increment=args.observed_funding_events_increment,
        min_latest_funding_bps=args.min_latest_funding_bps,
        min_remaining_net_carry_bps=args.min_remaining_net_carry_bps,
        max_spread_bps=args.max_spread_bps,
        strong_carry_bps=args.strong_carry_bps,
        min_continue_carry_bps=args.min_continue_carry_bps,
        max_warning_spread_bps=args.max_warning_spread_bps,
        docs_root=args.docs_root,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
