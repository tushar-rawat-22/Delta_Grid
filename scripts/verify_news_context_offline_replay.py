#!/usr/bin/env python3
"""Validate the synthetic-only News Context point-in-time replay contract."""

from __future__ import annotations

import copy
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "contracts" / "NEWS_CONTEXT_OFFLINE_REPLAY_V1.json"
FIXTURE_PATH = ROOT / "contracts" / "fixtures" / "news_context_offline_replay_v1.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ContractError(ValueError):
    """Raised when the replay contract or fixture fails closed."""


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
    return parsed


def validate(contract: dict, fixture: dict) -> None:
    if contract.get("contract_id") != "NEWS_CONTEXT_OFFLINE_REPLAY_V1":
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
    if contract.get("evidence_boundary", {}).get("software_test_is_alpha_evidence") is not False:
        raise ContractError("software tests must not be classified as alpha evidence")
    if contract.get("evidence_boundary", {}).get("news_direction_authority") is not False:
        raise ContractError("news direction authority must remain false")

    cutoff = parse_utc_z(fixture.get("replay_cutoff"), "replay_cutoff")
    required = set(contract.get("required_record_fields", []))
    allowed_sources = set(contract.get("source_families", []))
    allowed_states = set(contract.get("availability_states", []))
    forbidden = set(contract.get("forbidden_authority_fields", []))
    seen_dedupe = set()

    records = fixture.get("records")
    if not isinstance(records, list) or not records:
        raise ContractError("fixture records must be a non-empty list")

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ContractError(f"record[{index}] must be an object")
        missing = sorted(required - record.keys())
        if missing:
            raise ContractError(f"record[{index}] missing required fields: {missing}")
        forbidden_present = sorted(forbidden & record.keys())
        if forbidden_present:
            raise ContractError(f"record[{index}] contains forbidden authority fields: {forbidden_present}")
        if record["source_family"] not in allowed_sources:
            raise ContractError(f"record[{index}] source_family is not admitted")
        if record["availability_state"] not in allowed_states:
            raise ContractError(f"record[{index}] availability_state is not admitted")

        dedupe_key = record["dedupe_key"]
        if not isinstance(dedupe_key, str) or not dedupe_key:
            raise ContractError(f"record[{index}] dedupe_key must be non-empty")
        if dedupe_key in seen_dedupe:
            raise ContractError(f"record[{index}] duplicate dedupe_key")
        seen_dedupe.add(dedupe_key)

        published = parse_utc_z(record["published_at"], f"record[{index}].published_at")
        first_seen = parse_utc_z(record["first_seen_at"], f"record[{index}].first_seen_at")
        fetched = parse_utc_z(record["fetched_at"], f"record[{index}].fetched_at")

        if record["availability_state"] == "AVAILABLE":
            if not record["source_native_ref"]:
                raise ContractError(f"record[{index}] AVAILABLE record needs source_native_ref")
            if not SHA256_RE.fullmatch(record["provenance_sha256"]):
                raise ContractError(f"record[{index}] AVAILABLE record needs lowercase SHA-256")
            if not (published <= first_seen <= fetched <= cutoff):
                raise ContractError(
                    f"record[{index}] violates published <= first_seen <= fetched <= replay_cutoff"
                )
        else:
            if not (first_seen <= fetched <= cutoff):
                raise ContractError(
                    f"record[{index}] missing-state observation occurs after replay_cutoff"
                )


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
        lambda data: data["records"][0].update(first_seen_at="2026-08-01T12:00:01Z"),
        "future first_seen leakage",
    )
    expect_failure(
        contract,
        fixture,
        lambda data: data["records"][0].update(
            published_at="2026-08-01T10:05:00Z",
            first_seen_at="2026-08-01T10:02:00Z",
        ),
        "timestamp ordering",
    )
    expect_failure(
        contract,
        fixture,
        lambda data: data["records"][0].update(provenance_sha256="not-a-sha256"),
        "provenance hash",
    )
    expect_failure(
        contract,
        fixture,
        lambda data: data["records"][1].update(
            dedupe_key=data["records"][0]["dedupe_key"]
        ),
        "dedupe collision",
    )
    expect_failure(
        contract,
        fixture,
        lambda data: data["records"][0].update(direction_signal="BUY"),
        "forbidden direction authority",
    )


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    fixture = load_json(FIXTURE_PATH)
    self_test(contract, fixture)
    print("NEWS_CONTEXT_OFFLINE_REPLAY_V1=PASS")
    print("fixture=SYNTHETIC_METADATA_ONLY")
    print("authority_effect=NONE")
    print("alpha_evidence=NO")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ContractError, AssertionError, json.JSONDecodeError) as exc:
        print(f"NEWS_CONTEXT_OFFLINE_REPLAY_V1=FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
