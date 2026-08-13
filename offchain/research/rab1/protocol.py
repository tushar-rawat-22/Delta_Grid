"""RAB-1 contract verification and exact forward evidence calendar."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from offchain.market_data_acquisition.core import canonical_hash, strict_json_load
from offchain.research.development_runtime.registry import production_registry
from offchain.research.statistical_governance.core import AUTONOMY_V5_HASH, AUTONOMY_V5_ID, GovernanceError
from offchain.research.statistical_governance.registry import (
    production_protected_evaluator_registry,
    production_statistical_adapter_registry,
)


CONTRACT_ID = "deltagrid-rab1-prospective-protocol-v1"
CONTRACT_HASH = "f77816ebb283f540899f6cb33c30ce857886e5922b5ae588605380f822f264d2"
CONTRACT_PATH = Path(__file__).resolve().parents[3] / "contracts" / "DELTAGRID_RAB1_PROSPECTIVE_PROTOCOL_V1.json"
HOUR_MS = 3_600_000
DAY_MS = 86_400_000


def contract_hash(value: Mapping[str, Any]) -> str:
    core = dict(value)
    core.pop("contract_hash_sha256", None)
    return canonical_hash(core)


def load_contract() -> dict[str, Any]:
    value = strict_json_load(CONTRACT_PATH)
    if not isinstance(value, dict) or value.get("contract_id") != CONTRACT_ID:
        raise GovernanceError("RAB1_CONTRACT_ID_MISMATCH")
    if value.get("contract_hash_sha256") != CONTRACT_HASH or contract_hash(value) != CONTRACT_HASH:
        raise GovernanceError("RAB1_CONTRACT_HASH_MISMATCH")
    if (
        value.get("autonomy_constitution_id") != AUTONOMY_V5_ID
        or value.get("autonomy_constitution_hash_sha256") != AUTONOMY_V5_HASH
        or value.get("maximum_verdict", {}).get("authority_effect") != "NONE"
        or value.get("terminal_policy", {}).get("mission104_authorized") is not False
    ):
        raise GovernanceError("RAB1_CONTRACT_AUTHORITY_INVALID")
    authorization = value.get("production_registry_authorization")
    if not isinstance(authorization, dict):
        raise GovernanceError("RAB1_REGISTRY_AUTHORIZATION_INVALID")
    development = production_registry()
    statistical = production_statistical_adapter_registry()
    evaluators = production_protected_evaluator_registry()
    if (
        development.snapshot_hash != authorization.get("m102_registry_snapshot_hash")
        or statistical.snapshot_hash != authorization.get("m103_statistical_registry_snapshot_hash")
        or evaluators.snapshot_hash != authorization.get("m103_evaluator_registry_snapshot_hash")
    ):
        raise GovernanceError("RAB1_REGISTRY_AUTHORIZATION_INVALID")
    family, _ = development.resolve(authorization["family_id"], 1, 4)
    if family.definition_hash != authorization.get("family_hash"):
        raise GovernanceError("RAB1_REGISTRY_AUTHORIZATION_INVALID")
    variants = authorization.get("variants")
    if not isinstance(variants, list) or len(variants) != 4:
        raise GovernanceError("RAB1_REGISTRY_AUTHORIZATION_INVALID")
    for expected, declared in enumerate(variants, 1):
        _, variant = development.resolve(family.family_id, expected, 4)
        if declared != {
            "declared_trial_number": expected,
            "variant_id": variant.variant_id,
            "variant_hash": variant.definition_hash,
        }:
            raise GovernanceError("RAB1_REGISTRY_AUTHORIZATION_INVALID")
    statistical.resolve(authorization["statistical_adapter_id"], authorization["statistical_adapter_hash"])
    evaluators.resolve(authorization["protected_evaluator_id"], authorization["protected_evaluator_hash"])
    return value


def _t0(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError) as error:
        raise GovernanceError("RAB1_T0_INVALID") from error
    if parsed.minute or parsed.second or parsed.microsecond:
        raise GovernanceError("RAB1_T0_NOT_UTC_HOUR")
    return parsed


def _iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def evidence_calendar(t0: str) -> dict[str, Any]:
    start = _t0(t0)
    boundaries = {
        "T0": start,
        "WARMUP_END": start + timedelta(days=14),
        "DEVELOPMENT_END": start + timedelta(days=90),
        "REPLICATION_END": start + timedelta(days=120),
        "VALIDATION_END": start + timedelta(days=150),
        "HOLDOUT_END": start + timedelta(days=180),
    }
    return {
        "calendar_schema": "DELTAGRID_RAB1_FORWARD_EVIDENCE_CALENDAR_V1",
        "t0": _iso(start),
        "warmup": [_iso(start), _iso(boundaries["WARMUP_END"])],
        "development": [_iso(boundaries["WARMUP_END"]), _iso(boundaries["DEVELOPMENT_END"])],
        "replication": [_iso(boundaries["DEVELOPMENT_END"]), _iso(boundaries["REPLICATION_END"])],
        "validation": [_iso(boundaries["REPLICATION_END"]), _iso(boundaries["VALIDATION_END"])],
        "holdout": [_iso(boundaries["VALIDATION_END"]), _iso(boundaries["HOLDOUT_END"])],
        "earliest_terminal_verdict_at": _iso(boundaries["HOLDOUT_END"] + timedelta(hours=24)),
        "authority_effect": "NONE",
        "mission104_authorized": False,
    }


def protected_partition_specs(t0: str) -> list[dict[str, Any]]:
    start = _t0(t0)
    stages = (("REPLICATION", 90, 120), ("VALIDATION", 120, 150), ("HOLDOUT", 150, 180))
    specs = []
    for index, (stage, start_day, end_day) in enumerate(stages):
        nominal_start = start + timedelta(days=start_day)
        nominal_end = start + timedelta(days=end_day)
        # The final 24 hours are the embargo and the final hour is reserved for
        # forward outcome finalization. Context may overlap prior data but can
        # never create fills, positions, costs, funding, or PnL.
        scoring_end = nominal_end - timedelta(hours=25)
        context_start = nominal_start - timedelta(days=14) if index == 0 else nominal_start
        scoring_start = nominal_start if index == 0 else nominal_start + timedelta(days=14)
        specs.append({
            "schema_version": "1.0",
            "stage": stage,
            "stream_symbols": [
                "funding_rates:BTCUSDT", "funding_rates:ETHUSDT", "funding_rates:SOLUSDT",
                "perpetual_ohlcv:BTCUSDT", "perpetual_ohlcv:ETHUSDT", "perpetual_ohlcv:SOLUSDT",
            ],
            "stream_intervals": {"funding_rates": None, "perpetual_ohlcv": "1h"},
            "context_start": int(context_start.timestamp() * 1000),
            "scoring_start": int(scoring_start.timestamp() * 1000),
            "scoring_end": int(scoring_end.timestamp() * 1000),
            "availability_cutoff": _iso(nominal_end + timedelta(hours=24)),
            "time_unit": "MILLISECONDS",
            "minimum_samples": 1,
            "maximum_samples": 20_000,
            "purge_ms": 24 * HOUR_MS,
            "gap_ms": 0,
            "embargo_ms": 24 * HOUR_MS,
            "forward_horizon_ms": HOUR_MS,
            "data_certification_policy": "M99_M100_M101_VERIFIED",
            "availability_policy": "AVAILABLE_AT_OR_BEFORE_FROZEN_CUTOFF",
            "disjoint_from": [item[0] for item in stages[:index]],
            "protected_start_state": "FLAT_CASH",
        })
    return specs


def development_gates() -> list[dict[str, str]]:
    return [
        {"measurement_id": "net_pnl", "operator": "GT", "threshold": "0"},
        {"measurement_id": "daily_block_count", "operator": "GE", "threshold": "60"},
        {"measurement_id": "gross_pnl", "operator": "GT", "threshold": "0"},
        {"measurement_id": "max_drawdown", "operator": "LE", "threshold": "500"},
        {"measurement_id": "turnover", "operator": "GT", "threshold": "0"},
    ]


def protected_rules() -> dict[str, Any]:
    rule = {
        "statistic": "net_pnl",
        "direction": "GREATER",
        "threshold": "0",
        "measurement_gates": [
            {"measurement_id": "final_equity", "operator": "GT", "threshold": "10000"},
            {"measurement_id": "gross_pnl", "operator": "GT", "threshold": "0"},
            {"measurement_id": "turnover", "operator": "GT", "threshold": "0"},
            {"measurement_id": "max_drawdown", "operator": "LE", "threshold": "500"},
        ],
        "decision_rule": "M103_EXACT_ALL_GATES_AND_STATISTIC_V1",
        "minimum_scored_samples": 1,
    }
    return {stage: dict(rule) for stage in ("REPLICATION", "VALIDATION", "HOLDOUT")}
