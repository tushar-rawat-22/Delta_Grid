"""Read persisted operational evidence without starting any trading machinery.

This inspector is deliberately narrower than the historical paper modules. It
opens an existing SQLite database read-only, verifies the persisted control
rows used by the operational release gate, and reduces those rows to one
operator verdict.

It never creates a database or table, invokes a paper/risk/capital/kill-switch
runner, connects to an exchange, transmits an order, enables trading, or grants
capital authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping
from urllib.parse import quote

from offchain.safety.operational_release_gate import (
    BLOCKED,
    evaluate_operational_release,
)


@dataclass(frozen=True)
class EvidenceSource:
    name: str
    table: str
    label_column: str
    critical_columns: tuple[str, ...]


COMMON_COLUMNS = (
    "created_at",
    "global_verdict",
    "live_trading",
    "live_order_sent",
    "capital_deployment",
    "safety_breach_count",
    "summary_json",
)

SOURCES = (
    EvidenceSource(
        name="paper",
        table="paper_sandbox_sessions",
        label_column="session_label",
        critical_columns=COMMON_COLUMNS,
    ),
    EvidenceSource(
        name="risk",
        table="institutional_risk_control_reviews",
        label_column="review_label",
        critical_columns=COMMON_COLUMNS + ("risk_decision",),
    ),
    EvidenceSource(
        name="capital",
        table="capital_readiness_reviews",
        label_column="review_label",
        critical_columns=COMMON_COLUMNS + ("capital_decision",),
    ),
    EvidenceSource(
        name="kill_switch",
        table="paper_drawdown_kill_switch_reviews",
        label_column="review_label",
        critical_columns=COMMON_COLUMNS + ("kill_switch_decision", "kill_switch_state"),
    ),
)


class InspectionError(RuntimeError):
    """Raised for malformed or contradictory persisted readiness evidence."""


class _DuplicateKey(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateKey(key)
        value[key] = item
    return value


def _reject_nonfinite(_raw: str) -> Any:
    raise ValueError("NONFINITE_JSON_NUMBER")


def _strict_json_object(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, str):
        raise InspectionError("SUMMARY_JSON_NOT_TEXT")
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (json.JSONDecodeError, ValueError, TypeError) as error:
        raise InspectionError("SUMMARY_JSON_INVALID") from error
    if not isinstance(value, dict):
        raise InspectionError("SUMMARY_JSON_NOT_OBJECT")
    return value


def _open_readonly(database_path: Path) -> sqlite3.Connection:
    if database_path.is_symlink() or not database_path.is_file():
        raise InspectionError("DATABASE_MISSING_OR_INVALID")

    resolved = database_path.resolve(strict=True)
    uri = f"file:{quote(str(resolved), safe='/')}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as error:
        raise InspectionError("DATABASE_READONLY_OPEN_FAILED") from error

    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        query_only = connection.execute("PRAGMA query_only").fetchone()
        if query_only is None or int(query_only[0]) != 1:
            raise InspectionError("DATABASE_QUERY_ONLY_NOT_ENFORCED")
    except Exception:
        connection.close()
        raise
    return connection


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if exists is None:
        raise InspectionError(f"{table}:TABLE_MISSING")

    rows = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    return {str(row[1]) for row in rows}


def _critical_value_matches(column: str, persisted: Any, summary: Mapping[str, Any]) -> bool:
    if column not in summary:
        return False
    candidate = summary[column]
    if column in {"live_order_sent", "safety_breach_count"}:
        return type(candidate) is int and type(persisted) is int and candidate == persisted
    return candidate == persisted


def _load_source(
    connection: sqlite3.Connection,
    source: EvidenceSource,
) -> tuple[dict[str, Any], dict[str, Any]]:
    required = {source.label_column, *source.critical_columns}
    columns = _table_columns(connection, source.table)
    missing = sorted(required - columns)
    if missing:
        raise InspectionError(f"{source.table}:COLUMN_MISSING:{','.join(missing)}")

    selected = (source.label_column, *source.critical_columns)
    select_sql = ", ".join(f'"{column}"' for column in selected)
    row = connection.execute(
        f'SELECT {select_sql} FROM "{source.table}" '
        f'ORDER BY "created_at" DESC, "{source.label_column}" DESC LIMIT 1'
    ).fetchone()
    if row is None:
        raise InspectionError(f"{source.table}:ROW_MISSING")

    summary = _strict_json_object(row["summary_json"])
    for column in source.critical_columns:
        if column == "summary_json":
            continue
        if not _critical_value_matches(column, row[column], summary):
            raise InspectionError(f"{source.table}:SUMMARY_CONTRADICTION:{column}")

    provenance = {
        "table": source.table,
        "row_label": str(row[source.label_column]),
        "created_at": str(row["created_at"]),
        "status": "VERIFIED_READ_ONLY",
    }
    return summary, provenance


def inspect_operational_readiness(db_path: str | Path) -> dict[str, Any]:
    """Inspect the newest persisted control rows and return a fail-closed verdict."""

    path = Path(db_path)
    summaries: dict[str, dict[str, Any] | None] = {source.name: None for source in SOURCES}
    provenance: dict[str, dict[str, Any]] = {}
    inspector_blockers: list[str] = []

    try:
        connection = _open_readonly(path)
    except InspectionError as error:
        inspector_blockers.append(str(error))
        report = evaluate_operational_release(
            paper=None,
            risk=None,
            capital=None,
            kill_switch=None,
        )
        return _build_output(report, provenance, inspector_blockers)

    try:
        for source in SOURCES:
            try:
                summary, source_provenance = _load_source(connection, source)
                summaries[source.name] = summary
                provenance[source.name] = source_provenance
            except (InspectionError, sqlite3.Error) as error:
                inspector_blockers.append(f"{source.name}:{error}")
                provenance[source.name] = {
                    "table": source.table,
                    "status": "INVALID_OR_MISSING",
                }
    finally:
        connection.close()

    report = evaluate_operational_release(
        paper=summaries["paper"],
        risk=summaries["risk"],
        capital=summaries["capital"],
        kill_switch=summaries["kill_switch"],
    )
    return _build_output(report, provenance, inspector_blockers)


def _build_output(
    report: Any,
    provenance: Mapping[str, Mapping[str, Any]],
    inspector_blockers: list[str],
) -> dict[str, Any]:
    release = asdict(report)
    if inspector_blockers:
        release["status"] = BLOCKED
        release["ready_for_extended_paper"] = False

    return {
        "inspection_status": "VERIFIED" if not inspector_blockers else "BLOCKED",
        "release": release,
        "inspector_blockers": tuple(inspector_blockers),
        "sources": dict(provenance),
        "authority_effect": "NONE",
        "live_trading_allowed": False,
        "exchange_access_allowed": False,
        "capital_deployment_allowed": False,
        "database_mode": "READ_ONLY_QUERY_ONLY",
    }
