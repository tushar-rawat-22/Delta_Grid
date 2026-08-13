"""Sealed RAB-1 statistical adapter and protected evaluator."""

from __future__ import annotations

from decimal import Decimal
import hashlib
from typing import Any, Mapping

from offchain.research.development_runtime.core import canonical_decimal
from offchain.research.statistical_governance.core import GovernanceError, canonical_hash
from offchain.research.statistical_governance.registry import ProtectedEvaluator, StatisticalAdapter


STATISTICAL_ADAPTER_ID = "RAB1_24H_BLOCK_SIGN_FLIP_ADAPTER_V1"
PROTECTED_EVALUATOR_ID = "RAB1_AUTHORITATIVE_M102_METRICS_EVALUATOR_V1"
NULL_ALGORITHM_ID = "RAB1_24H_BLOCK_SIGN_FLIP_V1"
DEVELOPMENT_MEASUREMENTS = {
    "daily_block_count", "gross_pnl", "max_drawdown", "net_pnl", "turnover",
}
PROTECTED_MEASUREMENTS = {"final_equity", "gross_pnl", "max_drawdown", "net_pnl", "turnover"}


def _sign(draw_hex: str, ordinal: int) -> Decimal:
    digest = hashlib.sha256(
        b"DELTAGRID_RAB1_24H_BLOCK_SIGN_FLIP_V1\x00"
        + bytes.fromhex(draw_hex)
        + ordinal.to_bytes(8, "big")
    ).digest()
    return Decimal(1) if digest[-1] & 1 else Decimal(-1)


def _statistical_function(value: Mapping[str, Any]) -> Mapping[str, Any]:
    required = {
        "input_schema", "verified_result", "primary_statistic", "direction", "null_policy",
        "randomization_plan", "_verified_trace",
    }
    if set(value) != required or value["input_schema"] != "DELTAGRID_M103_STATISTICAL_INPUT_V1":
        raise GovernanceError("RAB1_STATISTICAL_INPUT_INVALID")
    if value["primary_statistic"] != "net_pnl" or value["direction"] != "GREATER":
        raise GovernanceError("RAB1_STATISTICAL_PROTOCOL_INVALID")
    trace = value["_verified_trace"]
    if not isinstance(trace, Mapping) or set(trace) != {
        "trace_schema", "event_ledger_hash", "daily_net_pnl_blocks", "daily_block_count",
    }:
        raise GovernanceError("RAB1_VERIFIED_TRACE_INVALID")
    blocks_raw = trace["daily_net_pnl_blocks"]
    if not isinstance(blocks_raw, tuple) or trace["trace_schema"] != "RAB1_VERIFIED_EVENT_LEDGER_TRACE_V1":
        raise GovernanceError("RAB1_VERIFIED_TRACE_INVALID")
    try:
        blocks = [Decimal(item) for item in blocks_raw]
    except Exception as error:
        raise GovernanceError("RAB1_VERIFIED_TRACE_INVALID") from error
    if len(blocks) != trace["daily_block_count"] or not blocks or any(not item.is_finite() for item in blocks):
        raise GovernanceError("RAB1_VERIFIED_TRACE_INVALID")
    verified = value["verified_result"]
    metrics = verified.get("metrics") if isinstance(verified, Mapping) else None
    if not isinstance(metrics, Mapping) or not PROTECTED_MEASUREMENTS <= set(metrics):
        raise GovernanceError("RAB1_VERIFIED_METRICS_INVALID")
    observed = sum(blocks, Decimal(0))
    if observed != Decimal(metrics["net_pnl"]):
        raise GovernanceError("RAB1_TRACE_NET_PNL_MISMATCH")
    plan = value["randomization_plan"]
    if not isinstance(plan, Mapping) or plan.get("definition", {}).get("repetitions") != 9_999:
        raise GovernanceError("RAB1_RANDOMIZATION_PLAN_INVALID")
    entries = plan.get("entries")
    if not isinstance(entries, list) or len(entries) != 9_999:
        raise GovernanceError("RAB1_RANDOMIZATION_PLAN_INVALID")
    results = []
    for expected_ordinal, entry in enumerate(entries):
        if not isinstance(entry, Mapping) or entry.get("ordinal") != expected_ordinal:
            raise GovernanceError("RAB1_RANDOMIZATION_PLAN_INVALID")
        draw = entry.get("draw_u256_hex")
        if not isinstance(draw, str) or len(draw) != 64:
            raise GovernanceError("RAB1_RANDOMIZATION_PLAN_INVALID")
        statistic = sum((_sign(draw, index) * block for index, block in enumerate(blocks)), Decimal(0))
        results.append({
            "ordinal": expected_ordinal,
            "draw_u256_hex": draw,
            "statistic": canonical_decimal(statistic),
        })
    measurements = {
        "daily_block_count": str(len(blocks)),
        "gross_pnl": str(metrics["gross_pnl"]),
        "max_drawdown": str(metrics["max_drawdown"]),
        "net_pnl": str(metrics["net_pnl"]),
        "turnover": str(metrics["turnover"]),
    }
    null_core = {
        "kind": "EMPIRICAL_PLAN_RESULTS_V1",
        "observed_statistic": canonical_decimal(observed),
        "plan_commitment": plan["plan_commitment"],
        "results": results,
    }
    return {
        "null_evidence": {**null_core, "evidence_commitment": canonical_hash(null_core)},
        "measurements": measurements,
        "measurement_evidence_hash": canonical_hash(measurements),
    }


def _protected_function(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if set(value) != {
        "input_schema", "candidate_hash", "stage", "authoritative_metrics",
        "authoritative_ledger_hash", "execution_evidence_hash",
    } or value["input_schema"] != "DELTAGRID_M103_POST_EXECUTION_MEASUREMENT_INPUT_V1":
        raise GovernanceError("RAB1_PROTECTED_INPUT_INVALID")
    metrics = value["authoritative_metrics"]
    if not isinstance(metrics, Mapping) or not PROTECTED_MEASUREMENTS <= set(metrics):
        raise GovernanceError("RAB1_PROTECTED_METRICS_INVALID")
    measurements = {key: str(metrics[key]) for key in sorted(PROTECTED_MEASUREMENTS)}
    return {"measurements": measurements, "measurement_evidence_hash": canonical_hash(measurements)}


def statistical_adapter() -> StatisticalAdapter:
    return StatisticalAdapter(
        STATISTICAL_ADAPTER_ID,
        {
            "version": "RAB1_STATISTICAL_ADAPTER_V1",
            "input_schema": "DELTAGRID_M103_STATISTICAL_INPUT_V1",
            "output_schema": "DELTAGRID_M103_STATISTICAL_OUTPUT_V1",
            "null_algorithm": {
                "kind": "M103_SHA256_COUNTER_ORDINAL_PLAN_V1",
                "algorithm_id": NULL_ALGORITHM_ID,
                "plan_definition": "ORDINAL_AND_U256_DRAW_V1",
            },
            "measurement_algorithm": "RAB1_AUTHORITATIVE_METRICS_AND_24H_BLOCKS_V1",
            "deterministic": True,
        },
        _statistical_function,
    )


def protected_evaluator() -> ProtectedEvaluator:
    return ProtectedEvaluator(
        PROTECTED_EVALUATOR_ID,
        {
            "version": "RAB1_PROTECTED_EVALUATOR_V1",
            "input_schema": "DELTAGRID_M103_POST_EXECUTION_MEASUREMENT_INPUT_V1",
            "output_schema": "DELTAGRID_M103_POST_EXECUTION_MEASUREMENT_OUTPUT_V1",
            "measurement_algorithm": "RAB1_EXACT_AUTHORITATIVE_M102_DECIMAL_METRICS_V1",
            "deterministic": True,
        },
        _protected_function,
    )
