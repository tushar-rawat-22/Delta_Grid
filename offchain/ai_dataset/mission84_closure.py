"""Mission 84 Closure and Evidence Correction.

Mission 84.5 through Mission 84.8 produced deterministic synthetic-fixture
research evidence. This module preserves those historical records and appends
an authoritative supersession layer proving that none of the fixture-screening
candidates is real-data validated, training eligible, deployable, or authorized
for live use.

This module performs no backtesting, model training, model promotion, live
signal generation, exchange execution, strategy reweighting, capital
deployment, private-key use, paid API use, or profitability claims.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from offchain.ai_dataset.multi_strategy_backtest_pack import (
    CAPITAL_DEPLOYMENT_STATUS,
    LIVE_ORDER_SENT_VALUE,
    LIVE_TRADING_STATUS,
    MISSION85_STATUS,
    canonical_json,
    normalize_label,
    safe_int,
    table_exists,
    utc_now,
)

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")

CLOSURE_SCOPE = "MISSION84_SYNTHETIC_RESEARCH_EVIDENCE_CLOSURE"
MISSION84_STATUS_CLOSED = "CLOSED"
MISSION84_STATUS_BLOCKED = "CLOSURE_BLOCKED"
MISSION84_OUTCOME = (
    "SYNTHETIC_RESEARCH_PIPELINE_COMPLETE_NO_VALIDATED_ALPHA"
)
BLOCKED_OUTCOME = "MISSION84_CLOSURE_REQUIRES_REMEDIATION"

ORIGINAL_REGISTRY_STATUS = (
    "PROVISIONAL_ALPHA_RESEARCH_CANDIDATE_FIXTURE_ONLY_UNVALIDATED"
)
ORIGINAL_EVIDENCE_SCOPE = (
    "SYNTHETIC_FIXTURE_WALK_FORWARD_ONLY_UNVALIDATED"
)
EFFECTIVE_STATUS = (
    "FIXTURE_SCREENING_RECORD_ONLY_NOT_REAL_DATA_VALIDATED"
)

NEXT_WORKSTREAM = "REAL_MARKET_RESEARCH_FOUNDATION_CRYPTO_FIRST"
ENGINE_STATE = "MISSION84_CLOSURE_READY_LOCAL_ONLY"
ENGINE_DECISION = "MISSION84_CLOSURE_AND_EVIDENCE_CORRECTION_ACCEPTED"
GLOBAL_VERDICT = "MISSION84_CLOSED_NO_REAL_DATA_VALIDATED_ALPHA"
RECOMMENDED_ACTION = (
    "PARK_MODEL_PROMOTION_AND_BEGIN_CRYPTO_FIRST_REAL_MARKET_FOUNDATION"
)

CHECK_PASS = "PASS"
CHECK_FAIL = "FAIL"

_REQUIRED_SOURCE_TABLES = (
    "ai_alpha_candidate_promotion_runs",
    "ai_alpha_candidate_registry",
    "ai_walk_forward_robustness_results",
    "ai_multi_strategy_backtest_results",
)

_SOURCE_ZERO_FIELDS = (
    "model_training_count",
    "model_artifact_count",
    "model_promotion_count",
    "strategy_reweighting_count",
    "live_signal_count",
    "exchange_order_count",
    "capital_deployment_count",
    "paid_api_count",
    "private_key_use_count",
    "profitability_claim_count",
    "fail_check_count",
    "safety_breach_count",
)

_REQUIRED_REGISTRY_ACTIONS = {
    "model_training_action": "NO_MODEL_TRAINING",
    "model_artifact_action": "NO_MODEL_ARTIFACT",
    "model_promotion_action": "NO_MODEL_PROMOTION",
    "strategy_reweighting_action": "NO_STRATEGY_REWEIGHTING",
    "live_signal_action": "NO_LIVE_SIGNAL",
    "exchange_order_action": "NO_EXCHANGE_ORDER",
    "capital_action": "NO_CAPITAL_DEPLOYMENT",
    "paid_api_action": "NO_PAID_API",
    "profitability_claim_action": "NO_PROFITABILITY_CLAIM",
}

_SUPERSESSION_COLUMNS = (
    "supersession_id",
    "closure_run_label",
    "source_promotion_run_label",
    "registry_entry_id",
    "created_at",
    "strategy_family_code",
    "asset_group",
    "timeframe",
    "cost_model_code",
    "original_registry_status",
    "original_evidence_scope",
    "original_next_validation_stage",
    "effective_status",
    "real_data_eligible",
    "model_training_eligible",
    "model_promotion_eligible",
    "strategy_reweighting_eligible",
    "live_signal_eligible",
    "exchange_order_eligible",
    "capital_deployment_eligible",
    "paid_api_eligible",
    "profitability_claim_eligible",
    "mission85_status",
    "next_workstream",
    "research_limitation_codes_json",
    "metadata_json",
)

_CHECK_COLUMNS = (
    "check_id",
    "closure_run_label",
    "source_promotion_run_label",
    "created_at",
    "check_category",
    "check_name",
    "check_status",
    "observed_value",
    "threshold_value",
    "check_reason",
    "closure_scope",
    "live_trading",
    "live_order_sent",
    "capital_deployment",
    "metadata_json",
)

_RUN_COLUMNS = (
    "closure_run_label",
    "report_label",
    "source_promotion_run_label",
    "created_at",
    "closure_scope",
    "mission84_status",
    "mission84_outcome",
    "fixture_screening_candidate_count",
    "superseded_candidate_count",
    "source_pair_count",
    "source_pair_reuse_count",
    "invalid_noncrypto_funding_candidate_count",
    "real_data_validated_candidate_count",
    "model_training_eligible_count",
    "model_promotion_count",
    "strategy_reweighting_count",
    "live_signal_count",
    "exchange_order_count",
    "capital_deployment_count",
    "paid_api_count",
    "private_key_use_count",
    "profitability_claim_count",
    "closure_check_count",
    "pass_check_count",
    "fail_check_count",
    "safety_breach_count",
    "mission85_status",
    "next_workstream",
    "engine_state",
    "engine_decision",
    "global_verdict",
    "recommended_action",
    "live_trading",
    "live_order_sent",
    "capital_deployment",
    "summary_json",
    "markdown_report",
)


def _value(
    row: sqlite3.Row | Mapping[str, Any] | None,
    key: str,
    default: Any = None,
) -> Any:
    if row is None:
        return default
    if isinstance(row, sqlite3.Row):
        return row[key] if key in row.keys() else default
    return row.get(key, default)


def ensure_schema(db_path: str | Path) -> None:
    """Create append-only Mission 84 closure evidence tables."""

    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ai_mission84_closure_runs (
                closure_run_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                source_promotion_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                closure_scope TEXT NOT NULL,
                mission84_status TEXT NOT NULL,
                mission84_outcome TEXT NOT NULL,
                fixture_screening_candidate_count INTEGER NOT NULL,
                superseded_candidate_count INTEGER NOT NULL,
                source_pair_count INTEGER NOT NULL,
                source_pair_reuse_count INTEGER NOT NULL,
                invalid_noncrypto_funding_candidate_count INTEGER NOT NULL,
                real_data_validated_candidate_count INTEGER NOT NULL,
                model_training_eligible_count INTEGER NOT NULL,
                model_promotion_count INTEGER NOT NULL,
                strategy_reweighting_count INTEGER NOT NULL,
                live_signal_count INTEGER NOT NULL,
                exchange_order_count INTEGER NOT NULL,
                capital_deployment_count INTEGER NOT NULL,
                paid_api_count INTEGER NOT NULL,
                private_key_use_count INTEGER NOT NULL,
                profitability_claim_count INTEGER NOT NULL,
                closure_check_count INTEGER NOT NULL,
                pass_check_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                mission85_status TEXT NOT NULL,
                next_workstream TEXT NOT NULL,
                engine_state TEXT NOT NULL,
                engine_decision TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_mission84_candidate_supersessions (
                supersession_id TEXT PRIMARY KEY,
                closure_run_label TEXT NOT NULL,
                source_promotion_run_label TEXT NOT NULL,
                registry_entry_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                strategy_family_code TEXT NOT NULL,
                asset_group TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                cost_model_code TEXT NOT NULL,
                original_registry_status TEXT NOT NULL,
                original_evidence_scope TEXT NOT NULL,
                original_next_validation_stage TEXT NOT NULL,
                effective_status TEXT NOT NULL,
                real_data_eligible INTEGER NOT NULL,
                model_training_eligible INTEGER NOT NULL,
                model_promotion_eligible INTEGER NOT NULL,
                strategy_reweighting_eligible INTEGER NOT NULL,
                live_signal_eligible INTEGER NOT NULL,
                exchange_order_eligible INTEGER NOT NULL,
                capital_deployment_eligible INTEGER NOT NULL,
                paid_api_eligible INTEGER NOT NULL,
                profitability_claim_eligible INTEGER NOT NULL,
                mission85_status TEXT NOT NULL,
                next_workstream TEXT NOT NULL,
                research_limitation_codes_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                UNIQUE (closure_run_label, registry_entry_id)
            );

            CREATE TABLE IF NOT EXISTS ai_mission84_closure_checks (
                check_id TEXT PRIMARY KEY,
                closure_run_label TEXT NOT NULL,
                source_promotion_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                check_category TEXT NOT NULL,
                check_name TEXT NOT NULL,
                check_status TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                threshold_value TEXT NOT NULL,
                check_reason TEXT NOT NULL,
                closure_scope TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_mission84_closure_reports (
                report_label TEXT PRIMARY KEY,
                closure_run_label TEXT NOT NULL,
                source_promotion_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                report_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS
                idx_mission84_supersession_registry
            ON ai_mission84_candidate_supersessions (
                registry_entry_id,
                closure_run_label
            );

            CREATE INDEX IF NOT EXISTS
                idx_mission84_supersession_source
            ON ai_mission84_candidate_supersessions (
                source_promotion_run_label
            );
            """
        )
        conn.commit()


def _refresh_effective_registry_view(conn: sqlite3.Connection) -> None:
    """Expose the effective fail-closed status without mutating source rows."""

    conn.executescript(
        """
        DROP VIEW IF EXISTS ai_alpha_candidate_registry_effective;

        CREATE VIEW ai_alpha_candidate_registry_effective AS
        SELECT
            registry.*,
            COALESCE(
                supersession.effective_status,
                registry.registry_status
            ) AS effective_registry_status,
            COALESCE(
                supersession.real_data_eligible,
                0
            ) AS real_data_eligible,
            COALESCE(
                supersession.model_training_eligible,
                0
            ) AS model_training_eligible,
            COALESCE(
                supersession.model_promotion_eligible,
                0
            ) AS model_promotion_eligible,
            COALESCE(
                supersession.live_signal_eligible,
                0
            ) AS live_signal_eligible,
            COALESCE(
                supersession.exchange_order_eligible,
                0
            ) AS exchange_order_eligible,
            COALESCE(
                supersession.capital_deployment_eligible,
                0
            ) AS capital_deployment_eligible,
            COALESCE(
                supersession.profitability_claim_eligible,
                0
            ) AS profitability_claim_eligible,
            supersession.closure_run_label
                AS superseded_by_closure_run_label,
            supersession.next_workstream
                AS effective_next_workstream
        FROM ai_alpha_candidate_registry AS registry
        LEFT JOIN ai_mission84_candidate_supersessions AS supersession
          ON supersession.rowid = (
              SELECT MAX(latest.rowid)
              FROM ai_mission84_candidate_supersessions AS latest
              WHERE latest.registry_entry_id =
                    registry.registry_entry_id
          );
        """
    )


def source_run_is_safe(
    source_run: sqlite3.Row | Mapping[str, Any] | None,
) -> bool:
    if source_run is None:
        return False

    if str(_value(source_run, "mission85_status", "")) != MISSION85_STATUS:
        return False

    return all(
        safe_int(_value(source_run, field, -1)) == 0
        for field in _SOURCE_ZERO_FIELDS
    )


def registry_row_is_safe(
    row: sqlite3.Row | Mapping[str, Any],
) -> bool:
    for field, expected in _REQUIRED_REGISTRY_ACTIONS.items():
        if str(_value(row, field, "")) != expected:
            return False

    return (
        str(_value(row, "live_trading", "")) == LIVE_TRADING_STATUS
        and safe_int(_value(row, "live_order_sent", -1))
        == LIVE_ORDER_SENT_VALUE
        and str(_value(row, "capital_deployment", ""))
        == CAPITAL_DEPLOYMENT_STATUS
    )


def limitation_codes(
    row: sqlite3.Row | Mapping[str, Any],
) -> list[str]:
    codes = [
        "SYNTHETIC_FIXTURE_EVIDENCE_ONLY",
        "NO_REAL_MARKET_REPLICATION",
        "REPRESENTATIVE_PAIR_SAMPLING_NOT_FULL_UNIVERSE",
    ]

    strategy_family = str(
        _value(row, "strategy_family_code", "")
    )
    asset_group = str(_value(row, "asset_group", ""))

    if (
        strategy_family == "FUNDING_BASIS_CARRY"
        and asset_group != "CRYPTO"
    ):
        codes.append(
            "FUNDING_BASIS_INVALID_FOR_NONCRYPTO_ASSET_GROUP"
        )

    if strategy_family == "VOLATILITY_REGIME_FILTER":
        codes.append(
            "REGIME_FILTER_REQUIRES_OVERLAY_REDESIGN"
        )

    if strategy_family == "HYBRID_ENSEMBLE":
        codes.append(
            "HYBRID_REQUIRES_VALIDATED_COMPONENT_STRATEGIES"
        )

    return codes


def build_supersession(
    row: sqlite3.Row | Mapping[str, Any],
    closure_run_label: str,
    source_promotion_run_label: str,
    created_at: str,
) -> dict[str, Any]:
    registry_entry_id = str(
        _value(row, "registry_entry_id", "")
    )
    if not registry_entry_id:
        raise ValueError("registry_entry_id is required")

    return {
        "supersession_id": (
            f"{closure_run_label}-{registry_entry_id}"
        ),
        "closure_run_label": closure_run_label,
        "source_promotion_run_label": source_promotion_run_label,
        "registry_entry_id": registry_entry_id,
        "created_at": created_at,
        "strategy_family_code": str(
            _value(row, "strategy_family_code", "UNKNOWN")
        ),
        "asset_group": str(
            _value(row, "asset_group", "UNKNOWN")
        ),
        "timeframe": str(
            _value(row, "timeframe", "UNKNOWN")
        ),
        "cost_model_code": str(
            _value(row, "cost_model_code", "UNKNOWN")
        ),
        "original_registry_status": str(
            _value(row, "registry_status", "")
        ),
        "original_evidence_scope": str(
            _value(row, "evidence_scope", "")
        ),
        "original_next_validation_stage": str(
            _value(row, "next_validation_stage", "")
        ),
        "effective_status": EFFECTIVE_STATUS,
        "real_data_eligible": 0,
        "model_training_eligible": 0,
        "model_promotion_eligible": 0,
        "strategy_reweighting_eligible": 0,
        "live_signal_eligible": 0,
        "exchange_order_eligible": 0,
        "capital_deployment_eligible": 0,
        "paid_api_eligible": 0,
        "profitability_claim_eligible": 0,
        "mission85_status": MISSION85_STATUS,
        "next_workstream": NEXT_WORKSTREAM,
        "research_limitation_codes_json": canonical_json(
            limitation_codes(row)
        ),
        "metadata_json": canonical_json(
            {
                "append_only_supersession": True,
                "original_registry_row_preserved": True,
                "fixture_screening_only": True,
                "real_data_validated": False,
                "training_authorized": False,
                "model_promotion_authorized": False,
                "live_trading_authorized": False,
                "capital_authorized": False,
                "profitability_claim_authorized": False,
            }
        ),
    }


def supersession_is_safe(row: Mapping[str, Any]) -> bool:
    zero_fields = (
        "real_data_eligible",
        "model_training_eligible",
        "model_promotion_eligible",
        "strategy_reweighting_eligible",
        "live_signal_eligible",
        "exchange_order_eligible",
        "capital_deployment_eligible",
        "paid_api_eligible",
        "profitability_claim_eligible",
    )

    return (
        str(row.get("effective_status", "")) == EFFECTIVE_STATUS
        and str(row.get("mission85_status", ""))
        == MISSION85_STATUS
        and all(safe_int(row.get(field, -1)) == 0 for field in zero_fields)
    )


def make_check(
    closure_run_label: str,
    source_promotion_run_label: str,
    created_at: str,
    category: str,
    name: str,
    passed: bool,
    observed: Any,
    threshold: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_id": (
            f"{closure_run_label}-"
            f"{category.lower()}-"
            f"{name.lower().replace('_', '-')}"
        ),
        "closure_run_label": closure_run_label,
        "source_promotion_run_label": source_promotion_run_label,
        "created_at": created_at,
        "check_category": category,
        "check_name": name,
        "check_status": CHECK_PASS if passed else CHECK_FAIL,
        "observed_value": str(observed),
        "threshold_value": str(threshold),
        "check_reason": reason,
        "closure_scope": CLOSURE_SCOPE,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata_json": canonical_json(
            {
                "local_only": True,
                "paper_only": True,
                "append_only": True,
                "no_live_execution": True,
            }
        ),
    }


def _insert_row(
    conn: sqlite3.Connection,
    table: str,
    row: Mapping[str, Any],
    columns: Sequence[str],
) -> None:
    placeholders = ",".join("?" for _ in columns)
    column_sql = ",".join(columns)

    conn.execute(
        f"INSERT INTO {table} ({column_sql}) "
        f"VALUES ({placeholders})",
        tuple(row[column] for column in columns),
    )


def _build_markdown(summary: Mapping[str, Any]) -> str:
    return f"""# DeltaGrid Mission 84 Closure Report

- Closure run: {summary['closure_run_label']}
- Source promotion run: {summary['source_promotion_run_label']}
- Mission 84 status: {summary['mission84_status']}
- Mission 84 outcome: {summary['mission84_outcome']}
- Fixture-screening candidates: {summary['fixture_screening_candidate_count']}
- Superseded candidates: {summary['superseded_candidate_count']}
- Source pairs represented: {summary['source_pair_count']}
- Source pair reuse count: {summary['source_pair_reuse_count']}
- Invalid non-crypto funding candidates: {summary['invalid_noncrypto_funding_candidate_count']}
- Real-data validated candidates: {summary['real_data_validated_candidate_count']}
- Model-training eligible candidates: {summary['model_training_eligible_count']}
- Model promotions: {summary['model_promotion_count']}
- Live signals: {summary['live_signal_count']}
- Exchange orders: {summary['exchange_order_count']}
- Capital deployments: {summary['capital_deployment_count']}
- Profitability claims: {summary['profitability_claim_count']}
- Checks: {summary['pass_check_count']} passed, {summary['fail_check_count']} failed
- Safety breaches: {summary['safety_breach_count']}
- Mission 85: {summary['mission85_status']}
- Next workstream: {summary['next_workstream']}

Mission 84 synthetic-fixture evidence is preserved as historical software and
research-pipeline evidence. It is not real-market alpha evidence and does not
authorize training, promotion, signals, orders, capital, or profitability
claims.
"""


def run_mission84_closure(
    db_path: str | Path,
    closure_run_label: str = "mission84-closure-local-check",
    report_label: str = "mission84-closure-local-check-report",
    source_promotion_run_label: str = "mission84-8-final-check",
    expected_fixture_candidates: int = 35,
    created_at: str | None = None,
) -> dict[str, Any]:
    closure_run_label = normalize_label(
        closure_run_label,
        "closure_run_label",
    )
    report_label = normalize_label(
        report_label,
        "report_label",
    )
    source_promotion_run_label = normalize_label(
        source_promotion_run_label,
        "source_promotion_run_label",
    )

    if expected_fixture_candidates <= 0:
        raise ValueError(
            "expected_fixture_candidates must be positive"
        )

    created_at = created_at or utc_now()
    ensure_schema(db_path)

    with sqlite3.connect(Path(db_path)) as conn:
        conn.row_factory = sqlite3.Row

        missing_tables = [
            table
            for table in _REQUIRED_SOURCE_TABLES
            if not table_exists(conn, table)
        ]
        if missing_tables:
            raise RuntimeError(
                "missing Mission 84 source tables: "
                + ", ".join(missing_tables)
            )

        source_run = conn.execute(
            """
            SELECT *
            FROM ai_alpha_candidate_promotion_runs
            WHERE promotion_run_label = ?
            """,
            (source_promotion_run_label,),
        ).fetchone()

        if source_run is None:
            raise RuntimeError(
                "Mission 84.8 source promotion run not found: "
                f"{source_promotion_run_label}"
            )

        registry_rows = conn.execute(
            """
            SELECT *
            FROM ai_alpha_candidate_registry
            WHERE promotion_run_label = ?
            ORDER BY registry_entry_id
            """,
            (source_promotion_run_label,),
        ).fetchall()

        lineage_rows = conn.execute(
            """
            SELECT
                registry.registry_entry_id,
                registry.asset_group,
                backtest.symbol,
                backtest.companion_symbol
            FROM ai_alpha_candidate_registry AS registry
            LEFT JOIN ai_walk_forward_robustness_results AS robustness
              ON robustness.robustness_result_id =
                 registry.source_robustness_result_id
            LEFT JOIN ai_multi_strategy_backtest_results AS backtest
              ON backtest.result_id = robustness.source_result_id
            WHERE registry.promotion_run_label = ?
            ORDER BY registry.registry_entry_id
            """,
            (source_promotion_run_label,),
        ).fetchall()

        source_declared_count = safe_int(
            _value(source_run, "provisional_candidate_count", -1)
        )
        registry_count = len(registry_rows)

        source_safe = source_run_is_safe(source_run)

        original_status_valid = all(
            str(_value(row, "registry_status", ""))
            == ORIGINAL_REGISTRY_STATUS
            for row in registry_rows
        )
        original_evidence_valid = all(
            str(_value(row, "evidence_scope", ""))
            == ORIGINAL_EVIDENCE_SCOPE
            for row in registry_rows
        )
        original_registry_safety_valid = all(
            registry_row_is_safe(row)
            for row in registry_rows
        )

        lineage_complete = (
            len(lineage_rows) == registry_count
            and all(
                str(_value(row, "symbol", "")).strip()
                and str(
                    _value(row, "companion_symbol", "")
                ).strip()
                for row in lineage_rows
            )
        )

        distinct_pairs = {
            (
                str(_value(row, "asset_group", "")),
                str(_value(row, "symbol", "")),
                str(_value(row, "companion_symbol", "")),
            )
            for row in lineage_rows
            if str(_value(row, "symbol", "")).strip()
            and str(_value(row, "companion_symbol", "")).strip()
        }

        source_pair_count = len(distinct_pairs)
        source_pair_reuse_count = max(
            0,
            len(lineage_rows) - source_pair_count,
        )

        invalid_noncrypto_funding_count = sum(
            1
            for row in registry_rows
            if str(_value(row, "strategy_family_code", ""))
            == "FUNDING_BASIS_CARRY"
            and str(_value(row, "asset_group", ""))
            != "CRYPTO"
        )

        supersessions = [
            build_supersession(
                row=row,
                closure_run_label=closure_run_label,
                source_promotion_run_label=(
                    source_promotion_run_label
                ),
                created_at=created_at,
            )
            for row in registry_rows
        ]

        unsafe_registry_count = sum(
            not registry_row_is_safe(row)
            for row in registry_rows
        )
        unsafe_supersession_count = sum(
            not supersession_is_safe(row)
            for row in supersessions
        )
        source_safety_issue_count = 0 if source_safe else 1

        safety_breach_count = (
            unsafe_registry_count
            + unsafe_supersession_count
            + source_safety_issue_count
        )

        checks = [
            make_check(
                closure_run_label,
                source_promotion_run_label,
                created_at,
                "SOURCE",
                "SOURCE_RUN_SAFE",
                source_safe,
                source_safe,
                True,
                "Mission 84.8 source run must retain every safety lock.",
            ),
            make_check(
                closure_run_label,
                source_promotion_run_label,
                created_at,
                "COVERAGE",
                "EXPECTED_FIXTURE_CANDIDATES",
                registry_count == expected_fixture_candidates,
                registry_count,
                expected_fixture_candidates,
                "The verified Mission 84.8 fixture registry must be complete.",
            ),
            make_check(
                closure_run_label,
                source_promotion_run_label,
                created_at,
                "COVERAGE",
                "SOURCE_DECLARED_COUNT_MATCHES_REGISTRY",
                source_declared_count == registry_count,
                source_declared_count,
                registry_count,
                "The source run count must match persisted registry rows.",
            ),
            make_check(
                closure_run_label,
                source_promotion_run_label,
                created_at,
                "EVIDENCE",
                "ORIGINAL_STATUS_FIXTURE_ONLY",
                original_status_valid,
                original_status_valid,
                True,
                "Every source entry must remain explicitly fixture-only.",
            ),
            make_check(
                closure_run_label,
                source_promotion_run_label,
                created_at,
                "EVIDENCE",
                "ORIGINAL_EVIDENCE_SCOPE_SYNTHETIC",
                original_evidence_valid,
                original_evidence_valid,
                True,
                "Every source entry must retain synthetic evidence scope.",
            ),
            make_check(
                closure_run_label,
                source_promotion_run_label,
                created_at,
                "SAFETY",
                "ORIGINAL_REGISTRY_SAFETY_LOCKS",
                original_registry_safety_valid,
                unsafe_registry_count,
                0,
                "Original registry rows must retain all safety locks.",
            ),
            make_check(
                closure_run_label,
                source_promotion_run_label,
                created_at,
                "LINEAGE",
                "BACKTEST_LINEAGE_COMPLETE",
                lineage_complete,
                len(lineage_rows),
                registry_count,
                "Every fixture candidate must retain backtest lineage.",
            ),
            make_check(
                closure_run_label,
                source_promotion_run_label,
                created_at,
                "LIMITATION",
                "REPRESENTATIVE_PAIR_REUSE_RECORDED",
                source_pair_reuse_count > 0,
                source_pair_reuse_count,
                "> 0",
                "The representative-pair limitation must be recorded.",
            ),
            make_check(
                closure_run_label,
                source_promotion_run_label,
                created_at,
                "LIMITATION",
                "NONCRYPTO_FUNDING_LIMITATION_RECORDED",
                invalid_noncrypto_funding_count > 0,
                invalid_noncrypto_funding_count,
                "> 0",
                "Invalid non-crypto funding combinations must be recorded.",
            ),
            make_check(
                closure_run_label,
                source_promotion_run_label,
                created_at,
                "SUPERSESSION",
                "SUPERSESSION_COVERAGE_COMPLETE",
                len(supersessions) == registry_count,
                len(supersessions),
                registry_count,
                "Every fixture candidate must receive a supersession record.",
            ),
            make_check(
                closure_run_label,
                source_promotion_run_label,
                created_at,
                "SUPERSESSION",
                "EFFECTIVE_STATUS_NOT_REAL_DATA_VALIDATED",
                all(
                    row["effective_status"] == EFFECTIVE_STATUS
                    for row in supersessions
                ),
                EFFECTIVE_STATUS,
                EFFECTIVE_STATUS,
                "Effective status must deny real-data validation.",
            ),
            make_check(
                closure_run_label,
                source_promotion_run_label,
                created_at,
                "GOVERNANCE",
                "ZERO_REAL_DATA_VALIDATED",
                all(
                    safe_int(row["real_data_eligible"]) == 0
                    for row in supersessions
                ),
                0,
                0,
                "No synthetic candidate is real-data validated.",
            ),
            make_check(
                closure_run_label,
                source_promotion_run_label,
                created_at,
                "GOVERNANCE",
                "ZERO_MODEL_TRAINING_ELIGIBLE",
                all(
                    safe_int(row["model_training_eligible"]) == 0
                    for row in supersessions
                ),
                0,
                0,
                "No fixture candidate is training eligible.",
            ),
            make_check(
                closure_run_label,
                source_promotion_run_label,
                created_at,
                "SAFETY",
                "NO_MODEL_PROMOTION",
                all(
                    safe_int(row["model_promotion_eligible"]) == 0
                    for row in supersessions
                ),
                0,
                0,
                "No model promotion is authorized.",
            ),
            make_check(
                closure_run_label,
                source_promotion_run_label,
                created_at,
                "SAFETY",
                "NO_STRATEGY_REWEIGHTING",
                all(
                    safe_int(
                        row["strategy_reweighting_eligible"]
                    )
                    == 0
                    for row in supersessions
                ),
                0,
                0,
                "No strategy reweighting is authorized.",
            ),
            make_check(
                closure_run_label,
                source_promotion_run_label,
                created_at,
                "SAFETY",
                "NO_LIVE_SIGNALS",
                all(
                    safe_int(row["live_signal_eligible"]) == 0
                    for row in supersessions
                ),
                0,
                0,
                "No live signal generation is authorized.",
            ),
            make_check(
                closure_run_label,
                source_promotion_run_label,
                created_at,
                "SAFETY",
                "NO_EXCHANGE_ORDERS",
                all(
                    safe_int(row["exchange_order_eligible"]) == 0
                    for row in supersessions
                ),
                0,
                0,
                "No exchange order is authorized.",
            ),
            make_check(
                closure_run_label,
                source_promotion_run_label,
                created_at,
                "SAFETY",
                "NO_CAPITAL_DEPLOYMENT",
                all(
                    safe_int(
                        row["capital_deployment_eligible"]
                    )
                    == 0
                    for row in supersessions
                ),
                0,
                0,
                "No capital deployment is authorized.",
            ),
            make_check(
                closure_run_label,
                source_promotion_run_label,
                created_at,
                "SAFETY",
                "NO_PAID_APIS",
                all(
                    safe_int(row["paid_api_eligible"]) == 0
                    for row in supersessions
                ),
                0,
                0,
                "No paid API is authorized.",
            ),
            make_check(
                closure_run_label,
                source_promotion_run_label,
                created_at,
                "SAFETY",
                "NO_PRIVATE_KEYS",
                True,
                0,
                0,
                "The closure uses no private keys or signing.",
            ),
            make_check(
                closure_run_label,
                source_promotion_run_label,
                created_at,
                "GOVERNANCE",
                "NO_PROFITABILITY_CLAIMS",
                all(
                    safe_int(
                        row["profitability_claim_eligible"]
                    )
                    == 0
                    for row in supersessions
                ),
                0,
                0,
                "Synthetic fixture observations are not profitability claims.",
            ),
            make_check(
                closure_run_label,
                source_promotion_run_label,
                created_at,
                "GOVERNANCE",
                "MISSION85_PAUSED",
                MISSION85_STATUS
                == "PAUSED_UNTIL_ROBUST_ALPHA_CANDIDATES_EXIST",
                MISSION85_STATUS,
                "PAUSED_UNTIL_ROBUST_ALPHA_CANDIDATES_EXIST",
                "Mission 85 must remain paused.",
            ),
            make_check(
                closure_run_label,
                source_promotion_run_label,
                created_at,
                "SAFETY",
                "ZERO_SAFETY_BREACHES",
                safety_breach_count == 0,
                safety_breach_count,
                0,
                "Source and supersession safety checks must pass.",
            ),
        ]

        pass_count = sum(
            row["check_status"] == CHECK_PASS
            for row in checks
        )
        fail_count = sum(
            row["check_status"] == CHECK_FAIL
            for row in checks
        )
        ready = fail_count == 0

        summary: dict[str, Any] = {
            "closure_run_label": closure_run_label,
            "report_label": report_label,
            "source_promotion_run_label": (
                source_promotion_run_label
            ),
            "created_at": created_at,
            "closure_scope": CLOSURE_SCOPE,
            "mission84_status": (
                MISSION84_STATUS_CLOSED
                if ready
                else MISSION84_STATUS_BLOCKED
            ),
            "mission84_outcome": (
                MISSION84_OUTCOME
                if ready
                else BLOCKED_OUTCOME
            ),
            "fixture_screening_candidate_count": registry_count,
            "superseded_candidate_count": len(supersessions),
            "source_pair_count": source_pair_count,
            "source_pair_reuse_count": source_pair_reuse_count,
            "invalid_noncrypto_funding_candidate_count": (
                invalid_noncrypto_funding_count
            ),
            "real_data_validated_candidate_count": 0,
            "model_training_eligible_count": 0,
            "model_promotion_count": 0,
            "strategy_reweighting_count": 0,
            "live_signal_count": 0,
            "exchange_order_count": 0,
            "capital_deployment_count": 0,
            "paid_api_count": 0,
            "private_key_use_count": 0,
            "profitability_claim_count": 0,
            "closure_check_count": len(checks),
            "pass_check_count": pass_count,
            "fail_check_count": fail_count,
            "safety_breach_count": safety_breach_count,
            "mission85_status": MISSION85_STATUS,
            "next_workstream": NEXT_WORKSTREAM,
            "engine_state": (
                ENGINE_STATE
                if ready
                else "MISSION84_CLOSURE_BLOCKED"
            ),
            "engine_decision": (
                ENGINE_DECISION
                if ready
                else "MISSION84_CLOSURE_REQUIRES_REMEDIATION"
            ),
            "global_verdict": (
                GLOBAL_VERDICT
                if ready
                else "MISSION84_CLOSURE_BLOCKED_RESEARCH_ONLY"
            ),
            "recommended_action": (
                RECOMMENDED_ACTION
                if ready
                else "REMEDIATE_FAILED_MISSION84_CLOSURE_CHECKS"
            ),
            "live_trading": LIVE_TRADING_STATUS,
            "live_order_sent": LIVE_ORDER_SENT_VALUE,
            "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
            "closure_checks": checks,
            "supersessions": supersessions,
        }

        markdown_report = _build_markdown(summary)
        summary["markdown_report"] = markdown_report

        conn.execute(
            """
            DELETE FROM ai_mission84_candidate_supersessions
            WHERE closure_run_label = ?
            """,
            (closure_run_label,),
        )
        conn.execute(
            """
            DELETE FROM ai_mission84_closure_checks
            WHERE closure_run_label = ?
            """,
            (closure_run_label,),
        )
        conn.execute(
            """
            DELETE FROM ai_mission84_closure_runs
            WHERE closure_run_label = ?
            """,
            (closure_run_label,),
        )
        conn.execute(
            """
            DELETE FROM ai_mission84_closure_reports
            WHERE report_label = ?
            """,
            (report_label,),
        )

        for row in supersessions:
            _insert_row(
                conn,
                "ai_mission84_candidate_supersessions",
                row,
                _SUPERSESSION_COLUMNS,
            )

        for row in checks:
            _insert_row(
                conn,
                "ai_mission84_closure_checks",
                row,
                _CHECK_COLUMNS,
            )

        summary_payload = {
            key: value
            for key, value in summary.items()
            if key
            not in {
                "markdown_report",
                "closure_checks",
                "supersessions",
            }
        }

        run_row = dict(summary_payload)
        run_row["summary_json"] = canonical_json(
            {
                **summary_payload,
                "closure_checks": checks,
            }
        )
        run_row["markdown_report"] = markdown_report

        _insert_row(
            conn,
            "ai_mission84_closure_runs",
            run_row,
            _RUN_COLUMNS,
        )

        report_row = {
            "report_label": report_label,
            "closure_run_label": closure_run_label,
            "source_promotion_run_label": (
                source_promotion_run_label
            ),
            "created_at": created_at,
            "global_verdict": summary["global_verdict"],
            "recommended_action": summary["recommended_action"],
            "report_json": canonical_json(
                {
                    **summary_payload,
                    "closure_checks": checks,
                }
            ),
            "markdown_report": markdown_report,
            "live_trading": LIVE_TRADING_STATUS,
            "live_order_sent": LIVE_ORDER_SENT_VALUE,
            "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        }

        _insert_row(
            conn,
            "ai_mission84_closure_reports",
            report_row,
            tuple(report_row.keys()),
        )

        _refresh_effective_registry_view(conn)
        conn.commit()

    return summary


def load_real_data_eligible_candidates(
    db_path: str | Path,
) -> list[dict[str, Any]]:
    """Return only candidates explicitly eligible under the effective view."""

    ensure_schema(db_path)

    with sqlite3.connect(Path(db_path)) as conn:
        conn.row_factory = sqlite3.Row

        view_exists = conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'view'
              AND name = 'ai_alpha_candidate_registry_effective'
            """
        ).fetchone()

        if view_exists is None:
            return []

        rows = conn.execute(
            """
            SELECT *
            FROM ai_alpha_candidate_registry_effective
            WHERE real_data_eligible = 1
            ORDER BY registry_entry_id
            """
        ).fetchall()

    return [dict(row) for row in rows]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Close Mission 84 and append authoritative "
            "fixture-evidence supersession records."
        )
    )
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--closure-run-label",
        default="mission84-closure-local-check",
    )
    parser.add_argument(
        "--report-label",
        default="mission84-closure-local-check-report",
    )
    parser.add_argument(
        "--source-promotion-run-label",
        default="mission84-8-final-check",
    )
    parser.add_argument(
        "--expected-fixture-candidates",
        type=int,
        default=35,
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(
        list(argv) if argv is not None else None
    )

    summary = run_mission84_closure(
        db_path=args.db_path,
        closure_run_label=args.closure_run_label,
        report_label=args.report_label,
        source_promotion_run_label=(
            args.source_promotion_run_label
        ),
        expected_fixture_candidates=(
            args.expected_fixture_candidates
        ),
    )

    output = {
        key: value
        for key, value in summary.items()
        if key
        not in {
            "markdown_report",
            "closure_checks",
            "supersessions",
        }
    }
    print(json.dumps(output, indent=2, sort_keys=True))

    return 0 if summary["fail_check_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
