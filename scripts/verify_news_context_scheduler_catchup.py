#!/usr/bin/env python3
"""Validate the synthetic-only News Context scheduler catch-up contract."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "contracts" / "fixtures" / "NEWS_CONTEXT_SCHEDULER_CATCHUP_V1.json"
FIXTURE_PATH = ROOT / "contracts" / "fixtures" / "news_context_scheduler_catchup_v1.json"


class ContractError(ValueError):
    """Raised when the scheduler catch-up contract or fixture fails closed."""


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_utc_z(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ContractError(f"{field} must be RFC3339 UTC with a trailing Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(f"{field} is not a valid RFC3339 timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise ContractError(f"{field} must be UTC")
    canonical = parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
    if value != canonical:
        raise ContractError(f"{field} must use canonical RFC3339 UTC second precision")
    return parsed


def manifest_identity(source_family: str, previous_watermark: str, window_start: str, window_end: str) -> str:
    payload = "|".join((source_family, previous_watermark, window_start, window_end))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate(contract: dict, fixture: dict) -> None:
    if contract.get("contract_id") != "NEWS_CONTEXT_SCHEDULER_CATCHUP_V1":
        raise ContractError("unexpected contract_id")
    if contract.get("authority_effect") != "NONE":
        raise ContractError("authority_effect must remain NONE")
    if fixture.get("contract_id") != contract["contract_id"]:
        raise ContractError("fixture contract_id mismatch")
    if fixture.get("fixture_kind") != "SYNTHETIC_METADATA_ONLY":
        raise ContractError("only synthetic metadata fixtures are allowed")

    scope = contract.get("scope", {})
    if not scope or any(value is not False for value in scope.values()):
        raise ContractError("all activating/authorizing scope flags must remain false")
    evidence = contract.get("evidence_boundary", {})
    if evidence.get("software_test_is_alpha_evidence") is not False:
        raise ContractError("software tests must not be classified as alpha evidence")
    if evidence.get("news_direction_authority") is not False:
        raise ContractError("news direction authority must remain false")

    planner = contract.get("planner", {})
    if planner.get("watermark_semantics") != "LAST_DURABLY_PERSISTED_WINDOW_END":
        raise ContractError("watermark must represent the last durably persisted window end")
    if planner.get("timestamp_format") != "RFC3339_UTC_SECONDS_Z":
        raise ContractError("scheduler timestamps must use canonical UTC second precision")
    if planner.get("window_start_rule") != "durable_watermark_minus_overlap":
        raise ContractError("window start rule changed")
    if planner.get("window_end_rule") != "invocation_time":
        raise ContractError("window end rule changed")
    if planner.get("future_window") != "REJECT":
        raise ContractError("future windows must be rejected")
    if planner.get("watermark_advance_rule") != "ONLY_AFTER_MANIFEST_PERSISTED":
        raise ContractError("watermark advancement must remain persistence-gated")
    if planner.get("watermark_regression") != "REJECT":
        raise ContractError("watermark regression must be rejected")

    overlap_seconds = planner.get("overlap_seconds")
    if not isinstance(overlap_seconds, int) or isinstance(overlap_seconds, bool) or overlap_seconds <= 0:
        raise ContractError("overlap_seconds must be a positive integer")

    idempotence = contract.get("idempotence", {})
    if idempotence.get("manifest_identity") != "sha256(source_family|previous_watermark|window_start|window_end)":
        raise ContractError("manifest identity formula changed")
    if idempotence.get("same_inputs_same_manifest") is not True:
        raise ContractError("same scheduler inputs must keep the same manifest identity")
    if idempotence.get("rerun_duplicate_action") != "NOOP_AFTER_DEDUPE":
        raise ContractError("reruns must remain dedupe-safe no-ops")

    failure = contract.get("failure_semantics", {})
    if failure.get("persistence_failure_advances_watermark") is not False:
        raise ContractError("persistence failure must not advance the watermark")
    if failure.get("scheduler_gap_requires_catchup") is not True:
        raise ContractError("scheduler gaps must require catch-up")
    if failure.get("source_unavailable_distinct_from_scheduler_gap") is not True:
        raise ContractError("source outage and scheduler gap must remain distinct")
    if failure.get("no_result_distinct_from_scheduler_gap") is not True:
        raise ContractError("zero-result and scheduler gap must remain distinct")

    allowed_sources = set(contract.get("source_families", []))
    if not allowed_sources:
        raise ContractError("source_families must remain non-empty")

    scenarios = fixture.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ContractError("fixture scenarios must be a non-empty list")

    seen_ids: set[str] = set()
    manifests_by_inputs: dict[tuple[str, str, str, str], str] = {}
    scenario_by_id: dict[str, dict] = {}

    for index, scenario in enumerate(scenarios):
        if not isinstance(scenario, dict):
            raise ContractError(f"scenario[{index}] must be an object")
        required = {
            "scenario_id",
            "source_family",
            "previous_watermark",
            "invocation_time",
            "expected_window_start",
            "expected_window_end",
            "manifest_persisted",
            "expected_next_watermark",
        }
        if set(scenario) != required:
            raise ContractError(f"scenario[{index}] fields must exactly match the closed scenario schema")

        scenario_id = scenario["scenario_id"]
        if not isinstance(scenario_id, str) or not scenario_id or scenario_id in seen_ids:
            raise ContractError(f"scenario[{index}] scenario_id must be unique and non-empty")
        seen_ids.add(scenario_id)
        scenario_by_id[scenario_id] = scenario

        source_family = scenario["source_family"]
        if source_family not in allowed_sources:
            raise ContractError(f"scenario[{index}] source_family is not admitted")
        if not isinstance(scenario["manifest_persisted"], bool):
            raise ContractError(f"scenario[{index}] manifest_persisted must be boolean")

        previous = parse_utc_z(scenario["previous_watermark"], f"scenario[{index}].previous_watermark")
        invocation = parse_utc_z(scenario["invocation_time"], f"scenario[{index}].invocation_time")
        window_start = parse_utc_z(scenario["expected_window_start"], f"scenario[{index}].expected_window_start")
        window_end = parse_utc_z(scenario["expected_window_end"], f"scenario[{index}].expected_window_end")
        next_watermark = parse_utc_z(
            scenario["expected_next_watermark"], f"scenario[{index}].expected_next_watermark"
        )

        if previous > invocation:
            raise ContractError(f"scenario[{index}] durable watermark is in the future")
        if window_start != previous - timedelta(seconds=overlap_seconds):
            raise ContractError(f"scenario[{index}] overlap window start is not deterministic")
        if window_end != invocation:
            raise ContractError(f"scenario[{index}] window end must equal invocation time")
        if not (window_start <= previous <= window_end):
            raise ContractError(f"scenario[{index}] planned window does not cover the durable watermark")

        expected_next = window_end if scenario["manifest_persisted"] else previous
        if next_watermark != expected_next:
            raise ContractError(f"scenario[{index}] watermark advancement violates persistence gate")
        if next_watermark < previous:
            raise ContractError(f"scenario[{index}] watermark regression")
        if window_end > invocation or next_watermark > invocation:
            raise ContractError(f"scenario[{index}] future-time leakage")

        inputs = (
            source_family,
            scenario["previous_watermark"],
            scenario["expected_window_start"],
            scenario["expected_window_end"],
        )
        identity = manifest_identity(*inputs)
        previous_identity = manifests_by_inputs.setdefault(inputs, identity)
        if previous_identity != identity:
            raise ContractError(f"scenario[{index}] identical inputs changed manifest identity")

    failed = scenario_by_id.get("manifest-persistence-failure")
    retry = scenario_by_id.get("retry-after-persistence-failure")
    if failed is None or retry is None:
        raise ContractError("fixture must include persistence failure and exact retry scenarios")
    retry_identity_fields = (
        "source_family",
        "previous_watermark",
        "invocation_time",
        "expected_window_start",
        "expected_window_end",
    )
    if any(failed[field] != retry[field] for field in retry_identity_fields):
        raise ContractError("retry after persistence failure must reproduce the exact same planned interval")
    if failed["manifest_persisted"] is not False or retry["manifest_persisted"] is not True:
        raise ContractError("persistence retry fixture states are invalid")
    if failed["expected_next_watermark"] != failed["previous_watermark"]:
        raise ContractError("failed persistence advanced its watermark")
    if retry["expected_next_watermark"] != retry["expected_window_end"]:
        raise ContractError("successful retry did not advance to the persisted window end")


def expect_failure(contract: dict, fixture: dict, mutate, label: str) -> None:
    candidate = copy.deepcopy(fixture)
    mutate(candidate)
    try:
        validate(contract, candidate)
    except ContractError:
        return
    raise AssertionError(f"negative self-test did not fail: {label}")


def self_test(contract: dict, fixture: dict) -> None:
    validate(contract, fixture)
    expect_failure(
        contract,
        fixture,
        lambda data: data["scenarios"][0].update(expected_window_end="2026-08-01T10:00:01Z"),
        "future window end",
    )
    expect_failure(
        contract,
        fixture,
        lambda data: data["scenarios"][2].update(expected_next_watermark="2026-08-01T13:30:00Z"),
        "failed persistence advances watermark",
    )
    expect_failure(
        contract,
        fixture,
        lambda data: data["scenarios"][3].update(invocation_time="2026-08-01T13:31:00Z"),
        "retry changes planned interval",
    )
    expect_failure(
        contract,
        fixture,
        lambda data: data["scenarios"][1].update(expected_window_start="2026-08-01T10:00:00Z"),
        "scheduler gap drops bounded overlap",
    )
    expect_failure(
        contract,
        fixture,
        lambda data: data["scenarios"][0].update(previous_watermark="2026-08-01T10:00:01Z"),
        "future durable watermark",
    )
    expect_failure(
        contract,
        fixture,
        lambda data: data["scenarios"][0].update(
            previous_watermark="2026-08-01T09:00:00.000Z",
            invocation_time="2026-08-01T10:00:00.000Z",
            expected_window_start="2026-08-01T08:55:00.000Z",
            expected_window_end="2026-08-01T10:00:00.000Z",
            expected_next_watermark="2026-08-01T10:00:00.000Z",
        ),
        "semantically identical timestamps create a second manifest spelling",
    )


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    fixture = load_json(FIXTURE_PATH)
    self_test(contract, fixture)
    print("NEWS_CONTEXT_SCHEDULER_CATCHUP_V1=PASS")
    print("fixture=SYNTHETIC_METADATA_ONLY")
    print("authority_effect=NONE")
    print("alpha_evidence=NO")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ContractError, AssertionError, json.JSONDecodeError) as exc:
        print(f"NEWS_CONTEXT_SCHEDULER_CATCHUP_V1=FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
