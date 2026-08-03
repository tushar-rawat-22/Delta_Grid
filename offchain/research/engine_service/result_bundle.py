"""Canonical result construction and persisted-link result loading."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Mapping

from offchain.research.admission import (
    AdmissionError,
    ControlRegistry,
    TrialLedger,
    TrialResultLink,
    canonical_hash,
    canonical_json,
)

from .models import (
    EngineError,
    ExecutionOutcome,
    ExecutionPermit,
    LinkedResult,
    MISSION_AUTHORIZATION_STAGE,
    MISSION_BASE_COMMIT,
    MISSION_CONTRACT_HASH,
    MISSION_CONTRACT_ID,
    PRECEDING_CONTRACT_HASH,
    PRECEDING_CONTRACT_PATH,
    REASON_EXPLANATIONS,
    RESULT_BUNDLE_VERSION,
    ResultBundle,
    _RESULT_BUNDLE_CONSTRUCTION_TOKEN,
)
from .strict_json import (
    MAX_ACCOUNTING_VALUE,
    MAX_EVENT_LEDGER_BYTES,
    MAX_RESULT_BYTES,
    decode_canonical_json,
    publish_canonical,
    resolve_existing_regular_file,
    sha256_bytes,
)
from .synthetic_controls import (
    ENGINE_ID,
    ENGINE_VERSION,
    KERNEL_ID,
    KERNEL_VERSION,
)
from .synthetic_fixture import _timing_diagnostics, _validate_fixture_mapping


TRIAL_ID_RE = re.compile(r"trial-[0-9a-f]{32}\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
WARNINGS = (
    "SYNTHETIC_ONLY_NON_ALPHA_CONTROL",
    "NO_PROFITABILITY_INFERENCE",
    "NO_RESEARCH_TRADING_OR_CAPITAL_AUTHORITY",
)
EVENT_LEDGER_SCHEMA_VERSION = "1.0"
EVENT_LEDGER_ARTIFACT_TYPE = "CANONICAL_SYNTHETIC_EVENT_LEDGER"
BENCHMARK_BASELINE_ID = "FIXED_BUY_AND_HOLD_BASELINE_V1"
BENCHMARK_BASELINE_ROLE = "NON_TRIAL_BASELINE"
CODE_IDENTITY = "DELTAGRID_MISSION95_CANONICAL_RESULT_ENGINE_V1"
SIMULATOR_IDENTITY = "DELTAGRID_SYNTHETIC_LONG_OR_FLAT_SIMULATOR_V1"
EXECUTION_MODEL_IDENTITY = (
    "DELTAGRID_AVAILABLE_FILL_TARGET_DELTA_EXECUTION_MODEL_V1"
)
COST_MODEL_IDENTITY = "DELTAGRID_INTEGER_FEE_SLIPPAGE_COST_MODEL_V1"
RISK_MODEL_IDENTITY = (
    "DELTAGRID_INTEGER_DRAWDOWN_EXPOSURE_CONCENTRATION_RISK_MODEL_V1"
)
MISSION93_GAP_05_FIELD_MAP = (
    ("schema_version", ("$.schema_version",), "SCALAR", "DIRECT"),
    ("result_bundle_id", ("$.result_bundle_id",), "SCALAR", "DIRECT"),
    ("manifest_id", ("$.admission.request_id",), "SCALAR", "DIRECT"),
    ("manifest_hash_sha256", ("$.admission.request_hash",), "SCALAR", "DIRECT"),
    ("code_identity", ("$.engine.code_identity",), "SCALAR", "DIRECT"),
    (
        "repository_commit",
        ("$.engine.implementation_repository_commit",),
        "SCALAR",
        "DIRECT",
    ),
    ("dataset_ids", ("$.dataset.dataset_id",), "SINGLETON_LIST", "SINGLETON_PROJECTION"),
    (
        "dataset_hashes",
        ("$.dataset.dataset_content_hash",),
        "SINGLETON_LIST",
        "SINGLETON_PROJECTION",
    ),
    ("simulator_identity", ("$.engine.simulator_identity",), "SCALAR", "DIRECT"),
    ("cost_model_identity", ("$.engine.cost_model_identity",), "SCALAR", "DIRECT"),
    (
        "execution_model_identity",
        ("$.engine.execution_model_identity",),
        "SCALAR",
        "DIRECT",
    ),
    ("risk_model_identity", ("$.engine.risk_model_identity",), "SCALAR", "DIRECT"),
    ("start_timestamp", ("$.result.data_start_at",), "SCALAR", "DIRECT"),
    ("end_timestamp", ("$.result.data_end_at",), "SCALAR", "DIRECT"),
    ("status_token", ("$.result.status_token",), "SCALAR", "DIRECT"),
    ("reason_token", ("$.result.reason_token",), "SCALAR", "DIRECT"),
    (
        "failure_stop_or_rejection_reason",
        ("$.result.failure_stop_or_rejection_reason",),
        "SCALAR",
        "DIRECT",
    ),
    ("human_explanation", ("$.result.human_explanation",), "SCALAR", "DIRECT"),
    (
        "gross_result",
        ("$.metrics.trial.gross_result_units",),
        "SCALAR",
        "DIRECT",
    ),
    ("net_result", ("$.metrics.trial.net_result_units",), "SCALAR", "DIRECT"),
    ("benchmark", ("$.metrics.benchmark",), "OBJECT", "DIRECT"),
    (
        "costs_by_component",
        (
            "$.metrics.trial.fee_cost_units",
            "$.metrics.trial.slippage_cost_units",
            "$.metrics.trial.funding_cost_units",
            "$.metrics.trial.borrowing_cost_units",
            "$.metrics.trial.impact_cost_units",
            "$.metrics.trial.latency_cost_units",
        ),
        "OBJECT",
        "FIELD_GROUP",
    ),
    (
        "maximum_drawdown",
        (
            "$.metrics.trial.maximum_drawdown_units",
            "$.metrics.trial.maximum_drawdown_bps",
        ),
        "OBJECT",
        "FIELD_GROUP",
    ),
    (
        "exposure",
        (
            "$.metrics.trial.exposure_position_units_sum",
            "$.metrics.trial.exposure_event_count",
            "$.metrics.trial.exposure_bps",
        ),
        "OBJECT",
        "FIELD_GROUP",
    ),
    ("turnover", ("$.metrics.trial.turnover_units",), "SCALAR", "DIRECT"),
    ("trade_count", ("$.metrics.trial.trade_count",), "SCALAR", "DIRECT"),
    (
        "concentration",
        ("$.metrics.trial.concentration_bps",),
        "SCALAR",
        "DIRECT",
    ),
    (
        "timing_diagnostics",
        ("$.execution.timing_diagnostics",),
        "OBJECT",
        "DIRECT",
    ),
    (
        "protected_access_counts",
        ("$.protected_access_counts",),
        "OBJECT",
        "DIRECT",
    ),
    (
        "artifact_paths",
        ("$.artifacts[].relative_path",),
        "ARRAY",
        "DIRECT",
    ),
    ("warnings", ("$.warnings",), "ARRAY", "DIRECT"),
    ("verification_results", ("$.verification",), "OBJECT", "DIRECT"),
    (
        "canonical_result_hash_sha256",
        ("$.canonical_result_hash",),
        "SCALAR",
        "DIRECT",
    ),
)


def _mission93_gap_05_field_map() -> list[dict[str, Any]]:
    return [
        {
            "mission93_field": field,
            "mission95_paths": list(paths),
            "cardinality": cardinality,
            "transformation": transformation,
        }
        for field, paths, cardinality, transformation in MISSION93_GAP_05_FIELD_MAP
    ]
ACCESS_COUNT_FIELDS = frozenset(
    {
        "market_data_access_count",
        "development_market_access_count",
        "validation_access_count",
        "holdout_access_count",
        "protected_data_access_count",
        "network_access_count",
        "exchange_access_count",
        "model_access_count",
        "paper_trading_access_count",
        "live_trading_access_count",
        "capital_access_count",
        "strategy_access_count",
        "autonomous_research_access_count",
        "dashboard_access_count",
    }
)
VERIFICATION_FIELDS = frozenset(
    {
        "request_hash_verified",
        "decision_hash_verified",
        "reservation_verified",
        "dataset_resolution_verified",
        "fixture_bytes_verified",
        "fixture_schema_verified",
        "control_verified",
        "permit_verified",
        "event_ledger_verified",
        "protected_access_counts_verified",
        "canonical_result_verified",
    }
)
RESULT_FIELDS = frozenset(
    {
        "schema_version",
        "result_bundle_id",
        "result_bundle_version",
        "mission_contract",
        "admission",
        "engine",
        "dataset",
        "control",
        "result",
        "execution",
        "metrics",
        "protected_access_counts",
        "artifacts",
        "warnings",
        "verification",
        "mission93_gap_05_field_map",
        "canonical_result_hash",
    }
)
MISSION_FIELDS = frozenset(
    {
        "contract_id",
        "contract_hash",
        "authorization_stage",
        "base_commit",
        "preceding_contract_path",
        "preceding_contract_hash",
    }
)
ADMISSION_FIELDS = frozenset(
    {
        "request_id",
        "request_hash",
        "request_created_at",
        "decision_id",
        "decision_hash",
        "decision_token",
        "reason_token",
        "trial_id",
        "budget_id",
        "budget_hash",
        "declared_trial_number",
        "reservation_reserved_at",
        "initiated_by",
        "experiment_family",
        "total_trial_budget",
        "repository_clean",
        "dataset_resolution_hash",
        "validated_control_hash",
    }
)
ENGINE_FIELDS = frozenset(
    {
        "engine_id",
        "engine_version",
        "kernel_id",
        "kernel_version",
        "implementation_repository_commit",
        "permit_scope",
        "permit_hash",
        "code_identity",
        "simulator_identity",
        "execution_model_identity",
        "cost_model_identity",
        "risk_model_identity",
    }
)
DATASET_FIELDS = frozenset(
    {
        "dataset_id",
        "dataset_content_hash",
        "artifact_id",
        "artifact_path",
        "metadata_hash",
        "resolution_hash",
        "fixture_id",
        "fixture_hash",
        "data_class",
        "split_identity",
        "instrument_id",
        "currency_unit",
        "initial_cash_units",
        "trade_quantity_units",
        "fee_bps",
        "slippage_bps",
        "provenance_reference",
        "resolution_authorization_stage",
        "resolution_reason_token",
    }
)
CONTROL_FIELDS = frozenset(
    {
        "control_identifier",
        "control_parameters",
        "validated_control_hash",
        "non_alpha",
        "registry_execution_authorized",
    }
)
RESULT_STATUS_FIELDS = frozenset(
    {
        "status_token",
        "reason_token",
        "human_explanation",
        "recorded_at",
        "data_start_at",
        "data_end_at",
        "failure_stop_or_rejection_reason",
    }
)
EXECUTION_FIELDS = frozenset(
    {"event_count", "targets_hash", "final_state", "timing_diagnostics"}
)
TIMING_FIELDS = frozenset(
    {
        "event_count",
        "interval_count",
        "data_start_at",
        "data_end_at",
        "duration_microseconds",
        "minimum_interval_microseconds",
        "maximum_interval_microseconds",
        "nonpositive_interval_count",
    }
)
METRICS_FIELDS = frozenset({"trial", "benchmark"})
BENCHMARK_FIELDS = frozenset({"baseline_id", "baseline_role", "metrics"})
ARTIFACT_FIELDS = frozenset(
    {
        "artifact_id",
        "artifact_type",
        "relative_path",
        "byte_sha256",
        "canonical_artifact_hash",
    }
)
LEDGER_FIELDS = frozenset(
    {
        "schema_version",
        "artifact_id",
        "artifact_type",
        "trial_id",
        "engine_id",
        "engine_version",
        "kernel_id",
        "kernel_version",
        "fixture_id",
        "fixture_hash",
        "control_identifier",
        "validated_control_hash",
        "permit_hash",
        "rows",
        "final_state",
        "canonical_event_ledger_hash",
    }
)
ROW_FIELDS = frozenset(
    {
        "event_index",
        "event_id",
        "timestamp",
        "mid_price_units",
        "available_fill_bps",
        "target_position_units",
        "position_before_units",
        "attempted_delta_units",
        "executed_delta_units",
        "execution_price_units",
        "fee_cost_units",
        "slippage_cost_units",
        "event_turnover_units",
        "position_after_units",
        "gross_cash_units",
        "net_cash_units",
        "gross_equity_units",
        "net_equity_units",
        "cumulative_fee_cost_units",
        "cumulative_slippage_cost_units",
        "state_before",
        "state_after",
    }
)
KERNEL_METRIC_FIELDS = frozenset(
    {
        "initial_cash_units",
        "final_gross_cash_units",
        "final_net_cash_units",
        "gross_result_units",
        "net_result_units",
        "fee_cost_units",
        "slippage_cost_units",
        "funding_cost_units",
        "borrowing_cost_units",
        "impact_cost_units",
        "latency_cost_units",
        "maximum_drawdown_units",
        "maximum_drawdown_bps",
        "turnover_units",
        "exposure_position_units_sum",
        "exposure_event_count",
        "exposure_bps",
        "concentration_bps",
        "attempt_count",
        "fill_count",
        "trade_count",
        "entry_count",
        "exit_count",
        "partial_entry_count",
        "partial_exit_count",
        "final_position_units",
        "final_state",
    }
)


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and HASH_RE.fullmatch(value) is not None


def validate_trial_id(trial_id: str) -> None:
    if not isinstance(trial_id, str) or TRIAL_ID_RE.fullmatch(trial_id) is None:
        raise EngineError("RESULT_PATH_UNSAFE")


def reconstruct_decision_id(admission: Mapping[str, Any]) -> str:
    identity = {
        "operation": "admit",
        "request_id": admission["request_id"],
        "trial_id": admission["trial_id"],
        "decision_token": "ADMITTED",
        "reason_token": "ADMISSION_GATES_PASSED",
        "dataset_resolution_hash": admission.get("dataset_resolution_hash"),
        "validated_control_hash": admission.get("validated_control_hash"),
        "budget_id": admission["budget_id"],
        "declared_trial_number": admission["declared_trial_number"],
        "created_at": admission["request_created_at"],
    }
    return f"decision-{canonical_hash(identity)[:32]}"


def _artifact_id(identity: Mapping[str, Any], targets_hash: str) -> str:
    artifact_identity = {
        "trial_id": identity["trial_id"],
        "fixture_hash": identity["fixture_hash"],
        "validated_control_hash": identity["validated_control_hash"],
        "permit_hash": identity["permit_hash"],
        "targets_hash": targets_hash,
    }
    return f"event-ledger-{canonical_hash(artifact_identity)[:32]}"


def build_event_ledger(
    *,
    identity: Mapping[str, Any],
    outcome: ExecutionOutcome,
) -> dict[str, Any]:
    core = {
        "schema_version": EVENT_LEDGER_SCHEMA_VERSION,
        "artifact_id": _artifact_id(identity, outcome.targets_hash),
        "artifact_type": EVENT_LEDGER_ARTIFACT_TYPE,
        "trial_id": identity["trial_id"],
        "engine_id": identity["engine_id"],
        "engine_version": identity["engine_version"],
        "kernel_id": identity["kernel_id"],
        "kernel_version": identity["kernel_version"],
        "fixture_id": identity["fixture_id"],
        "fixture_hash": identity["fixture_hash"],
        "control_identifier": identity["control_identifier"],
        "validated_control_hash": identity["validated_control_hash"],
        "permit_hash": identity["permit_hash"],
        "rows": [dict(row) for row in outcome.rows],
        "final_state": outcome.final_state,
    }
    return {**core, "canonical_event_ledger_hash": canonical_hash(core)}


def _bundle_identity(bundle: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "mission_contract": bundle["mission_contract"],
        "request_hash": bundle["admission"]["request_hash"],
        "decision_hash": bundle["admission"]["decision_hash"],
        "trial_id": bundle["admission"]["trial_id"],
        "dataset": bundle["dataset"],
        "control": bundle["control"],
        "permit_hash": bundle["engine"]["permit_hash"],
        "targets_hash": bundle["execution"]["targets_hash"],
        "artifact_hash": bundle["artifacts"][0]["canonical_artifact_hash"],
    }


def build_result_bundle(
    *,
    mission_contract: Mapping[str, Any],
    admission: Mapping[str, Any],
    engine: Mapping[str, Any],
    dataset: Mapping[str, Any],
    control: Mapping[str, Any],
    outcome: ExecutionOutcome,
    benchmark: ExecutionOutcome,
    artifact: Mapping[str, Any],
    recorded_at: str,
    data_start_at: str,
    data_end_at: str,
    event_timestamps: tuple[str, ...],
) -> dict[str, Any]:
    timing_diagnostics = _timing_diagnostics(event_timestamps)
    core = {
        "schema_version": "1.0",
        "result_bundle_id": "",
        "result_bundle_version": RESULT_BUNDLE_VERSION,
        "mission_contract": dict(mission_contract),
        "admission": dict(admission),
        "engine": dict(engine),
        "dataset": dict(dataset),
        "control": {
            **dict(control),
            "control_parameters": dict(control["control_parameters"]),
        },
        "result": {
            "status_token": "RESULT_VERIFIED",
            "reason_token": "SYNTHETIC_CONTROL_RESULT_VERIFIED",
            "human_explanation": REASON_EXPLANATIONS[
                "SYNTHETIC_CONTROL_RESULT_VERIFIED"
            ],
            "recorded_at": recorded_at,
            "data_start_at": data_start_at,
            "data_end_at": data_end_at,
            "failure_stop_or_rejection_reason": None,
        },
        "execution": {
            "event_count": len(outcome.rows),
            "targets_hash": outcome.targets_hash,
            "final_state": outcome.final_state,
            "timing_diagnostics": timing_diagnostics,
        },
        "metrics": {
            "trial": dict(outcome.metrics),
            "benchmark": {
                "baseline_id": BENCHMARK_BASELINE_ID,
                "baseline_role": BENCHMARK_BASELINE_ROLE,
                "metrics": dict(benchmark.metrics),
            },
        },
        "protected_access_counts": {
            field: 0 for field in sorted(ACCESS_COUNT_FIELDS)
        },
        "artifacts": [dict(artifact)],
        "warnings": list(WARNINGS),
        "verification": {
            field: True for field in sorted(VERIFICATION_FIELDS)
        },
        "mission93_gap_05_field_map": _mission93_gap_05_field_map(),
    }
    core["result_bundle_id"] = (
        f"result-bundle-{canonical_hash(_bundle_identity(core))[:32]}"
    )
    return {**core, "canonical_result_hash": canonical_hash(core)}


def publish_event_ledger(path: Path, ledger: Mapping[str, Any]) -> bytes:
    return publish_canonical(
        path,
        ledger,
        max_bytes=MAX_EVENT_LEDGER_BYTES,
        validate_existing=lambda raw: _verify_event_ledger_bytes(raw, dict(ledger)),
    )


def publish_result(path: Path, bundle: Mapping[str, Any]) -> bytes:
    return publish_canonical(
        path,
        bundle,
        max_bytes=MAX_RESULT_BYTES,
        validate_existing=lambda raw: _verify_result_bytes(raw),
    )


def _exact_fields(value: Any, fields: frozenset[str], reason: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise EngineError(reason)
    return value


def _verify_event_ledger_bytes(
    raw: bytes,
    expected: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    ledger = _exact_fields(
        decode_canonical_json(
            raw,
            invalid_reason="RESULT_SCHEMA_INVALID",
            max_bytes=MAX_EVENT_LEDGER_BYTES,
        ),
        LEDGER_FIELDS,
        "RESULT_SCHEMA_INVALID",
    )
    core = dict(ledger)
    supplied = core.pop("canonical_event_ledger_hash")
    if not isinstance(supplied, str) or canonical_hash(core) != supplied:
        raise EngineError("RESULT_HASH_MISMATCH")
    if not isinstance(ledger["rows"], list) or not ledger["rows"]:
        raise EngineError("RESULT_SCHEMA_INVALID")
    for index, row in enumerate(ledger["rows"]):
        _exact_fields(row, ROW_FIELDS, "RESULT_SCHEMA_INVALID")
        if (
            type(row["event_index"]) is not int
            or row["event_index"] != index
            or any(
                type(row[field]) is not int
                for field in ROW_FIELDS
                - {"event_id", "timestamp", "state_before", "state_after"}
            )
            or any(
                not isinstance(row[field], str) or not row[field]
                for field in {"event_id", "timestamp", "state_before", "state_after"}
            )
        ):
            raise EngineError("RESULT_SCHEMA_INVALID")
    if expected is not None and ledger != expected:
        raise EngineError("RESULT_ARTIFACT_MISMATCH")
    return ledger


def _verify_result_bytes(raw: bytes) -> dict[str, Any]:
    bundle = _exact_fields(
        decode_canonical_json(
            raw,
            invalid_reason="RESULT_SCHEMA_INVALID",
            max_bytes=MAX_RESULT_BYTES,
        ),
        RESULT_FIELDS,
        "RESULT_SCHEMA_INVALID",
    )
    if (
        bundle["schema_version"] != "1.0"
        or type(bundle["result_bundle_version"]) is not int
        or bundle["result_bundle_version"] != RESULT_BUNDLE_VERSION
    ):
        raise EngineError("RESULT_SCHEMA_INVALID")
    _exact_fields(bundle["mission_contract"], MISSION_FIELDS, "RESULT_SCHEMA_INVALID")
    _exact_fields(bundle["admission"], ADMISSION_FIELDS, "RESULT_SCHEMA_INVALID")
    _exact_fields(bundle["engine"], ENGINE_FIELDS, "RESULT_SCHEMA_INVALID")
    _exact_fields(bundle["dataset"], DATASET_FIELDS, "RESULT_SCHEMA_INVALID")
    _exact_fields(bundle["control"], CONTROL_FIELDS, "RESULT_SCHEMA_INVALID")
    _exact_fields(bundle["result"], RESULT_STATUS_FIELDS, "RESULT_SCHEMA_INVALID")
    _exact_fields(bundle["execution"], EXECUTION_FIELDS, "RESULT_SCHEMA_INVALID")
    metrics = _exact_fields(bundle["metrics"], METRICS_FIELDS, "RESULT_SCHEMA_INVALID")
    benchmark = _exact_fields(
        metrics["benchmark"],
        BENCHMARK_FIELDS,
        "RESULT_SCHEMA_INVALID",
    )
    timing = _exact_fields(
        bundle["execution"]["timing_diagnostics"],
        TIMING_FIELDS,
        "RESULT_SCHEMA_INVALID",
    )
    for metric_value in (metrics["trial"], benchmark["metrics"]):
        if (
            not isinstance(metric_value, dict)
            or set(metric_value) != KERNEL_METRIC_FIELDS
            or any(
                type(metric_value[field]) is not int
                for field in KERNEL_METRIC_FIELDS - {"final_state"}
            )
            or metric_value["final_state"] != "FLAT"
        ):
            raise EngineError("RESULT_SCHEMA_INVALID")
    if (
        not isinstance(bundle["protected_access_counts"], dict)
        or set(bundle["protected_access_counts"]) != ACCESS_COUNT_FIELDS
        or any(
            type(value) is not int or value != 0
            for value in bundle["protected_access_counts"].values()
        )
        or bundle["warnings"] != list(WARNINGS)
        or not isinstance(bundle["verification"], dict)
        or set(bundle["verification"]) != VERIFICATION_FIELDS
        or any(value is not True for value in bundle["verification"].values())
        or not isinstance(bundle["artifacts"], list)
        or len(bundle["artifacts"]) != 1
        or bundle["mission93_gap_05_field_map"] != _mission93_gap_05_field_map()
        or any(
            type(timing[field]) is not int
            for field in TIMING_FIELDS - {"data_start_at", "data_end_at"}
        )
        or not isinstance(timing["data_start_at"], str)
        or not isinstance(timing["data_end_at"], str)
    ):
        raise EngineError("RESULT_SCHEMA_INVALID")
    _exact_fields(bundle["artifacts"][0], ARTIFACT_FIELDS, "RESULT_SCHEMA_INVALID")
    core = dict(bundle)
    supplied = core.pop("canonical_result_hash")
    if not isinstance(supplied, str) or canonical_hash(core) != supplied:
        raise EngineError("RESULT_HASH_MISMATCH")
    expected_id = f"result-bundle-{canonical_hash(_bundle_identity(bundle))[:32]}"
    if bundle["result_bundle_id"] != expected_id:
        raise EngineError("RESULT_HASH_MISMATCH")
    return bundle


def _read_bounded(path: Path, limit: int) -> bytes:
    try:
        with path.open("rb") as artifact_file:
            raw = artifact_file.read(limit + 1)
    except OSError as error:
        raise EngineError("RESULT_ARTIFACT_MISMATCH") from error
    if len(raw) > limit:
        raise EngineError("RESULT_SCHEMA_INVALID")
    return raw


def _root_path(value: Path | str) -> Path:
    root = Path(value)
    return root if root.is_absolute() else Path.cwd() / root


def _verify_bundle_relationships(
    bundle: Mapping[str, Any],
    ledger: Mapping[str, Any],
) -> None:
    mission = bundle["mission_contract"]
    if mission != {
        "contract_id": MISSION_CONTRACT_ID,
        "contract_hash": MISSION_CONTRACT_HASH,
        "authorization_stage": MISSION_AUTHORIZATION_STAGE,
        "base_commit": MISSION_BASE_COMMIT,
        "preceding_contract_path": PRECEDING_CONTRACT_PATH,
        "preceding_contract_hash": PRECEDING_CONTRACT_HASH,
    }:
        raise EngineError("RESULT_ARTIFACT_MISMATCH")
    engine = bundle["engine"]
    if (
        engine["engine_id"] != ENGINE_ID
        or engine["engine_version"] != ENGINE_VERSION
        or engine["kernel_id"] != KERNEL_ID
        or engine["kernel_version"] != KERNEL_VERSION
        or engine["code_identity"] != CODE_IDENTITY
        or engine["simulator_identity"] != SIMULATOR_IDENTITY
        or engine["execution_model_identity"] != EXECUTION_MODEL_IDENTITY
        or engine["cost_model_identity"] != COST_MODEL_IDENTITY
        or engine["risk_model_identity"] != RISK_MODEL_IDENTITY
        or not isinstance(engine["implementation_repository_commit"], str)
        or COMMIT_RE.fullmatch(engine["implementation_repository_commit"]) is None
    ):
        raise EngineError("RESULT_ARTIFACT_MISMATCH")
    admission = bundle["admission"]
    if (
        admission["decision_token"] != "ADMITTED"
        or admission["reason_token"] != "ADMISSION_GATES_PASSED"
        or admission["request_created_at"] != admission["reservation_reserved_at"]
        or admission["repository_clean"] is not True
        or type(admission["declared_trial_number"]) is not int
        or admission["declared_trial_number"] < 1
        or type(admission["total_trial_budget"]) is not int
        or admission["total_trial_budget"] < 1
        or not _is_hash(admission["request_hash"])
        or not _is_hash(admission["decision_hash"])
        or not _is_hash(admission["budget_hash"])
        or not _is_hash(admission["dataset_resolution_hash"])
        or not _is_hash(admission["validated_control_hash"])
    ):
        raise EngineError("RESULT_ARTIFACT_MISMATCH")
    request_core = {
        "schema_version": "1.0",
        "request_id": admission["request_id"],
        "controlling_contract_id": mission["contract_id"],
        "controlling_contract_hash": mission["contract_hash"],
        "repository_commit": engine["implementation_repository_commit"],
        "repository_clean": admission["repository_clean"],
        "budget_id": admission["budget_id"],
        "declared_trial_number": admission["declared_trial_number"],
        "dataset_id": bundle["dataset"]["dataset_id"],
        "dataset_hash": bundle["dataset"]["dataset_content_hash"],
        "data_class": bundle["dataset"]["data_class"],
        "split_identity": bundle["dataset"]["split_identity"],
        "authorization_stage": mission["authorization_stage"],
        "control_identifier": bundle["control"]["control_identifier"],
        "control_parameters": bundle["control"]["control_parameters"],
        "initiated_by": admission["initiated_by"],
        "created_at": admission["request_created_at"],
    }
    if canonical_hash(request_core) != admission["request_hash"]:
        raise EngineError("RESULT_ARTIFACT_MISMATCH")
    decision_identity = {
        **admission,
        "dataset_resolution_hash": admission["dataset_resolution_hash"],
        "validated_control_hash": admission["validated_control_hash"],
    }
    if admission["decision_id"] != reconstruct_decision_id(decision_identity):
        raise EngineError("RESULT_ARTIFACT_MISMATCH")
    decision_core = {
        "schema_version": "1.0",
        "decision_id": admission["decision_id"],
        "request_id": admission["request_id"],
        "trial_id": admission["trial_id"],
        "decision_token": admission["decision_token"],
        "reason_token": admission["reason_token"],
        "dataset_resolution_hash": admission["dataset_resolution_hash"],
        "validated_control_hash": admission["validated_control_hash"],
        "budget_id": admission["budget_id"],
        "declared_trial_number": admission["declared_trial_number"],
        "created_at": admission["request_created_at"],
    }
    if canonical_hash(decision_core) != admission["decision_hash"]:
        raise EngineError("RESULT_ARTIFACT_MISMATCH")
    dataset = bundle["dataset"]
    if (
        dataset["data_class"] != "SYNTHETIC_FIXTURE"
        or dataset["split_identity"] != "SYNTHETIC_DEVELOPMENT"
        or any(
            type(dataset[field]) is not int
            or not 0 < dataset[field] <= MAX_ACCOUNTING_VALUE
            for field in (
                "initial_cash_units",
                "trade_quantity_units",
            )
        )
        or any(
            type(dataset[field]) is not int or not 0 <= dataset[field] <= 10_000
            for field in ("fee_bps", "slippage_bps")
        )
        or any(
            not _is_hash(dataset[field])
            for field in (
                "dataset_content_hash",
                "metadata_hash",
                "resolution_hash",
                "fixture_hash",
            )
        )
        or dataset["resolution_authorization_stage"]
        != MISSION_AUTHORIZATION_STAGE
        or dataset["resolution_reason_token"] != "DATASET_AUTHORIZED"
        or not isinstance(dataset["provenance_reference"], str)
        or not dataset["provenance_reference"]
        or dataset["resolution_hash"] != admission["dataset_resolution_hash"]
        or bundle["control"]["validated_control_hash"]
        != admission["validated_control_hash"]
    ):
        raise EngineError("RESULT_ARTIFACT_MISMATCH")
    resolution_core = {
        "schema_version": "1.0",
        "dataset_id": dataset["dataset_id"],
        "artifact_id": dataset["artifact_id"],
        "content_sha256": dataset["dataset_content_hash"],
        "metadata_sha256": dataset["metadata_hash"],
        "data_class": dataset["data_class"],
        "split_identity": dataset["split_identity"],
        "artifact_path": dataset["artifact_path"],
        "authorization_stage": dataset["resolution_authorization_stage"],
        "provenance_reference": dataset["provenance_reference"],
        "reason_token": dataset["resolution_reason_token"],
    }
    if canonical_hash(resolution_core) != dataset["resolution_hash"]:
        raise EngineError("RESULT_ARTIFACT_MISMATCH")
    control = ControlRegistry().validate(
        bundle["control"]["control_identifier"],
        bundle["control"]["control_parameters"],
    )
    if (
        control.canonical_control_hash
        != bundle["control"]["validated_control_hash"]
        or control.non_alpha is not True
        or control.execution_authorized is not False
        or bundle["control"]["non_alpha"] is not True
        or bundle["control"]["registry_execution_authorized"] is not False
    ):
        raise EngineError("RESULT_ARTIFACT_MISMATCH")
    permit = ExecutionPermit.issue(
        request_hash=admission["request_hash"],
        decision_hash=admission["decision_hash"],
        trial_id=admission["trial_id"],
        dataset_resolution_hash=dataset["resolution_hash"],
        validated_control_hash=control.canonical_control_hash,
    )
    if (
        engine["permit_scope"] != permit.scope
        or engine["permit_hash"] != permit.canonical_permit_hash
    ):
        raise EngineError("RESULT_ARTIFACT_MISMATCH")
    result = bundle["result"]
    if result != {
        "status_token": "RESULT_VERIFIED",
        "reason_token": "SYNTHETIC_CONTROL_RESULT_VERIFIED",
        "human_explanation": REASON_EXPLANATIONS[
            "SYNTHETIC_CONTROL_RESULT_VERIFIED"
        ],
        "recorded_at": admission["request_created_at"],
        "data_start_at": ledger["rows"][0]["timestamp"],
        "data_end_at": ledger["rows"][-1]["timestamp"],
        "failure_stop_or_rejection_reason": None,
    }:
        raise EngineError("RESULT_ARTIFACT_MISMATCH")
    fixture_core = {
        "schema_version": "1.0",
        "fixture_id": dataset["fixture_id"],
        "instrument_id": dataset["instrument_id"],
        "currency_unit": dataset["currency_unit"],
        "initial_cash_units": dataset["initial_cash_units"],
        "trade_quantity_units": dataset["trade_quantity_units"],
        "fee_bps": dataset["fee_bps"],
        "slippage_bps": dataset["slippage_bps"],
        "events": [
            {
                "event_id": row["event_id"],
                "timestamp": row["timestamp"],
                "mid_price_units": row["mid_price_units"],
                "available_fill_bps": row["available_fill_bps"],
            }
            for row in ledger["rows"]
        ],
    }
    try:
        reconstructed_fixture = _validate_fixture_mapping(
            fixture_core,
            includes_canonical_hash=False,
        )
    except EngineError as error:
        raise EngineError("RESULT_ARTIFACT_MISMATCH") from error
    if reconstructed_fixture.canonical_fixture_hash != dataset["fixture_hash"]:
        raise EngineError("RESULT_ARTIFACT_MISMATCH")
    complete_fixture = {
        **fixture_core,
        "canonical_fixture_hash": reconstructed_fixture.canonical_fixture_hash,
    }
    if (
        sha256_bytes(canonical_json(complete_fixture).encode("utf-8"))
        != dataset["dataset_content_hash"]
    ):
        raise EngineError("RESULT_ARTIFACT_MISMATCH")
    try:
        timing_diagnostics = _timing_diagnostics(
            tuple(row["timestamp"] for row in ledger["rows"])
        )
    except EngineError as error:
        raise EngineError("RESULT_ARTIFACT_MISMATCH") from error
    targets_hash = canonical_hash(
        [row["target_position_units"] for row in ledger["rows"]]
    )
    execution = bundle["execution"]
    metrics = bundle["metrics"]
    artifact = bundle["artifacts"][0]
    if (
        ledger["schema_version"] != EVENT_LEDGER_SCHEMA_VERSION
        or ledger["artifact_type"] != EVENT_LEDGER_ARTIFACT_TYPE
        or targets_hash != execution["targets_hash"]
        or len(ledger["rows"]) != execution["event_count"]
        or execution["timing_diagnostics"] != timing_diagnostics
        or timing_diagnostics["nonpositive_interval_count"] != 0
        or result["data_start_at"] != timing_diagnostics["data_start_at"]
        or result["data_end_at"] != timing_diagnostics["data_end_at"]
        or execution["final_state"] != "FLAT"
        or ledger["final_state"] != "FLAT"
        or ledger["rows"][-1]["position_after_units"] != 0
        or ledger["rows"][-1]["state_after"] != "FLAT"
        or ledger["artifact_id"]
        != _artifact_id(
            {
                "trial_id": admission["trial_id"],
                "fixture_hash": dataset["fixture_hash"],
                "validated_control_hash": control.canonical_control_hash,
                "permit_hash": permit.canonical_permit_hash,
            },
            targets_hash,
        )
        or ledger["trial_id"] != admission["trial_id"]
        or ledger["fixture_id"] != dataset["fixture_id"]
        or ledger["fixture_hash"] != dataset["fixture_hash"]
        or ledger["control_identifier"] != control.control_identifier
        or ledger["validated_control_hash"] != control.canonical_control_hash
        or ledger["permit_hash"] != permit.canonical_permit_hash
        or ledger["engine_id"] != ENGINE_ID
        or ledger["engine_version"] != ENGINE_VERSION
        or ledger["kernel_id"] != KERNEL_ID
        or ledger["kernel_version"] != KERNEL_VERSION
        or ledger["artifact_id"] != artifact["artifact_id"]
        or artifact["artifact_type"] != EVENT_LEDGER_ARTIFACT_TYPE
        or metrics["benchmark"]["baseline_id"] != BENCHMARK_BASELINE_ID
        or metrics["benchmark"]["baseline_role"] != BENCHMARK_BASELINE_ROLE
        or metrics["trial"]["initial_cash_units"]
        != dataset["initial_cash_units"]
        or metrics["trial"]["final_position_units"] != 0
        or metrics["trial"]["final_state"] != "FLAT"
        or metrics["benchmark"]["metrics"]["initial_cash_units"]
        != dataset["initial_cash_units"]
        or metrics["benchmark"]["metrics"]["final_position_units"] != 0
        or metrics["benchmark"]["metrics"]["final_state"] != "FLAT"
        or not _is_hash(artifact["byte_sha256"])
        or not _is_hash(artifact["canonical_artifact_hash"])
    ):
        raise EngineError("RESULT_ARTIFACT_MISMATCH")


def _load_link_artifacts(
    *,
    result_root: Path | str,
    link: TrialResultLink,
) -> tuple[ResultBundle, dict[str, Any], dict[str, Any]]:
    try:
        verified_link = TrialResultLink.from_mapping(link.as_dict())
    except AdmissionError as error:
        raise EngineError("RESULT_ARTIFACT_MISMATCH") from error
    validate_trial_id(verified_link.trial_id)
    if verified_link.result_bundle_path != f"{verified_link.trial_id}/result.json":
        raise EngineError("RESULT_ARTIFACT_MISMATCH")
    root = _root_path(result_root)
    result_path = resolve_existing_regular_file(
        root,
        verified_link.result_bundle_path,
        unsafe_reason="RESULT_PATH_UNSAFE",
        missing_reason="RESULT_ARTIFACT_MISMATCH",
    )
    result_raw = _read_bounded(result_path, MAX_RESULT_BYTES)
    bundle = _verify_result_bytes(result_raw)
    if (
        bundle["result_bundle_id"] != verified_link.result_bundle_id
        or bundle["canonical_result_hash"] != verified_link.result_bundle_hash
        or bundle["admission"]["trial_id"] != verified_link.trial_id
    ):
        raise EngineError("RESULT_ARTIFACT_MISMATCH")
    artifact = bundle["artifacts"][0]
    if artifact["relative_path"] != f"{verified_link.trial_id}/event-ledger.json":
        raise EngineError("RESULT_ARTIFACT_MISMATCH")
    artifact_path = resolve_existing_regular_file(
        root,
        artifact["relative_path"],
        unsafe_reason="RESULT_PATH_UNSAFE",
        missing_reason="RESULT_ARTIFACT_MISMATCH",
    )
    artifact_raw = _read_bounded(artifact_path, MAX_EVENT_LEDGER_BYTES)
    ledger = _verify_event_ledger_bytes(artifact_raw)
    if (
        sha256_bytes(artifact_raw) != artifact["byte_sha256"]
        or ledger["canonical_event_ledger_hash"] != artifact["canonical_artifact_hash"]
    ):
        raise EngineError("RESULT_ARTIFACT_MISMATCH")
    _verify_bundle_relationships(bundle, ledger)
    return (
        ResultBundle._from_verified_bytes(
            result_raw,
            _RESULT_BUNDLE_CONSTRUCTION_TOKEN,
        ),
        bundle,
        ledger,
    )


def _verify_candidate_result(
    *,
    result_root: Path | str,
    candidate_link: TrialResultLink,
) -> ResultBundle:
    """Private pre-finalization verification anchored to the candidate link."""

    result, _, _ = _load_link_artifacts(
        result_root=result_root,
        link=candidate_link,
    )
    return result


def _load_linked_result_impl(
    *,
    result_root: Path | str,
    trial_ledger: TrialLedger,
    trial_id: str,
) -> LinkedResult:
    """Load an authoritative Mission 95 result from its persisted ledger link."""

    validate_trial_id(trial_id)
    try:
        link = trial_ledger.get_result_link(trial_id)
        event = trial_ledger.latest_event(trial_id)
    except AdmissionError as error:
        raise EngineError("RESULT_ARTIFACT_MISMATCH") from error
    if link is None:
        raise EngineError("RESULT_ARTIFACT_MISMATCH")
    if (
        event.status_token != "COMPLETED"
        or event.reason_token != "SYNTHETIC_CONTROL_COMPLETED"
        or event.event_timestamp != link.linked_at
    ):
        raise EngineError("RESULT_ARTIFACT_MISMATCH")
    result, bundle, _ = _load_link_artifacts(result_root=result_root, link=link)
    try:
        reservation = trial_ledger.get_reservation(trial_id)
        budget = trial_ledger.get_budget(reservation.budget_id)
    except AdmissionError as error:
        raise EngineError("RESULT_ARTIFACT_MISMATCH") from error
    reservation_core = {
        "budget_id": reservation.budget_id,
        "declared_trial_number": reservation.declared_trial_number,
        "request_hash": reservation.request_hash,
        "initiated_by": reservation.initiated_by,
        "reserved_at": reservation.reserved_at,
    }
    deterministic_trial_id = f"trial-{canonical_hash(reservation_core)[:32]}"
    admission = bundle["admission"]
    budget_core = budget.as_dict()
    budget_hash = budget_core.pop("canonical_budget_hash")
    if (
        deterministic_trial_id != trial_id
        or admission["trial_id"] != trial_id
        or admission["request_hash"] != reservation.request_hash
        or admission["budget_id"] != reservation.budget_id
        or admission["declared_trial_number"] != reservation.declared_trial_number
        or admission["initiated_by"] != reservation.initiated_by
        or admission["reservation_reserved_at"] != reservation.reserved_at
        or admission["request_created_at"] != reservation.reserved_at
        or canonical_hash(budget_core) != budget_hash
        or admission["budget_hash"] != budget.canonical_budget_hash
        or admission["experiment_family"] != budget.experiment_family
        or admission["total_trial_budget"] != budget.total_trial_budget
        or budget.controlling_contract_id != MISSION_CONTRACT_ID
        or budget.controlling_contract_hash != MISSION_CONTRACT_HASH
        or budget.experiment_family != "MISSION_95_SYNTHETIC_CONTROLS"
    ):
        raise EngineError("RESULT_ARTIFACT_MISMATCH")
    return LinkedResult(
        result_bundle=result,
        trial_status_token=event.status_token,
        trial_reason_token=event.reason_token,
        trial_linked_at=link.linked_at,
    )


def load_linked_result(
    *,
    result_root: Path | str,
    trial_ledger: TrialLedger,
    trial_id: str,
) -> LinkedResult:
    """Load a linked result and normalize expected persisted-data failures."""

    try:
        return _load_linked_result_impl(
            result_root=result_root,
            trial_ledger=trial_ledger,
            trial_id=trial_id,
        )
    except EngineError:
        raise
    except (
        AdmissionError,
        KeyError,
        TypeError,
        ValueError,
        UnicodeError,
        OSError,
    ) as error:
        raise EngineError("RESULT_ARTIFACT_MISMATCH") from error
