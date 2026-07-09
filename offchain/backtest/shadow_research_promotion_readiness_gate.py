"""
Mission 48: Shadow Research Promotion Readiness Gate.

This module converts the executive daily report into a formal promotion
readiness decision.

It is a governance and readiness layer, not an execution layer.

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXECUTIVE_DAILY_REPORTS_TABLE = "shadow_research_executive_daily_reports"
PROMOTION_READINESS_REPORTS_TABLE = "shadow_research_promotion_readiness_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"

NO_EXECUTIVE_HISTORY_VERDICT = "PROMOTION_READINESS_NO_EXECUTIVE_DAILY_HISTORY"
MISSING_EXECUTIVE_TABLE_VERDICT = "PROMOTION_READINESS_EXECUTIVE_DAILY_TABLE_MISSING"
NO_MATCHING_EXECUTIVE_REPORT_VERDICT = "PROMOTION_READINESS_NO_MATCHING_EXECUTIVE_REPORT"
SAFETY_BLOCKED_VERDICT = "PROMOTION_READINESS_SAFETY_BLOCKED"
RISK_REVIEW_VERDICT = "PROMOTION_READINESS_RISK_REVIEW_REQUIRED"
GOVERNANCE_INCOMPLETE_VERDICT = "PROMOTION_READINESS_GOVERNANCE_INCOMPLETE"
APPROVE_ALPHA_BUILDOUT_VERDICT = "PROMOTION_READINESS_APPROVE_ALPHA_BUILDOUT_BLOCK_LIVE_TRADING"
SHADOW_EXPANSION_READY_VERDICT = "PROMOTION_READINESS_SHADOW_EXPANSION_READY_NO_LIVE_TRADING"

DECISION_BLOCKED = "BLOCKED"
DECISION_APPROVE_ALPHA_BUILDOUT_ONLY = "APPROVE_ALPHA_ENGINE_BUILDOUT_ONLY"
DECISION_APPROVE_SHADOW_EXPANSION_ONLY = "APPROVE_SHADOW_RESEARCH_EXPANSION_ONLY"

NEXT_STAGE_ALPHA_BUILDOUT = "REAL_MARKET_ALPHA_ENGINE_BUILDOUT"
NEXT_STAGE_SHADOW_EXPANSION = "EXPANDED_SHADOW_RESEARCH_ONLY"
NEXT_STAGE_NONE = "NO_PROMOTION"

RECOMMEND_ALPHA_BUILDOUT = "BUILD_REAL_MARKET_ALPHA_ENGINE_CONTINUE_SHADOW_ONLY"
RECOMMEND_REVIEW_RISK = "REVIEW_RISK_OR_SAFETY_BEFORE_PROMOTION"
RECOMMEND_RUN_EXECUTIVE_DAILY = "RUN_MISSION_47_EXECUTIVE_DAILY_REPORT"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_readiness_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission48-promotion-readiness-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission48-report-{stamp}-{uuid.uuid4().hex[:8]}"


def safe_json_loads(value: str | None, fallback: Any) -> Any:
    if value is None:
        return fallback

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


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
            CREATE TABLE IF NOT EXISTS shadow_research_promotion_readiness_reports (
                report_label TEXT PRIMARY KEY,
                readiness_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_daily_label TEXT,
                source_daily_report_label TEXT,
                source_report_section_count INTEGER NOT NULL,
                present_section_count INTEGER NOT NULL,
                safety_issue_count INTEGER NOT NULL,
                risk_review_count INTEGER NOT NULL,
                promotion_readiness_decision TEXT NOT NULL,
                approved_next_stage TEXT NOT NULL,
                live_trading_decision TEXT NOT NULL,
                capital_deployment_decision TEXT NOT NULL,
                blocker_count INTEGER NOT NULL,
                evidence_check_count INTEGER NOT NULL,
                passed_evidence_check_count INTEGER NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                blockers_json TEXT NOT NULL,
                evidence_checks_json TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.commit()


def latest_executive_daily_row(conn: sqlite3.Connection) -> sqlite3.Row | None:
    row = conn.execute(
        """
        SELECT *
        FROM shadow_research_executive_daily_reports
        ORDER BY created_at DESC, report_label DESC
        LIMIT 1
        """
    ).fetchone()

    return row


def load_executive_daily_row(
    conn: sqlite3.Connection,
    daily_label: str | None,
    report_label: str | None,
) -> sqlite3.Row | None:
    if report_label:
        return conn.execute(
            """
            SELECT *
            FROM shadow_research_executive_daily_reports
            WHERE report_label = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (report_label,),
        ).fetchone()

    if daily_label:
        return conn.execute(
            """
            SELECT *
            FROM shadow_research_executive_daily_reports
            WHERE daily_label = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (daily_label,),
        ).fetchone()

    return latest_executive_daily_row(conn)


def section_by_table(summary: dict[str, Any], table_name: str) -> dict[str, Any] | None:
    for section in summary.get("sections", []):
        if section.get("table_name") == table_name:
            return section

    return None


def metric_from_section(
    summary: dict[str, Any],
    table_name: str,
    key: str,
    default: Any = None,
) -> Any:
    section = section_by_table(summary, table_name)

    if section is None:
        return default

    metrics = section.get("metrics") or {}

    if key in metrics:
        return metrics[key]

    latest_row = section.get("latest_row") or {}

    return latest_row.get(key, default)


def build_evidence_checks(
    row: sqlite3.Row,
    summary: dict[str, Any],
    min_required_sections: int,
) -> list[dict[str, Any]]:
    source_report_section_count = safe_int(row["source_report_section_count"])
    present_section_count = safe_int(row["present_section_count"])
    safety_issue_count = safe_int(row["safety_issue_count"])
    risk_review_count = safe_int(row["risk_review_count"])

    live_trading_status = str(row["live_trading_status"])
    capital_deployment_status = str(row["capital_deployment_status"])

    total_net_expected = safe_float(
        metric_from_section(
            summary,
            "shadow_observation_outcome_analytics_reports",
            "total_net_expected_pnl_usd",
            0.0,
        )
    )
    close_ready_count = safe_int(
        metric_from_section(
            summary,
            "shadow_observation_outcome_analytics_reports",
            "close_ready_count",
            0,
        )
    )
    negative_count = safe_int(
        metric_from_section(
            summary,
            "shadow_observation_pnl_attribution_reports",
            "negative_count",
            0,
        )
    )
    continued_count = safe_int(
        metric_from_section(
            summary,
            "shadow_observation_outcome_analytics_reports",
            "continued_count",
            0,
        )
    )

    return [
        {
            "name": "executive_daily_report_exists",
            "passed": True,
            "value": row["report_label"],
            "required": "existing executive daily report",
            "category": "governance",
        },
        {
            "name": "minimum_report_sections_present",
            "passed": present_section_count >= min_required_sections,
            "value": present_section_count,
            "required": min_required_sections,
            "category": "governance",
        },
        {
            "name": "source_report_sections_discovered",
            "passed": source_report_section_count >= min_required_sections,
            "value": source_report_section_count,
            "required": min_required_sections,
            "category": "governance",
        },
        {
            "name": "no_safety_issues",
            "passed": safety_issue_count == 0,
            "value": safety_issue_count,
            "required": 0,
            "category": "safety",
        },
        {
            "name": "no_risk_reviews",
            "passed": risk_review_count == 0,
            "value": risk_review_count,
            "required": 0,
            "category": "risk",
        },
        {
            "name": "live_trading_disabled",
            "passed": live_trading_status == LIVE_TRADING_STATUS,
            "value": live_trading_status,
            "required": LIVE_TRADING_STATUS,
            "category": "safety",
        },
        {
            "name": "capital_deployment_blocked",
            "passed": capital_deployment_status == CAPITAL_DEPLOYMENT_STATUS,
            "value": capital_deployment_status,
            "required": CAPITAL_DEPLOYMENT_STATUS,
            "category": "safety",
        },
        {
            "name": "positive_cost_adjusted_edge_proven",
            "passed": total_net_expected > 0,
            "value": total_net_expected,
            "required": "greater than 0",
            "category": "profitability",
        },
        {
            "name": "close_ready_observations_present",
            "passed": close_ready_count > 0,
            "value": close_ready_count,
            "required": "greater than 0",
            "category": "profitability",
        },
        {
            "name": "negative_expected_observations_absent",
            "passed": negative_count == 0,
            "value": negative_count,
            "required": 0,
            "category": "profitability",
        },
        {
            "name": "shadow_observations_exist",
            "passed": continued_count > 0 or close_ready_count > 0,
            "value": {
                "continued_count": continued_count,
                "close_ready_count": close_ready_count,
            },
            "required": "at least one shadow observation",
            "category": "research",
        },
    ]


def build_blockers(evidence_checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blockers = []

    for check in evidence_checks:
        if check["passed"]:
            continue

        blockers.append(
            {
                "name": check["name"],
                "category": check["category"],
                "value": check["value"],
                "required": check["required"],
                "message": f"{check['name']} failed: value={check['value']} required={check['required']}",
            }
        )

    return blockers


def classify_readiness(
    row: sqlite3.Row,
    evidence_checks: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
) -> dict[str, str]:
    safety_failed = any(
        check["category"] == "safety" and not check["passed"]
        for check in evidence_checks
    )
    risk_failed = any(
        check["category"] == "risk" and not check["passed"]
        for check in evidence_checks
    )
    governance_failed = any(
        check["category"] == "governance" and not check["passed"]
        for check in evidence_checks
    )
    profitability_failed = any(
        check["category"] == "profitability" and not check["passed"]
        for check in evidence_checks
    )

    if safety_failed:
        return {
            "promotion_readiness_decision": DECISION_BLOCKED,
            "approved_next_stage": NEXT_STAGE_NONE,
            "live_trading_decision": DECISION_BLOCKED,
            "capital_deployment_decision": DECISION_BLOCKED,
            "global_verdict": SAFETY_BLOCKED_VERDICT,
            "recommended_action": RECOMMEND_REVIEW_RISK,
        }

    if risk_failed:
        return {
            "promotion_readiness_decision": DECISION_BLOCKED,
            "approved_next_stage": NEXT_STAGE_NONE,
            "live_trading_decision": DECISION_BLOCKED,
            "capital_deployment_decision": DECISION_BLOCKED,
            "global_verdict": RISK_REVIEW_VERDICT,
            "recommended_action": RECOMMEND_REVIEW_RISK,
        }

    if governance_failed:
        return {
            "promotion_readiness_decision": DECISION_BLOCKED,
            "approved_next_stage": NEXT_STAGE_NONE,
            "live_trading_decision": DECISION_BLOCKED,
            "capital_deployment_decision": DECISION_BLOCKED,
            "global_verdict": GOVERNANCE_INCOMPLETE_VERDICT,
            "recommended_action": RECOMMEND_RUN_EXECUTIVE_DAILY,
        }

    if profitability_failed:
        return {
            "promotion_readiness_decision": DECISION_APPROVE_ALPHA_BUILDOUT_ONLY,
            "approved_next_stage": NEXT_STAGE_ALPHA_BUILDOUT,
            "live_trading_decision": DECISION_BLOCKED,
            "capital_deployment_decision": DECISION_BLOCKED,
            "global_verdict": APPROVE_ALPHA_BUILDOUT_VERDICT,
            "recommended_action": RECOMMEND_ALPHA_BUILDOUT,
        }

    return {
        "promotion_readiness_decision": DECISION_APPROVE_SHADOW_EXPANSION_ONLY,
        "approved_next_stage": NEXT_STAGE_SHADOW_EXPANSION,
        "live_trading_decision": DECISION_BLOCKED,
        "capital_deployment_decision": DECISION_BLOCKED,
        "global_verdict": SHADOW_EXPANSION_READY_VERDICT,
        "recommended_action": "EXPAND_SHADOW_RESEARCH_NO_LIVE_TRADING",
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    checks_lines = []

    for check in summary["evidence_checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        checks_lines.append(
            f"- {status}: {check['name']} "
            f"(value={check['value']}, required={check['required']})"
        )

    checks_markdown = "\n".join(checks_lines) or "- None"

    blocker_lines = []

    for blocker in summary["blockers"]:
        blocker_lines.append(
            f"- {blocker['category']}: {blocker['name']} "
            f"(value={blocker['value']}, required={blocker['required']})"
        )

    blockers_markdown = "\n".join(blocker_lines) or "- None"

    return f"""# DeltaGrid Mission 48 Shadow Research Promotion Readiness Report

Report label: {summary['report_label']}
Readiness label: {summary['readiness_label']}
Created at: {summary['created_at']}

Source daily label: {summary['source_daily_label']}
Source daily report label: {summary['source_daily_report_label']}

## Promotion Readiness Summary

Source report section count: {summary['source_report_section_count']}
Present section count: {summary['present_section_count']}
Safety issue count: {summary['safety_issue_count']}
Risk review count: {summary['risk_review_count']}

Promotion readiness decision: {summary['promotion_readiness_decision']}
Approved next stage: {summary['approved_next_stage']}
Live trading decision: {summary['live_trading_decision']}
Capital deployment decision: {summary['capital_deployment_decision']}

Evidence check count: {summary['evidence_check_count']}
Passed evidence check count: {summary['passed_evidence_check_count']}
Blocker count: {summary['blocker_count']}

## Evidence Checks

{checks_markdown}

## Blockers

{blockers_markdown}

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
"""


def persist_report(
    db_path: str | Path,
    summary: dict[str, Any],
    markdown_report: str,
) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO shadow_research_promotion_readiness_reports (
                report_label,
                readiness_label,
                created_at,
                source_daily_label,
                source_daily_report_label,
                source_report_section_count,
                present_section_count,
                safety_issue_count,
                risk_review_count,
                promotion_readiness_decision,
                approved_next_stage,
                live_trading_decision,
                capital_deployment_decision,
                blocker_count,
                evidence_check_count,
                passed_evidence_check_count,
                global_verdict,
                recommended_action,
                blockers_json,
                evidence_checks_json,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["report_label"],
                summary["readiness_label"],
                summary["created_at"],
                summary["source_daily_label"],
                summary["source_daily_report_label"],
                summary["source_report_section_count"],
                summary["present_section_count"],
                summary["safety_issue_count"],
                summary["risk_review_count"],
                summary["promotion_readiness_decision"],
                summary["approved_next_stage"],
                summary["live_trading_decision"],
                summary["capital_deployment_decision"],
                summary["blocker_count"],
                summary["evidence_check_count"],
                summary["passed_evidence_check_count"],
                summary["global_verdict"],
                summary["recommended_action"],
                json.dumps(summary["blockers"], sort_keys=True),
                json.dumps(summary["evidence_checks"], sort_keys=True),
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.commit()


def summarize_readiness(
    db_path: str | Path,
    readiness_label: str,
    report_label: str,
    created_at: str,
    row: sqlite3.Row,
    min_required_sections: int,
) -> dict[str, Any]:
    executive_summary = safe_json_loads(row["summary_json"], {})

    evidence_checks = build_evidence_checks(
        row=row,
        summary=executive_summary,
        min_required_sections=min_required_sections,
    )
    blockers = build_blockers(evidence_checks)
    classification = classify_readiness(
        row=row,
        evidence_checks=evidence_checks,
        blockers=blockers,
    )

    passed_count = sum(1 for check in evidence_checks if check["passed"])

    return {
        "report_label": report_label,
        "readiness_label": readiness_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_daily_label": row["daily_label"],
        "source_daily_report_label": row["report_label"],
        "source_report_section_count": safe_int(row["source_report_section_count"]),
        "present_section_count": safe_int(row["present_section_count"]),
        "safety_issue_count": safe_int(row["safety_issue_count"]),
        "risk_review_count": safe_int(row["risk_review_count"]),
        "promotion_readiness_decision": classification["promotion_readiness_decision"],
        "approved_next_stage": classification["approved_next_stage"],
        "live_trading_decision": classification["live_trading_decision"],
        "capital_deployment_decision": classification["capital_deployment_decision"],
        "blocker_count": len(blockers),
        "evidence_check_count": len(evidence_checks),
        "passed_evidence_check_count": passed_count,
        "global_verdict": classification["global_verdict"],
        "recommended_action": classification["recommended_action"],
        "blockers": blockers,
        "evidence_checks": evidence_checks,
        "source_executive_global_verdict": row["global_verdict"],
        "source_executive_recommended_action": row["recommended_action"],
    }


def run_shadow_research_promotion_readiness_gate(
    db_path: str | Path = "offchain/deltagrid.db",
    readiness_label: str | None = None,
    report_label: str | None = None,
    daily_label: str | None = None,
    daily_report_label: str | None = None,
    min_required_sections: int = 9,
) -> dict[str, Any]:
    db = Path(db_path)
    label = readiness_label or new_readiness_label()
    report = report_label or new_report_label()
    created_at = utc_now()

    if min_required_sections <= 0:
        raise ValueError("min_required_sections must be greater than 0")

    if not db.exists():
        summary = {
            "report_label": report,
            "readiness_label": label,
            "created_at": created_at,
            "db_path": str(db),
            "database_exists": False,
            "tables_present": False,
            "source_daily_label": daily_label,
            "source_daily_report_label": daily_report_label,
            "source_report_section_count": 0,
            "present_section_count": 0,
            "safety_issue_count": 0,
            "risk_review_count": 0,
            "promotion_readiness_decision": DECISION_BLOCKED,
            "approved_next_stage": NEXT_STAGE_NONE,
            "live_trading_decision": DECISION_BLOCKED,
            "capital_deployment_decision": DECISION_BLOCKED,
            "blocker_count": 1,
            "evidence_check_count": 0,
            "passed_evidence_check_count": 0,
            "global_verdict": NO_EXECUTIVE_HISTORY_VERDICT,
            "recommended_action": RECOMMEND_RUN_EXECUTIVE_DAILY,
            "blockers": [
                {
                    "name": "executive_daily_database_missing",
                    "category": "governance",
                    "value": str(db),
                    "required": "existing database",
                    "message": "Executive daily database history is missing.",
                }
            ],
            "evidence_checks": [],
        }
        summary["markdown_report"] = build_markdown_report(summary)
        return summary

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        if not table_exists(conn, EXECUTIVE_DAILY_REPORTS_TABLE):
            summary = {
                "report_label": report,
                "readiness_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "tables_present": False,
                "missing_tables": [EXECUTIVE_DAILY_REPORTS_TABLE],
                "source_daily_label": daily_label,
                "source_daily_report_label": daily_report_label,
                "source_report_section_count": 0,
                "present_section_count": 0,
                "safety_issue_count": 0,
                "risk_review_count": 0,
                "promotion_readiness_decision": DECISION_BLOCKED,
                "approved_next_stage": NEXT_STAGE_NONE,
                "live_trading_decision": DECISION_BLOCKED,
                "capital_deployment_decision": DECISION_BLOCKED,
                "blocker_count": 1,
                "evidence_check_count": 0,
                "passed_evidence_check_count": 0,
                "global_verdict": MISSING_EXECUTIVE_TABLE_VERDICT,
                "recommended_action": RECOMMEND_RUN_EXECUTIVE_DAILY,
                "blockers": [
                    {
                        "name": "executive_daily_report_table_missing",
                        "category": "governance",
                        "value": EXECUTIVE_DAILY_REPORTS_TABLE,
                        "required": "existing executive daily report table",
                        "message": "Mission 47 executive daily report table is missing.",
                    }
                ],
                "evidence_checks": [],
            }
            summary["markdown_report"] = build_markdown_report(summary)
            persist_report(db, summary, summary["markdown_report"])
            return summary

        row = load_executive_daily_row(
            conn=conn,
            daily_label=daily_label,
            report_label=daily_report_label,
        )

    if row is None:
        summary = {
            "report_label": report,
            "readiness_label": label,
            "created_at": created_at,
            "db_path": str(db),
            "database_exists": True,
            "tables_present": True,
            "source_daily_label": daily_label,
            "source_daily_report_label": daily_report_label,
            "source_report_section_count": 0,
            "present_section_count": 0,
            "safety_issue_count": 0,
            "risk_review_count": 0,
            "promotion_readiness_decision": DECISION_BLOCKED,
            "approved_next_stage": NEXT_STAGE_NONE,
            "live_trading_decision": DECISION_BLOCKED,
            "capital_deployment_decision": DECISION_BLOCKED,
            "blocker_count": 1,
            "evidence_check_count": 0,
            "passed_evidence_check_count": 0,
            "global_verdict": NO_MATCHING_EXECUTIVE_REPORT_VERDICT,
            "recommended_action": RECOMMEND_RUN_EXECUTIVE_DAILY,
            "blockers": [
                {
                    "name": "matching_executive_daily_report_missing",
                    "category": "governance",
                    "value": {
                        "daily_label": daily_label,
                        "daily_report_label": daily_report_label,
                    },
                    "required": "matching executive daily report",
                    "message": "No matching executive daily report was found.",
                }
            ],
            "evidence_checks": [],
        }
        summary["markdown_report"] = build_markdown_report(summary)
        persist_report(db, summary, summary["markdown_report"])
        return summary

    summary = summarize_readiness(
        db_path=db,
        readiness_label=label,
        report_label=report,
        created_at=created_at,
        row=row,
        min_required_sections=min_required_sections,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_report(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeltaGrid shadow research promotion readiness gate."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--readiness-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--daily-label", default=None)
    parser.add_argument("--daily-report-label", default=None)
    parser.add_argument("--min-required-sections", type=int, default=9)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_shadow_research_promotion_readiness_gate(
        db_path=args.db,
        readiness_label=args.readiness_label,
        report_label=args.report_label,
        daily_label=args.daily_label,
        daily_report_label=args.daily_report_label,
        min_required_sections=args.min_required_sections,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
