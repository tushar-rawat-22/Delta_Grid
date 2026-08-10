from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal, Inexact, ROUND_CEILING, Rounded, getcontext, setcontext
import hashlib
import json
from pathlib import Path
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import threading
from typing import Any, Mapping

import pytest

from offchain.research.development_runtime import (
    ACK_EXECUTE,
    ACK_INITIALIZE_RESULTS,
    AccountingKernel,
    DevelopmentRuntimeError,
    ExperimentRegistry,
    FamilyDefinition,
    MarketEvent,
    TargetExposureIntent,
    VariantDefinition,
    capture_authority_snapshot,
    execute_development_trial,
    initialize_result_runtime,
    load_causal_events,
    production_registry,
    read_trial_binding,
    verify_development_result,
    trial_lock,
    build_execution_specification,
    finalize_verified_result,
)
from offchain.research.development_runtime.finalizer import terminalize_failed_claim
from offchain.research.development_runtime.artifacts import build_result_artifacts
from offchain.research.development_runtime.runtime import claim_execution_spec, publish_artifact, trial_directory
from offchain.research.development_runtime import runtime as runtime_module
from offchain.research.development_runtime.core import (
    AUTONOMY_V4_HASH,
    EVENT_ORDERING_ID,
    MISSION102_HASH,
    canonical_bytes,
    canonical_hash,
)
from offchain.research.development_runtime.registry import ALL_STREAMS
from offchain.research.development_runtime import __main__ as cli_module
from offchain.tests import test_mission101_research_reopening as m101


ROOT = Path(__file__).resolve().parents[2]


def _shift_utc(value: str, **delta: int) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) + timedelta(**delta)
    return parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@pytest.fixture(scope="module")
def m102_source_backup(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return m101.source_backup.__wrapped__(tmp_path_factory)


@pytest.fixture
def chain(tmp_path: Path, m102_source_backup: Path) -> dict[str, Any]:
    return m101.chain.__wrapped__(tmp_path, m102_source_backup)


class _OneShotAdapter:
    def __init__(self, parameters: Mapping[str, Any]) -> None:
        self.target = parameters["target_notional"]
        self.seen = 0

    def on_event(self, event, state):
        del state
        self.seen += 1
        if self.seen == 1:
            return [TargetExposureIntent(event.symbol, "spot_ohlcv", self.target)]
        return []


def _registry(*, fee: str = "1", slippage: str = "2") -> ExperimentRegistry:
    variant = VariantDefinition(
        variant_id="variant-1",
        required_streams=("spot_ohlcv",),
        required_symbols=("BTCUSDT",),
        observable_inputs=("spot_ohlcv:BTCUSDT",),
        tradable_instruments=("spot_ohlcv:BTCUSDT",),
        informational_streams=(),
        initial_research_nav="10000",
        max_gross_research_exposure="1000",
        max_net_research_exposure="1000",
        per_instrument_bounds={"spot_ohlcv:BTCUSDT": "1000"},
        fee_bps=fee,
        slippage_bps=slippage,
        funding_accounting_applicable=False,
        strategy_parameters={"target_notional": "100"},
    )
    return ExperimentRegistry((FamilyDefinition(
        family_id="M101_METADATA_ONLY_FAMILY", variants=(variant,),
        adapter_factory=lambda parameters: _OneShotAdapter(parameters),
    ),))


def _admit_budget_one(chain: dict[str, Any]) -> tuple[dict[str, Any], Any, dict[str, Any]]:
    permit = m101._permit_with_budget(chain, 1)
    ledger = m101._private_ledger(chain, "m102-ledger", "m102-budget", 1)
    request = m101._request_for(
        chain, permit, request_id="m102-request", budget_id="m102-budget"
    )
    decision = m101._admission_service(chain, ledger).admit(request)
    assert decision["decision_token"] == "ADMITTED"
    return permit, ledger, decision


def test_contract_lineage_hashes_and_authority_boundaries() -> None:
    v4 = json.loads((ROOT / "contracts/DELTAGRID_AUTONOMY_CONSTITUTION_V4.json").read_text())
    m102 = json.loads((ROOT / "contracts/DELTAGRID_DEVELOPMENT_RESEARCH_RUNTIME_V1.json").read_text())
    for value, expected in ((v4, AUTONOMY_V4_HASH), (m102, MISSION102_HASH)):
        core = dict(value); core.pop("contract_hash_sha256")
        assert canonical_hash(core) == expected == value["contract_hash_sha256"]
    assert v4["parent_constitution_hash_sha256"] == "cdd768ee04693845f9c1dcc4af3a03bad03a62685b24681d1ff8426230c84743"
    assert m102["base_commit"] == "38417b1ceab82b381d2535ff146a7e6a843c3815"
    assert m102["authority"]["real_market_development_result_execution"] is True
    assert all(value is False for key, value in m102["authority"].items() if key != "real_market_development_result_execution")
    assert EVENT_ORDERING_ID == "AVAILABLE_AT_THEN_CUSTODY_RECORD_HASH_V1"
    assert m102["identities"]["event_ordering"] == EVENT_ORDERING_ID
    assert m102["identities"]["instrument_identity"] == "STREAM_COLON_SYMBOL_V1"


def test_v1_v2_v3_and_upstream_contract_bytes_unchanged() -> None:
    expected = {
        "DELTAGRID_AUTONOMY_CONSTITUTION_V1.json": "b9b1d48dd3f65ac492b287e9d5dcebe11f69063138698bf37432c11869a3da5b",
        "DELTAGRID_AUTONOMY_CONSTITUTION_V2.json": "a9d830e14ad1d93efbfd7529e9ee937926d577aeb63792acf900fbc80d968664",
        "DELTAGRID_AUTONOMY_CONSTITUTION_V3.json": "cdd768ee04693845f9c1dcc4af3a03bad03a62685b24681d1ff8426230c84743",
        "DELTAGRID_RESEARCH_ADMISSION_CORE_V1.json": "e4070b52a0f2dbc8ce34ea00d0a732c2aed25c9c21e5acfccc3f9d791dba6193",
        "DELTAGRID_CANONICAL_RESULT_ENGINE_SERVICE_V1.json": "d8fcd1169e638b648f8b5fccb389dfd090b016beb80e9e13d7f0a0af3210aa6a",
        "DELTAGRID_TEMPORAL_MARKET_DATA_CONTROL_PLANE_V1.json": "159a822f77e3c6bf6409e04b2c25a61c5c7232cf6e73ea160ffb6cbf167d5d4c",
        "DELTAGRID_FORWARD_MARKET_DATA_ACQUISITION_V1.json": "42f1ebe86264268763978d6969c2a605924805433a041647f2625dfd297e16e3",
        "DELTAGRID_RESEARCH_REOPENING_GOVERNANCE_V1.json": "067e85fa1eb35b4fa81cac40fd036938df300d2b7da2774b163f1e306ce53ce7",
    }
    for name, digest in expected.items():
        value = json.loads((ROOT / "contracts" / name).read_text())
        core = dict(value); core.pop("contract_hash_sha256")
        assert canonical_hash(core) == value["contract_hash_sha256"] == digest


def test_consumed_budget_one_exact_trial_passes_unrelated_trial_rejects(chain: dict[str, Any]) -> None:
    permit, ledger, decision = _admit_budget_one(chain)
    before = sqlite3.connect(chain["authority_root"] / "authority.sqlite3").execute("SELECT COUNT(*) FROM permit_consumptions").fetchone()[0]
    snapshot = capture_authority_snapshot(
        trial_id=decision["trial_id"], ledger_path=ledger.database_path,
        authority_root=chain["authority_root"], descriptor=chain["descriptor"],
        time_provider=lambda: chain["as_of"], repository_observer=m101._repository_observer(),
    )
    assert snapshot["effective_permit_state"] == "ISSUED"
    assert snapshot["consumption_id"].startswith("permit-consumption-")
    assert snapshot["permit_id"] == permit["permit_id"]
    assert sqlite3.connect(chain["authority_root"] / "authority.sqlite3").execute("SELECT COUNT(*) FROM permit_consumptions").fetchone()[0] == before

    other = m101._private_ledger(chain, "m102-other", "m102-other", 1)
    reservation = other.reserve(
        budget_id="m102-other", declared_trial_number=1, request_hash="a" * 64,
        initiated_by="OPERATOR", reserved_at=chain["as_of"],
        controlling_contract_id=m101.MISSION101_ID,
        controlling_contract_hash=m101.MISSION101_HASH,
    )
    other.append_event(trial_id=reservation.trial_id, status_token="ADMITTED", reason_token="M101_DEVELOPMENT_ADMISSION_GATES_PASSED", event_timestamp=chain["as_of"])
    with pytest.raises(DevelopmentRuntimeError, match="EXACT_PERMIT_CONSUMPTION_REQUIRED"):
        capture_authority_snapshot(
            trial_id=reservation.trial_id, ledger_path=other.database_path,
            authority_root=chain["authority_root"], descriptor=chain["descriptor"],
            time_provider=lambda: chain["as_of"], repository_observer=m101._repository_observer(),
        )


def test_revocation_and_expiry_snapshot_semantics(chain: dict[str, Any]) -> None:
    permit, ledger, decision = _admit_budget_one(chain)
    snapshot = capture_authority_snapshot(
        trial_id=decision["trial_id"], ledger_path=ledger.database_path,
        authority_root=chain["authority_root"], descriptor=chain["descriptor"],
        time_provider=lambda: chain["as_of"], repository_observer=m101._repository_observer(),
    )
    assert snapshot["effective_permit_state"] == "ISSUED"
    with pytest.raises(DevelopmentRuntimeError, match="PERMIT_EXPIRED"):
        capture_authority_snapshot(
            trial_id=decision["trial_id"], ledger_path=ledger.database_path,
            authority_root=chain["authority_root"], descriptor=chain["descriptor"],
            time_provider=lambda: chain["expires_at"], repository_observer=m101._repository_observer(),
        )
    m101.revoke_development_permit(
        chain["authority_root"], permit["permit_id"],
        acknowledgement=m101.ACK_REVOKE_PERMIT, time_provider=lambda: chain["as_of"],
    )
    # The already-returned snapshot remains the in-process linearization fact.
    assert snapshot["effective_permit_state"] == "ISSUED"
    with pytest.raises(DevelopmentRuntimeError, match="PERMIT_REVOKED"):
        capture_authority_snapshot(
            trial_id=decision["trial_id"], ledger_path=ledger.database_path,
            authority_root=chain["authority_root"], descriptor=chain["descriptor"],
            time_provider=lambda: chain["as_of"], repository_observer=m101._repository_observer(),
        )
    with pytest.raises(DevelopmentRuntimeError, match="PERMIT_REVOKED_AT_EXECUTION"):
        capture_authority_snapshot(
            trial_id=decision["trial_id"], ledger_path=ledger.database_path,
            authority_root=chain["authority_root"], descriptor=chain["descriptor"],
            authority_decision_time=chain["as_of"], require_current=False,
            repository_observer=m101._repository_observer(),
        )


def test_current_snapshot_rejects_visible_revocation_after_decision_timestamp(chain: dict[str, Any]) -> None:
    permit, ledger, decision = _admit_budget_one(chain)
    decision_timestamp = chain["as_of"]
    m101.revoke_development_permit(
        chain["authority_root"], permit["permit_id"],
        acknowledgement=m101.ACK_REVOKE_PERMIT,
        time_provider=lambda: chain["expires_at"],
    )
    with pytest.raises(DevelopmentRuntimeError, match="PERMIT_REVOKED"):
        capture_authority_snapshot(
            trial_id=decision["trial_id"], ledger_path=ledger.database_path,
            authority_root=chain["authority_root"], descriptor=chain["descriptor"],
            time_provider=lambda: decision_timestamp,
            repository_observer=m101._repository_observer(),
        )
    historical = capture_authority_snapshot(
        trial_id=decision["trial_id"], ledger_path=ledger.database_path,
        authority_root=chain["authority_root"], descriptor=chain["descriptor"],
        authority_decision_time=decision_timestamp, require_current=False,
        repository_observer=m101._repository_observer(),
    )
    assert historical["effective_permit_state"] == "ISSUED"


def test_authority_clock_is_sampled_after_snapshot_and_historical_time_is_causal(chain: dict[str, Any]) -> None:
    permit, ledger, decision = _admit_budget_one(chain)
    revocation_done = threading.Event()
    revocation_error: list[BaseException] = []

    def revoke() -> None:
        try:
            m101.revoke_development_permit(
                chain["authority_root"], permit["permit_id"],
                acknowledgement=m101.ACK_REVOKE_PERMIT,
                time_provider=lambda: chain["expires_at"],
            )
        except BaseException as error:
            revocation_error.append(error)
        finally:
            revocation_done.set()

    def revoke_after_snapshot_then_sample() -> str:
        threading.Thread(target=revoke, daemon=True).start()
        return chain["as_of"]

    snapshot = capture_authority_snapshot(
        trial_id=decision["trial_id"], ledger_path=ledger.database_path,
        authority_root=chain["authority_root"], descriptor=chain["descriptor"],
        time_provider=revoke_after_snapshot_then_sample,
        repository_observer=m101._repository_observer(),
    )
    assert revocation_done.wait(timeout=5)
    assert revocation_error == []
    assert snapshot["authority_decision_time"] == chain["as_of"]
    assert snapshot["effective_permit_state"] == "ISSUED"
    with pytest.raises(DevelopmentRuntimeError, match="PERMIT_REVOKED"):
        capture_authority_snapshot(
            trial_id=decision["trial_id"], ledger_path=ledger.database_path,
            authority_root=chain["authority_root"], descriptor=chain["descriptor"],
            time_provider=lambda: chain["as_of"],
            repository_observer=m101._repository_observer(),
        )
    historical = capture_authority_snapshot(
        trial_id=decision["trial_id"], ledger_path=ledger.database_path,
        authority_root=chain["authority_root"], descriptor=chain["descriptor"],
        authority_decision_time=chain["as_of"], require_current=False,
        repository_observer=m101._repository_observer(),
    )
    assert historical["authority_snapshot_hash"] == snapshot["authority_snapshot_hash"]
    with pytest.raises(DevelopmentRuntimeError, match="PERMIT_EXPIRED"):
        capture_authority_snapshot(
            trial_id=decision["trial_id"], ledger_path=ledger.database_path,
            authority_root=chain["authority_root"], descriptor=chain["descriptor"],
            authority_decision_time=chain["expires_at"], require_current=False,
            repository_observer=m101._repository_observer(),
        )


def test_final_m94_gate_blocks_terminalization_and_timestamp_mismatches(chain: dict[str, Any]) -> None:
    _permit, ledger, decision = _admit_budget_one(chain)

    def terminalize_after_m101_snapshot() -> str:
        ledger.append_event(
            trial_id=decision["trial_id"], status_token="FAILED",
            reason_token="CONCURRENT_TEST_TERMINALIZATION",
            event_timestamp=chain["as_of"],
        )
        return chain["as_of"]

    with pytest.raises(DevelopmentRuntimeError, match="TRIAL_TERMINAL"):
        capture_authority_snapshot(
            trial_id=decision["trial_id"], ledger_path=ledger.database_path,
            authority_root=chain["authority_root"], descriptor=chain["descriptor"],
            time_provider=terminalize_after_m101_snapshot,
            repository_observer=m101._repository_observer(),
        )

    mismatch = m101._private_ledger(chain, "mismatch-ledger", "mismatch-budget", 1)
    reservation = mismatch.reserve(
        budget_id="mismatch-budget", declared_trial_number=1,
        request_hash="f" * 64, initiated_by="OPERATOR",
        reserved_at=chain["as_of"], controlling_contract_id=m101.MISSION101_ID,
        controlling_contract_hash=m101.MISSION101_HASH,
    )
    mismatch.append_event(
        trial_id=reservation.trial_id, status_token="ADMITTED",
        reason_token="M101_DEVELOPMENT_ADMISSION_GATES_PASSED",
        event_timestamp=_shift_utc(chain["as_of"], seconds=1),
    )
    with pytest.raises(DevelopmentRuntimeError, match="M101_ADMISSION_TIMESTAMP_MISMATCH"):
        read_trial_binding(mismatch.database_path, reservation.trial_id)

    regression = m101._private_ledger(chain, "regression-ledger", "regression-budget", 1)
    reg = regression.reserve(
        budget_id="regression-budget", declared_trial_number=1,
        request_hash="e" * 64, initiated_by="OPERATOR",
        reserved_at=chain["as_of"], controlling_contract_id=m101.MISSION101_ID,
        controlling_contract_hash=m101.MISSION101_HASH,
    )
    regression.append_event(
        trial_id=reg.trial_id, status_token="ADMITTED",
        reason_token="M101_DEVELOPMENT_ADMISSION_GATES_PASSED",
        event_timestamp=_shift_utc(chain["as_of"], seconds=-1),
    )
    with pytest.raises(DevelopmentRuntimeError, match="TRIAL_EVENT_TIME_REGRESSION"):
        read_trial_binding(regression.database_path, reg.trial_id)


def test_successful_two_store_gate_is_not_retroactively_rewritten(chain: dict[str, Any]) -> None:
    _permit, ledger, decision = _admit_budget_one(chain)
    snapshot = capture_authority_snapshot(
        trial_id=decision["trial_id"], ledger_path=ledger.database_path,
        authority_root=chain["authority_root"], descriptor=chain["descriptor"],
        time_provider=lambda: chain["as_of"],
        repository_observer=m101._repository_observer(),
    )
    proof_hash = snapshot["authority_snapshot_hash"]
    ledger.append_event(
        trial_id=decision["trial_id"], status_token="FAILED",
        reason_token="POST_GATE_TEST_TERMINALIZATION",
        event_timestamp=chain["as_of"],
    )
    assert snapshot["authority_snapshot_hash"] == proof_hash
    with pytest.raises(DevelopmentRuntimeError, match="TRIAL_TERMINAL"):
        read_trial_binding(ledger.database_path, decision["trial_id"])


def test_registry_is_empty_deterministic_and_cli_cannot_inject_adapter() -> None:
    first = production_registry()
    second = production_registry()
    assert first.family_count == 0
    assert first.snapshot_hash == second.snapshot_hash
    assert _registry().snapshot_hash == _registry().snapshot_hash
    parser = cli_module.build_parser()
    option_text = " ".join(action.dest for action in parser._actions)
    assert "module" not in option_text and "strategy_file" not in option_text and "plugin" not in option_text


def test_strategy_parameters_are_recursively_copied_frozen_and_thawed() -> None:
    caller_parameters = {
        "target_notional": "100",
        "nested": {"levels": ["1", {"enabled": True, "count": 2}]},
    }
    base = _registry().resolve("M101_METADATA_ONLY_FAMILY", 1, 1)[1]
    variant = replace(base, strategy_parameters=caller_parameters)
    family = FamilyDefinition(
        family_id="deep-freeze-family", variants=(variant,),
        adapter_factory=lambda parameters: _OneShotAdapter(parameters),
    )
    registry = ExperimentRegistry((family,))
    identities = (variant.definition_hash, family.definition_hash, registry.snapshot_hash)
    caller_parameters["nested"]["levels"][1]["count"] = 999
    caller_parameters["nested"]["levels"].append("new")
    assert (variant.definition_hash, family.definition_hash, registry.snapshot_hash) == identities
    assert variant.core()["strategy_parameters"]["nested"]["levels"] == [
        "1", {"enabled": True, "count": 2},
    ]
    detached = variant.core()
    detached["strategy_parameters"]["nested"]["levels"][1]["count"] = -1
    assert variant.definition_hash == identities[0]
    with pytest.raises(TypeError):
        variant.strategy_parameters["nested"]["levels"][1]["count"] = 3
    with pytest.raises(DevelopmentRuntimeError, match="STRATEGY_PARAMETER_TYPE_INVALID"):
        replace(base, strategy_parameters={"economic_float": 1.25})


def test_one_trial_one_specification_conflict_and_identical_recovery(chain: dict[str, Any]) -> None:
    _permit, ledger, decision = _admit_budget_one(chain)
    snapshot = capture_authority_snapshot(
        trial_id=decision["trial_id"], ledger_path=ledger.database_path,
        authority_root=chain["authority_root"], descriptor=chain["descriptor"],
        time_provider=lambda: chain["as_of"], repository_observer=m101._repository_observer(),
    )
    first_registry = _registry(fee="1")
    first_family, first_variant = first_registry.resolve("M101_METADATA_ONLY_FAMILY", 1, 1)
    first = build_execution_specification(snapshot, chain["descriptor"], first_registry, first_family, first_variant)
    second_registry = _registry(fee="9")
    second_family, second_variant = second_registry.resolve("M101_METADATA_ONLY_FAMILY", 1, 1)
    second = build_execution_specification(snapshot, chain["descriptor"], second_registry, second_family, second_variant)
    root = chain["temp"] / "claim-results"
    initialize_result_runtime(root, acknowledgement=ACK_INITIALIZE_RESULTS)
    directory = trial_directory(root, decision["trial_id"], create=True)
    assert claim_execution_spec(directory, first)[1] is False
    assert claim_execution_spec(directory, first)[1] is True
    with pytest.raises(DevelopmentRuntimeError, match="EXECUTION_SPEC_CONFLICT"):
        claim_execution_spec(directory, second)


def _bar(
    number: int, *, available: str, close_time: int, close: str = "10",
    stream: str = "spot_ohlcv", symbol: str = "BTCUSDT",
) -> MarketEvent:
    payload = {
        "open_time_ms": close_time - 10, "close_time_ms": close_time,
        "open": close, "high": close, "low": close, "close": close,
        "volume": "1", "quote_volume": "10", "trade_count": 1,
        "normalizer_id": "x", "availability_policy_id": "x",
    }
    digest = hashlib.sha256(f"event-{number}-{stream}-{symbol}".encode()).hexdigest()
    return MarketEvent(
        event_id=f"m102-event-{digest}", custody_record_hash=digest,
        source_m100_record_hash=hashlib.sha256(f"source-{number}".encode()).hexdigest(),
        stream=stream, symbol=symbol, interval="1h",
        event_time_ms=close_time, available_at=available, revision=1,
        payload_hash=canonical_hash(payload), payload=payload,
    )


def test_causal_next_eligible_close_no_same_event_or_end_fill() -> None:
    variant = _registry().resolve("M101_METADATA_ONLY_FAMILY", 1, 1)[1]
    adapter = _OneShotAdapter({"target_notional": "100"})
    events = (
        _bar(1, available="1970-01-01T00:00:01.000000Z", close_time=500),
        _bar(2, available="1970-01-01T00:00:02.000000Z", close_time=1500),
        _bar(3, available="1970-01-01T00:00:03.000000Z", close_time=2500),
    )
    ledger, metrics = AccountingKernel(variant, adapter).run(events)
    assert len(ledger["fill_rows"]) == 1
    fill = ledger["fill_rows"][0]
    assert fill["fill_event_id"] == events[1].event_id
    assert fill["benchmark_close_time_ms"] == 1500
    assert fill["benchmark_price"] == "10"
    assert metrics["unfilled_intent_count"] == 0
    one_event_ledger, one_event_metrics = AccountingKernel(variant, _OneShotAdapter({"target_notional": "100"})).run(events[:1])
    assert one_event_ledger["fill_rows"] == []
    assert one_event_metrics["unfilled_intent_count"] == 1


def test_adapter_view_has_no_future_iterator_or_unrevealed_collection() -> None:
    variant = _registry().resolve("M101_METADATA_ONLY_FAMILY", 1, 1)[1]
    observed = []
    class Inspect:
        def on_event(self, event, state):
            observed.append((set(vars(event)), set(state)))
            return []
    AccountingKernel(variant, Inspect()).run((
        _bar(1, available="1970-01-01T00:00:01.000000Z", close_time=500),
        _bar(2, available="1970-01-01T00:00:02.000000Z", close_time=1500),
    ))
    assert all(not ({"future", "next_event", "events", "iterator"} & event_fields) for event_fields, _ in observed)
    assert all(not ({"future", "next_event", "events", "iterator"} & state_fields) for _, state_fields in observed)


def test_frozen_decimal_context_ignores_hostile_ambient_context(chain: dict[str, Any]) -> None:
    _permit, ledger, decision = _admit_budget_one(chain)
    snapshot = capture_authority_snapshot(
        trial_id=decision["trial_id"], ledger_path=ledger.database_path,
        authority_root=chain["authority_root"], descriptor=chain["descriptor"],
        time_provider=lambda: chain["as_of"],
        repository_observer=m101._repository_observer(),
    )
    events = (
        _bar(10, available="1970-01-01T00:00:01.000000Z", close_time=500, close="3"),
        _bar(11, available="1970-01-01T00:00:02.000000Z", close_time=1500, close="7"),
    )

    def artifacts() -> tuple[bytes, bytes, bytes]:
        registry = _registry(fee="1.25", slippage="2.5")
        family, variant = registry.resolve("M101_METADATA_ONLY_FAMILY", 1, 1)
        spec = build_execution_specification(snapshot, chain["descriptor"], registry, family, variant)
        event_ledger, metrics = AccountingKernel(
            variant, _OneShotAdapter({"target_notional": "100"}),
        ).run(events)
        bound_ledger, result = build_result_artifacts(spec, event_ledger, metrics)
        return canonical_bytes(spec), canonical_bytes(bound_ledger), canonical_bytes(result)

    baseline = artifacts()
    saved = getcontext().copy()
    try:
        hostile = getcontext()
        hostile.prec = 7
        hostile.rounding = ROUND_CEILING
        hostile.Emin = -9
        hostile.Emax = 9
        hostile.traps[Inexact] = True
        hostile.traps[Rounded] = True
        assert artifacts() == baseline
    finally:
        setcontext(saved)


def test_spot_short_rejected_and_decimal_accounting_has_no_float() -> None:
    variant = _registry().resolve("M101_METADATA_ONLY_FAMILY", 1, 1)[1]
    class Short:
        def on_event(self, event, state):
            return [TargetExposureIntent("BTCUSDT", "spot_ohlcv", "-1")]
    with pytest.raises(DevelopmentRuntimeError, match="SPOT_SHORT_FORBIDDEN"):
        AccountingKernel(variant, Short()).run((_bar(1, available="1970-01-01T00:00:01.000000Z", close_time=2000),))
    ledger, metrics = AccountingKernel(variant, _OneShotAdapter({"target_notional": "100"})).run((
        _bar(1, available="1970-01-01T00:00:01.000000Z", close_time=500),
        _bar(2, available="1970-01-01T00:00:02.000000Z", close_time=1500),
    ))
    assert not any(isinstance(value, float) for value in metrics.values())
    assert "profitable" not in json.dumps({"ledger": ledger, "metrics": metrics})


def test_same_symbol_spot_and_perpetual_positions_are_independent() -> None:
    variant = VariantDefinition(
        variant_id="mixed-same-symbol",
        required_streams=("spot_ohlcv", "perpetual_ohlcv", "funding_rates"),
        required_symbols=("BTCUSDT",),
        observable_inputs=(
            "spot_ohlcv:BTCUSDT", "perpetual_ohlcv:BTCUSDT", "funding_rates:BTCUSDT",
        ),
        tradable_instruments=("spot_ohlcv:BTCUSDT", "perpetual_ohlcv:BTCUSDT"),
        informational_streams=("funding_rates",), initial_research_nav="10000",
        max_gross_research_exposure="1000", max_net_research_exposure="1000",
        per_instrument_bounds={
            "spot_ohlcv:BTCUSDT": "1000", "perpetual_ohlcv:BTCUSDT": "1000",
        },
        fee_bps="0", slippage_bps="0", funding_accounting_applicable=True,
        strategy_parameters={},
    )

    class Opposite:
        def __init__(self): self.done = False
        def on_event(self, event, state):
            del event, state
            if self.done: return []
            self.done = True
            return [
                TargetExposureIntent("BTCUSDT", "spot_ohlcv", "100"),
                TargetExposureIntent("BTCUSDT", "perpetual_ohlcv", "-100"),
            ]

    events = (
        _bar(20, available="1970-01-01T00:00:01.000000Z", close_time=500),
        _bar(21, available="1970-01-01T00:00:02.000000Z", close_time=1500, close="20", stream="perpetual_ohlcv"),
        _bar(22, available="1970-01-01T00:00:03.000000Z", close_time=2500),
        _funding(20, rate="0.01", available="1970-01-01T00:00:04.000000Z", economic_time=2500),
    )
    ledger, metrics = AccountingKernel(variant, Opposite()).run(events)
    assert metrics["positions"] == {
        "perpetual_ohlcv:BTCUSDT": "-5", "spot_ohlcv:BTCUSDT": "10",
    }
    assert metrics["gross_exposure"] == "200"
    assert metrics["net_exposure"] == "0"
    assert {row["instrument_id"] for row in ledger["fill_rows"]} == set(metrics["positions"])
    assert Decimal(metrics["funding_cash_flow"]) > 0
    assert ledger["funding_rows"][0]["instrument_id"] == "perpetual_ohlcv:BTCUSDT"


@pytest.mark.parametrize("bad_price", ["0", "-1"])
def test_zero_or_negative_execution_price_fails_closed(bad_price: str) -> None:
    variant = _registry(fee="0", slippage="0").resolve("M101_METADATA_ONLY_FAMILY", 1, 1)[1]
    events = (
        _bar(23, available="1970-01-01T00:00:01.000000Z", close_time=500),
        _bar(24, available="1970-01-01T00:00:02.000000Z", close_time=1500, close=bad_price),
    )
    with pytest.raises(DevelopmentRuntimeError, match="EXECUTION_PRICE_INVALID"):
        AccountingKernel(variant, _OneShotAdapter({"target_notional": "100"})).run(events)


def test_target_notional_slippage_cannot_reverse_sell_direction() -> None:
    variant = _registry(fee="0", slippage="100").resolve("M101_METADATA_ONLY_FAMILY", 1, 1)[1]

    class EnterThenReduce:
        def __init__(self): self.count = 0
        def on_event(self, event, state):
            del state
            self.count += 1
            if self.count == 1:
                return [TargetExposureIntent(event.symbol, "spot_ohlcv", "100")]
            if self.count == 2:
                return [TargetExposureIntent(event.symbol, "spot_ohlcv", "99.5")]
            return []

    ledger, metrics = AccountingKernel(variant, EnterThenReduce()).run((
        _bar(25, available="1970-01-01T00:00:01.000000Z", close_time=500, close="100"),
        _bar(26, available="1970-01-01T00:00:02.000000Z", close_time=1500, close="100"),
        _bar(27, available="1970-01-01T00:00:03.000000Z", close_time=2500, close="100"),
    ))
    reduction = ledger["fill_rows"][1]
    assert reduction["target_notional"] == "99.5"
    assert reduction["target_quantity_at_benchmark"] == "0.995"
    assert reduction["benchmark_price"] == "100"
    assert reduction["execution_price"] == "99"
    assert reduction["quantity_delta"] == "-0.005"
    assert reduction["position_after"] == "0.995"
    assert metrics["positions"]["spot_ohlcv:BTCUSDT"] == "0.995"


@pytest.mark.parametrize(
    "start,target,expected_direction",
    [("100", "99.5", -1), ("-100", "-99.5", 1)],
)
def test_large_allowed_slippage_never_reverses_reduction(
    start: str, target: str, expected_direction: int,
) -> None:
    variant = replace(_perpetual_variant(), slippage_bps="9000")

    class Reduce:
        def __init__(self): self.count = 0
        def on_event(self, event, state):
            del state
            if event.stream != "perpetual_ohlcv": return []
            self.count += 1
            if self.count == 1: return [TargetExposureIntent("BTCUSDT", "perpetual_ohlcv", start)]
            if self.count == 2: return [TargetExposureIntent("BTCUSDT", "perpetual_ohlcv", target)]
            return []

    ledger, _metrics = AccountingKernel(variant, Reduce()).run((
        _perp_bar(28, available="1970-01-01T00:00:01.000000Z", close_time=500),
        _perp_bar(29, available="1970-01-01T00:00:02.000000Z", close_time=1500),
        _perp_bar(30, available="1970-01-01T00:00:03.000000Z", close_time=2500),
    ))
    delta = Decimal(ledger["fill_rows"][1]["quantity_delta"])
    assert (delta > 0) - (delta < 0) == expected_direction


def test_informational_bars_cannot_mark_tradable_position() -> None:
    base = _registry(fee="0", slippage="0").resolve("M101_METADATA_ONLY_FAMILY", 1, 1)[1]
    variant = replace(
        base,
        required_streams=("spot_ohlcv", "mark_price_ohlcv", "index_price_ohlcv"),
        observable_inputs=(
            "spot_ohlcv:BTCUSDT", "mark_price_ohlcv:BTCUSDT", "index_price_ohlcv:BTCUSDT",
        ),
        informational_streams=("mark_price_ohlcv", "index_price_ohlcv"),
    )
    events = (
        _bar(30, available="1970-01-01T00:00:01.000000Z", close_time=500),
        _bar(31, available="1970-01-01T00:00:02.000000Z", close_time=1500),
        _bar(32, available="1970-01-01T00:00:03.000000Z", close_time=2500, close="1000", stream="mark_price_ohlcv"),
        _bar(33, available="1970-01-01T00:00:04.000000Z", close_time=3500, close="2000", stream="index_price_ohlcv"),
    )
    _ledger, metrics = AccountingKernel(variant, _OneShotAdapter({"target_notional": "100"})).run(events)
    assert metrics["final_equity"] == "10000"
    assert metrics["gross_exposure"] == "100"
    assert metrics["positions"] == {"spot_ohlcv:BTCUSDT": "10"}


def test_adapter_and_accounting_see_only_exact_variant_scope() -> None:
    variant = _registry(fee="0", slippage="0").resolve("M101_METADATA_ONLY_FAMILY", 1, 1)[1]
    observed: list[tuple[str, str]] = []

    class Observe:
        def on_event(self, event, state):
            del state
            observed.append((event.stream, event.symbol))
            return []

    ledger, _metrics = AccountingKernel(variant, Observe()).run((
        _bar(40, available="1970-01-01T00:00:01.000000Z", close_time=500),
        _bar(41, available="1970-01-01T00:00:02.000000Z", close_time=1500, symbol="ETHUSDT"),
        _bar(42, available="1970-01-01T00:00:03.000000Z", close_time=2500, stream="mark_price_ohlcv"),
    ))
    assert observed == [("spot_ohlcv", "BTCUSDT")]
    assert len(ledger["event_rows"]) == 1

    cross_asset = replace(
        variant,
        required_streams=("spot_ohlcv", "mark_price_ohlcv"),
        required_symbols=("BTCUSDT", "ETHUSDT"),
        observable_inputs=("spot_ohlcv:BTCUSDT", "mark_price_ohlcv:ETHUSDT"),
        informational_streams=("mark_price_ohlcv",),
    )
    cross_observed: list[tuple[str, str]] = []

    class CrossObserve:
        def on_event(self, event, state):
            del state
            cross_observed.append((event.stream, event.symbol))
            return []

    AccountingKernel(cross_asset, CrossObserve()).run((
        _bar(43, available="1970-01-01T00:00:01.000000Z", close_time=500),
        _bar(44, available="1970-01-01T00:00:02.000000Z", close_time=1500, stream="mark_price_ohlcv", symbol="ETHUSDT"),
        _bar(45, available="1970-01-01T00:00:03.000000Z", close_time=2500, stream="mark_price_ohlcv"),
    ))
    assert cross_observed == [("spot_ohlcv", "BTCUSDT"), ("mark_price_ohlcv", "ETHUSDT")]


def test_variant_dataset_scope_and_numeric_boundaries(chain: dict[str, Any]) -> None:
    variant = _registry().resolve("M101_METADATA_ONLY_FAMILY", 1, 1)[1]
    variant.validate_dataset_scope(chain["descriptor"])
    missing_stream = replace(
        variant, required_streams=("spot_ohlcv", "perpetual_ohlcv"),
        observable_inputs=("spot_ohlcv:BTCUSDT", "perpetual_ohlcv:BTCUSDT"),
        tradable_instruments=("spot_ohlcv:BTCUSDT", "perpetual_ohlcv:BTCUSDT"),
        per_instrument_bounds={"spot_ohlcv:BTCUSDT": "1000", "perpetual_ohlcv:BTCUSDT": "1000"},
    )
    with pytest.raises(DevelopmentRuntimeError, match="VARIANT_REQUIRED_STREAM_MISSING"):
        missing_stream.validate_dataset_scope(chain["descriptor"])
    missing_symbol = replace(
        variant, required_symbols=("BTCUSDT", "ETHUSDT"),
        observable_inputs=("spot_ohlcv:BTCUSDT", "spot_ohlcv:ETHUSDT"),
    )
    with pytest.raises(DevelopmentRuntimeError, match="VARIANT_REQUIRED_SYMBOL_MISSING"):
        missing_symbol.validate_dataset_scope(chain["descriptor"])

    assert replace(variant, initial_research_nav="0.0001").initial_research_nav == "0.0001"
    assert replace(variant, fee_bps="10000").fee_bps == "10000"
    assert replace(variant, slippage_bps="9999.999").slippage_bps == "9999.999"
    for field, value, reason in (
        ("initial_research_nav", "0", "INITIAL_RESEARCH_NAV_INVALID"),
        ("initial_research_nav", "-1", "DECIMAL_INVALID"),
        ("fee_bps", "10000.0001", "FEE_BPS_INVALID"),
        ("fee_bps", "-0.1", "DECIMAL_INVALID"),
        ("slippage_bps", "10000", "SLIPPAGE_BPS_INVALID"),
        ("slippage_bps", "-0.1", "DECIMAL_INVALID"),
    ):
        with pytest.raises(DevelopmentRuntimeError, match=reason):
            replace(variant, **{field: value})


def _perpetual_variant() -> VariantDefinition:
    return VariantDefinition(
        variant_id="perp-1", required_streams=("perpetual_ohlcv", "funding_rates"),
        required_symbols=("BTCUSDT",),
        observable_inputs=("perpetual_ohlcv:BTCUSDT", "funding_rates:BTCUSDT"),
        tradable_instruments=("perpetual_ohlcv:BTCUSDT",),
        informational_streams=("funding_rates",), initial_research_nav="10000",
        max_gross_research_exposure="1000", max_net_research_exposure="1000",
        per_instrument_bounds={"perpetual_ohlcv:BTCUSDT": "1000"}, fee_bps="0", slippage_bps="0",
        funding_accounting_applicable=True, strategy_parameters={},
    )


def _perp_bar(number: int, *, available: str, close_time: int) -> MarketEvent:
    base = _bar(number, available=available, close_time=close_time)
    return MarketEvent(
        event_id=base.event_id, custody_record_hash=base.custody_record_hash,
        source_m100_record_hash=base.source_m100_record_hash,
        stream="perpetual_ohlcv", symbol=base.symbol, interval=base.interval,
        event_time_ms=base.event_time_ms, available_at=base.available_at,
        revision=base.revision, payload_hash=base.payload_hash, payload=base.payload,
    )


def _funding(number: int, *, rate: str, available: str, economic_time: int) -> MarketEvent:
    payload = {
        "funding_time_ms": economic_time, "funding_rate": rate, "mark_price": "10",
        "rate_type": "Regular", "normalizer_id": "x", "availability_policy_id": "x",
    }
    digest = hashlib.sha256(f"funding-{number}-{rate}".encode()).hexdigest()
    return MarketEvent(
        event_id=f"m102-event-{digest}", custody_record_hash=digest,
        source_m100_record_hash=hashlib.sha256(f"fund-source-{number}-{rate}".encode()).hexdigest(),
        stream="funding_rates", symbol="BTCUSDT", interval=None,
        event_time_ms=economic_time, available_at=available, revision=1,
        payload_hash=canonical_hash(payload), payload=payload,
    )


@pytest.mark.parametrize(
    "target,rate,expected_sign",
    [("100", "0.01", -1), ("-100", "0.01", 1), ("100", "-0.01", 1), ("-100", "-0.01", -1)],
)
def test_perpetual_long_short_and_funding_signs_use_economic_position(target: str, rate: str, expected_sign: int) -> None:
    class EnterThenFlat:
        def __init__(self): self.count = 0
        def on_event(self, event, state):
            del state
            if event.stream != "perpetual_ohlcv": return []
            self.count += 1
            if self.count == 1: return [TargetExposureIntent("BTCUSDT", "perpetual_ohlcv", target)]
            if self.count == 2: return [TargetExposureIntent("BTCUSDT", "perpetual_ohlcv", "0")]
            return []
    events = (
        _perp_bar(1, available="1970-01-01T00:00:01.000000Z", close_time=500),
        _perp_bar(2, available="1970-01-01T00:00:02.000000Z", close_time=1500),
        _perp_bar(3, available="1970-01-01T00:00:02.600000Z", close_time=2500),
        _funding(1, rate=rate, available="1970-01-01T00:00:03.000000Z", economic_time=2200),
    )
    ledger, metrics = AccountingKernel(_perpetual_variant(), EnterThenFlat()).run(events)
    assert metrics["positions"]["perpetual_ohlcv:BTCUSDT"] == "0"
    funding = Decimal(metrics["funding_cash_flow"])
    assert (funding > 0) - (funding < 0) == expected_sign
    row = ledger["funding_rows"][0]
    assert Decimal(row["position_at_economic_time"]) != 0
    assert row["recognition_available_at"] == events[-1].available_at


def test_delayed_fill_evidence_controls_position_effective_time_and_funding() -> None:
    class Enter:
        def __init__(self): self.done = False
        def on_event(self, event, state):
            del state
            if self.done or event.stream != "perpetual_ohlcv": return []
            self.done = True
            return [TargetExposureIntent("BTCUSDT", "perpetual_ohlcv", "100")]

    delayed_events = (
        _perp_bar(31, available="1970-01-01T00:00:01.000000Z", close_time=500),
        _perp_bar(32, available="1970-01-01T00:00:03.000000Z", close_time=1500),
        _funding(31, rate="0.01", available="1970-01-01T00:00:04.000000Z", economic_time=2000),
    )
    delayed_ledger, delayed_metrics = AccountingKernel(_perpetual_variant(), Enter()).run(delayed_events)
    fill = delayed_ledger["fill_rows"][0]
    assert fill["benchmark_close_time_ms"] == 1500
    assert fill["position_effective_at"] == 3000
    assert delayed_ledger["funding_rows"][0]["position_at_economic_time"] == "0"
    assert delayed_metrics["funding_cash_flow"] == "0"

    effective_events = (
        _perp_bar(33, available="1970-01-01T00:00:01.000000Z", close_time=500),
        _perp_bar(34, available="1970-01-01T00:00:02.000000Z", close_time=1500),
        _funding(32, rate="0.01", available="1970-01-01T00:00:03.000000Z", economic_time=2500),
    )
    effective_ledger, effective_metrics = AccountingKernel(_perpetual_variant(), Enter()).run(effective_events)
    assert effective_ledger["fill_rows"][0]["position_effective_at"] == 2000
    assert effective_ledger["funding_rows"][0]["position_at_economic_time"] == "10"
    assert Decimal(effective_metrics["funding_cash_flow"]) < 0

    funding_first_events = (
        _perp_bar(35, available="1970-01-01T00:00:01.000000Z", close_time=500),
        _funding(33, rate="0.01", available="1970-01-01T00:00:02.000000Z", economic_time=1800),
        _perp_bar(36, available="1970-01-01T00:00:03.000000Z", close_time=1500),
    )
    causal_ledger, causal_metrics = AccountingKernel(_perpetual_variant(), Enter()).run(funding_first_events)
    assert causal_ledger["funding_rows"][0]["position_at_economic_time"] == "0"
    assert causal_metrics["funding_cash_flow"] == "0"
    assert [row["event_id"] for row in causal_ledger["accounting_rows"]] == [
        event.event_id for event in funding_first_events
    ]


def test_trial_locks_serialize_same_trial_and_allow_different_trials(chain: dict[str, Any]) -> None:
    root = chain["temp"] / "locks-runtime"
    initialize_result_runtime(root, acknowledgement=ACK_INITIALIZE_RESULTS)
    ledger = m101._private_ledger(chain, "lock-ledger", "lock-budget", 2)
    trial_ids = []
    for number in (1, 2):
        reservation = ledger.reserve(
            budget_id="lock-budget", declared_trial_number=number,
            request_hash=str(number) * 64, initiated_by="OPERATOR",
            reserved_at=chain["as_of"], controlling_contract_id=m101.MISSION101_ID,
            controlling_contract_hash=m101.MISSION101_HASH,
        )
        ledger.append_event(
            trial_id=reservation.trial_id, status_token="ADMITTED",
            reason_token="M101_DEVELOPMENT_ADMISSION_GATES_PASSED",
            event_timestamp=chain["as_of"],
        )
        trial_ids.append(reservation.trial_id)
    entered = threading.Event()
    release = threading.Event()

    def hold() -> None:
        with trial_lock(root, trial_ids[0], ledger_path=ledger.database_path):
            entered.set(); release.wait(timeout=2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(hold)
        assert entered.wait(timeout=2)
        with trial_lock(root, trial_ids[1], ledger_path=ledger.database_path, timeout_seconds=0.1):
            pass
        with pytest.raises(DevelopmentRuntimeError, match="TRIAL_LOCK_TIMEOUT"):
            with trial_lock(root, trial_ids[0], ledger_path=ledger.database_path, timeout_seconds=0.05):
                pass
        release.set(); future.result(timeout=2)


def test_trial_lock_rejects_malformed_containment_and_dangling_symlink_without_creation(chain: dict[str, Any]) -> None:
    _permit, ledger, decision = _admit_budget_one(chain)
    tmp_path = chain["temp"]
    root = tmp_path / "lock-adversarial"
    initialize_result_runtime(root, acknowledgement=ACK_INITIALIZE_RESULTS)
    outside = tmp_path / "escaped.lock"
    malformed = (
        "trial-" + "1" * 31,
        "trial-" + "A" * 32,
        "trial-../escaped",
        "trial-" + "1" * 32 + "/escaped",
        "/tmp/trial-" + "1" * 32,
        "trial-" + "1" * 4096,
        "not-a-trial",
    )
    for trial_id in malformed:
        with pytest.raises(DevelopmentRuntimeError, match="TRIAL_ID_INVALID"):
            with trial_lock(root, trial_id, ledger_path=ledger.database_path):
                pass
    assert {item.name for item in (root / ".locks").iterdir()} == {".creation.lock"}
    assert not outside.exists()

    valid = decision["trial_id"]
    dangling_target = tmp_path / "dangling-target"
    (root / ".locks" / f"{valid}.lock").symlink_to(dangling_target)
    with pytest.raises(DevelopmentRuntimeError, match="LOCK_FILE_INVALID"):
        with trial_lock(root, valid, ledger_path=ledger.database_path):
            pass
    assert not dangling_target.exists()


def test_unknown_trials_and_lock_count_boundaries_create_no_excess_files(
    chain: dict[str, Any], monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = m101._private_ledger(chain, "lock-bound-ledger", "lock-bound-budget", 3)
    known: list[str] = []
    for number, character in enumerate(("a", "b", "c"), 1):
        reservation = ledger.reserve(
            budget_id="lock-bound-budget", declared_trial_number=number,
            request_hash=character * 64, initiated_by="OPERATOR",
            reserved_at=chain["as_of"], controlling_contract_id=m101.MISSION101_ID,
            controlling_contract_hash=m101.MISSION101_HASH,
        )
        ledger.append_event(
            trial_id=reservation.trial_id, status_token="ADMITTED",
            reason_token="M101_DEVELOPMENT_ADMISSION_GATES_PASSED",
            event_timestamp=chain["as_of"],
        )
        known.append(reservation.trial_id)

    root = chain["temp"] / "unknown-locks"
    initialize_result_runtime(root, acknowledgement=ACK_INITIALIZE_RESULTS)
    for number in range(100):
        unknown = f"trial-{number + 1000:032x}"
        with pytest.raises(DevelopmentRuntimeError, match="TRIAL_RESERVATION_MISMATCH"):
            with trial_lock(root, unknown, ledger_path=ledger.database_path):
                pass
    assert {item.name for item in (root / ".locks").iterdir()} == {".creation.lock"}

    monkeypatch.setattr(runtime_module, "MAX_LOCKS", 2)
    with trial_lock(root, known[0], ledger_path=ledger.database_path):
        pass
    with trial_lock(root, known[1], ledger_path=ledger.database_path):
        pass
    with pytest.raises(DevelopmentRuntimeError, match="LOCK_COUNT_LIMIT"):
        with trial_lock(root, known[2], ledger_path=ledger.database_path):
            pass
    assert len([item for item in (root / ".locks").iterdir() if item.name != ".creation.lock"]) == 2
    with pytest.raises(DevelopmentRuntimeError, match="TRIAL_RESERVATION_MISMATCH"):
        with trial_lock(root, "trial-" + "9" * 32, ledger_path=ledger.database_path):
            pass
    assert len([item for item in (root / ".locks").iterdir() if item.name != ".creation.lock"]) == 2
    # Existing locks remain usable at the exact boundary.
    with trial_lock(root, known[0], ledger_path=ledger.database_path):
        pass

    concurrent_root = chain["temp"] / "concurrent-lock-bound"
    initialize_result_runtime(concurrent_root, acknowledgement=ACK_INITIALIZE_RESULTS)
    monkeypatch.setattr(runtime_module, "MAX_LOCKS", 1)
    barrier = threading.Barrier(2)

    def create(trial_id: str) -> str:
        barrier.wait(timeout=2)
        try:
            with trial_lock(concurrent_root, trial_id, ledger_path=ledger.database_path):
                pass
            return "CREATED"
        except DevelopmentRuntimeError as error:
            return error.reason

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(create, known[:2]))
    assert sorted(outcomes) == ["CREATED", "LOCK_COUNT_LIMIT"]
    assert len([
        item for item in (concurrent_root / ".locks").iterdir()
        if item.name != ".creation.lock"
    ]) == 1


def test_backdated_completion_and_failure_create_no_terminal_evidence(chain: dict[str, Any]) -> None:
    permit, ledger, decision = _admit_budget_one(chain)
    verified = {
        "verdict": "VERIFIED", "trial_id": decision["trial_id"],
        "result_bundle_id": "result-bundle-" + "b" * 32,
        "canonical_result_hash": "c" * 64,
        "verifier": "DELTAGRID_M102_INDEPENDENT_RESULT_VERIFIER_V1",
        "verification_mode": "FULL_REPLAY_PREFINALIZATION",
    }
    with pytest.raises(DevelopmentRuntimeError, match="TRIAL_EVENT_TIME_REGRESSION"):
        finalize_verified_result(
            ledger.database_path, verified=verified,
            result_relative_path=f"{decision['trial_id']}/result.json",
            linked_at=permit["issued_at"],
        )
    with pytest.raises(DevelopmentRuntimeError, match="TRIAL_EVENT_TIME_REGRESSION"):
        terminalize_failed_claim(
            ledger.database_path, trial_id=decision["trial_id"],
            reason="TEST_FAILURE", event_at=permit["issued_at"],
        )
    conn = sqlite3.connect(ledger.database_path)
    assert conn.execute(
        "SELECT COUNT(*) FROM trial_result_links WHERE trial_id=?", (decision["trial_id"],)
    ).fetchone()[0] == 0
    assert ledger.event_statuses(decision["trial_id"]) == ("RESERVED", "ADMITTED")

    missing = m101._private_ledger(chain, "missing-link-ledger", "missing-link-budget", 1)
    reservation = missing.reserve(
        budget_id="missing-link-budget", declared_trial_number=1,
        request_hash="d" * 64, initiated_by="OPERATOR",
        reserved_at=chain["as_of"], controlling_contract_id=m101.MISSION101_ID,
        controlling_contract_hash=m101.MISSION101_HASH,
    )
    missing.append_event(
        trial_id=reservation.trial_id, status_token="ADMITTED",
        reason_token="M101_DEVELOPMENT_ADMISSION_GATES_PASSED",
        event_timestamp=chain["as_of"],
    )
    missing.append_event(
        trial_id=reservation.trial_id, status_token="COMPLETED",
        reason_token="M102_DEVELOPMENT_RESULT_VERIFIED",
        event_timestamp=chain["expires_at"],
    )
    with pytest.raises(DevelopmentRuntimeError, match="COMPLETED_RESULT_LINK_REQUIRED"):
        read_trial_binding(missing.database_path, reservation.trial_id, allow_completed=True)


def test_execution_failure_uses_fresh_injected_audit_time(chain: dict[str, Any]) -> None:
    _permit, ledger, decision = _admit_budget_one(chain)
    variant = _registry().resolve("M101_METADATA_ONLY_FAMILY", 1, 1)[1]

    class Fail:
        def on_event(self, event, state):
            del event, state
            raise RuntimeError("intentional")

    registry = ExperimentRegistry((FamilyDefinition(
        family_id="M101_METADATA_ONLY_FAMILY", variants=(variant,),
        adapter_factory=lambda parameters: Fail(),
    ),))
    root = chain["temp"] / "failure-results"
    initialize_result_runtime(root, acknowledgement=ACK_INITIALIZE_RESULTS)
    with pytest.raises(DevelopmentRuntimeError, match="ADAPTER_FAILURE"):
        execute_development_trial(
            trial_id=decision["trial_id"], ledger_path=ledger.database_path,
            authority_root=chain["authority_root"], descriptor=chain["descriptor"],
            release_directory=chain["release_directory"], custody_runtime_root=chain["custody_root"],
            result_runtime=root, acknowledgement=ACK_EXECUTE, registry=registry,
            time_provider=lambda: chain["as_of"],
            audit_time_provider=lambda: chain["expires_at"],
            repository_observer=m101._repository_observer(),
        )
    latest = ledger.latest_event(decision["trial_id"])
    assert latest.status_token == "FAILED"
    assert latest.event_timestamp == chain["expires_at"]


def test_public_verification_requires_exact_finalized_m94_link(chain: dict[str, Any]) -> None:
    _permit, ledger, decision = _admit_budget_one(chain)
    registry = _registry()
    snapshot = capture_authority_snapshot(
        trial_id=decision["trial_id"], ledger_path=ledger.database_path,
        authority_root=chain["authority_root"], descriptor=chain["descriptor"],
        time_provider=lambda: chain["as_of"],
        repository_observer=m101._repository_observer(),
    )
    family, variant = registry.resolve("M101_METADATA_ONLY_FAMILY", 1, 1)
    specification = build_execution_specification(
        snapshot, chain["descriptor"], registry, family, variant,
    )
    root = chain["temp"] / "prefinal-results"
    initialize_result_runtime(root, acknowledgement=ACK_INITIALIZE_RESULTS)
    directory = trial_directory(root, decision["trial_id"], create=True)
    claim_execution_spec(directory, specification)
    events = load_causal_events(
        chain["descriptor"], release_directory=chain["release_directory"],
        custody_runtime_root=chain["custody_root"],
        observable_inputs=variant.observable_inputs,
    )
    event_ledger, metrics = AccountingKernel(
        variant, family.adapter_factory(variant.strategy_parameters),
    ).run(events)
    bound_ledger, result = build_result_artifacts(specification, event_ledger, metrics)
    publish_artifact(directory, "event-ledger.json", bound_ledger)
    publish_artifact(directory, "result.json", result)

    internal = verify_development_result(
        result_runtime=root, trial_id=decision["trial_id"], ledger_path=ledger.database_path,
        authority_root=chain["authority_root"], descriptor=chain["descriptor"],
        release_directory=chain["release_directory"], custody_runtime_root=chain["custody_root"],
        registry=registry, require_finalized=False,
        repository_observer=m101._repository_observer(),
    )
    assert internal["verification_mode"] == "FULL_REPLAY_PREFINALIZATION"
    with pytest.raises(DevelopmentRuntimeError, match="FINALIZED_RESULT_REQUIRED"):
        verify_development_result(
            result_runtime=root, trial_id=decision["trial_id"], ledger_path=ledger.database_path,
            authority_root=chain["authority_root"], descriptor=chain["descriptor"],
            release_directory=chain["release_directory"], custody_runtime_root=chain["custody_root"],
            registry=registry, repository_observer=m101._repository_observer(),
        )

    completed_at = chain["expires_at"]
    bad_link_core = {
        "trial_id": decision["trial_id"],
        "result_bundle_id": "result-bundle-" + "0" * 32,
        "result_bundle_hash": "0" * 64,
        "result_bundle_path": f"{decision['trial_id']}/wrong-result.json",
        "linked_at": chain["as_of"],
    }
    conn = sqlite3.connect(ledger.database_path)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        "INSERT INTO trial_result_links(trial_id,result_bundle_id,result_bundle_hash,result_bundle_path,linked_at,canonical_result_link_hash) VALUES (?,?,?,?,?,?)",
        (*bad_link_core.values(), canonical_hash(bad_link_core)),
    )
    conn.commit(); conn.close()
    ledger.append_event(
        trial_id=decision["trial_id"], status_token="COMPLETED",
        reason_token="M102_DEVELOPMENT_RESULT_VERIFIED", event_timestamp=completed_at,
    )
    with pytest.raises(DevelopmentRuntimeError, match="FINALIZED_RESULT_LINK_MISMATCH"):
        verify_development_result(
            result_runtime=root, trial_id=decision["trial_id"], ledger_path=ledger.database_path,
            authority_root=chain["authority_root"], descriptor=chain["descriptor"],
            release_directory=chain["release_directory"], custody_runtime_root=chain["custody_root"],
            registry=registry, repository_observer=m101._repository_observer(),
        )


def test_full_execution_replay_finalization_and_revocation_readability(chain: dict[str, Any]) -> None:
    permit, ledger, decision = _admit_budget_one(chain)
    result_root = chain["temp"] / "m102-results"
    initialize_result_runtime(result_root, acknowledgement=ACK_INITIALIZE_RESULTS)
    result = execute_development_trial(
        trial_id=decision["trial_id"], ledger_path=ledger.database_path,
        authority_root=chain["authority_root"], descriptor=chain["descriptor"],
        release_directory=chain["release_directory"], custody_runtime_root=chain["custody_root"],
        result_runtime=result_root, acknowledgement=ACK_EXECUTE, registry=_registry(),
        time_provider=lambda: chain["as_of"], audit_time_provider=lambda: chain["expires_at"],
        repository_observer=m101._repository_observer(),
    )
    assert result["verdict"] == "VERIFIED"
    assert result["verification_mode"] == "FULL_REPLAY_FINALIZED"
    persisted_spec = json.loads((result_root / decision["trial_id"] / "execution-spec.json").read_text())
    binding = persisted_spec["authority_binding"]
    assert binding["authority_decision_time"] == chain["as_of"]
    assert binding["authority_decision_time"] != binding["permit_issued_at"]
    authority_core = dict(binding); authority_hash = authority_core.pop("authority_snapshot_hash")
    assert canonical_hash(authority_core) == authority_hash
    assert canonical_hash(persisted_spec["registry_snapshot_core"]) == persisted_spec["registry_snapshot_hash"]
    assert ledger.event_statuses(decision["trial_id"]) == ("RESERVED", "ADMITTED", "COMPLETED")
    conn = sqlite3.connect(ledger.database_path)
    reason = conn.execute("SELECT reason_token FROM trial_events WHERE trial_id=? ORDER BY sequence_number DESC LIMIT 1", (decision["trial_id"],)).fetchone()[0]
    assert reason == "M102_DEVELOPMENT_RESULT_VERIFIED"
    completed_at = conn.execute("SELECT event_timestamp FROM trial_events WHERE trial_id=? ORDER BY sequence_number DESC LIMIT 1", (decision["trial_id"],)).fetchone()[0]
    assert completed_at == chain["expires_at"]
    assert "SYNTHETIC_CONTROL_COMPLETED" not in {row[0] for row in conn.execute("SELECT reason_token FROM trial_events")}
    verified = verify_development_result(
        result_runtime=result_root, trial_id=decision["trial_id"], ledger_path=ledger.database_path,
        authority_root=chain["authority_root"], descriptor=chain["descriptor"],
        release_directory=chain["release_directory"], custody_runtime_root=chain["custody_root"],
        registry=_registry(), repository_observer=m101._repository_observer(),
    )
    assert verified["canonical_result_hash"] == result["canonical_result_hash"]
    with pytest.raises(DevelopmentRuntimeError, match="HISTORICAL_EXECUTION_CODE_CONTEXT_REQUIRED"):
        verify_development_result(
            result_runtime=result_root, trial_id=decision["trial_id"], ledger_path=ledger.database_path,
            authority_root=chain["authority_root"], descriptor=chain["descriptor"],
            release_directory=chain["release_directory"], custody_runtime_root=chain["custody_root"],
            registry=_registry(), repository_observer=m101._repository_observer(head="a" * 40),
        )
    with pytest.raises(DevelopmentRuntimeError, match="REGISTRY_SNAPSHOT_RECONSTRUCTION_MISMATCH"):
        verify_development_result(
            result_runtime=result_root, trial_id=decision["trial_id"], ledger_path=ledger.database_path,
            authority_root=chain["authority_root"], descriptor=chain["descriptor"],
            release_directory=chain["release_directory"], custody_runtime_root=chain["custody_root"],
            registry=_registry(fee="9"), repository_observer=m101._repository_observer(),
        )
    m101.revoke_development_permit(
        chain["authority_root"], permit["permit_id"],
        acknowledgement=m101.ACK_REVOKE_PERMIT, time_provider=lambda: chain["expires_at"],
    )
    replay = execute_development_trial(
        trial_id=decision["trial_id"], ledger_path=ledger.database_path,
        authority_root=chain["authority_root"], descriptor=chain["descriptor"],
        release_directory=chain["release_directory"], custody_runtime_root=chain["custody_root"],
        result_runtime=result_root, acknowledgement=ACK_EXECUTE, registry=_registry(),
        time_provider=lambda: chain["as_of"], repository_observer=m101._repository_observer(),
    )
    assert replay["canonical_result_hash"] == result["canonical_result_hash"]
    assert ledger.event_statuses(decision["trial_id"]) == ("RESERVED", "ADMITTED", "COMPLETED")


def test_result_runtime_rejects_relative_repo_and_symlink_roots(tmp_path: Path) -> None:
    with pytest.raises(DevelopmentRuntimeError, match="RESULT_ROOT_NOT_ABSOLUTE"):
        initialize_result_runtime("relative", acknowledgement=ACK_INITIALIZE_RESULTS)
    with pytest.raises(DevelopmentRuntimeError, match="RESULT_ROOT_INSIDE_REPOSITORY"):
        initialize_result_runtime(ROOT / "bad-results", acknowledgement=ACK_INITIALIZE_RESULTS)
    target = tmp_path / "target"; target.mkdir(mode=0o700)
    link = tmp_path / "link"; link.symlink_to(target, target_is_directory=True)
    with pytest.raises(DevelopmentRuntimeError, match="RESULT_ROOT_SYMLINK"):
        initialize_result_runtime(link, acknowledgement=ACK_INITIALIZE_RESULTS)
