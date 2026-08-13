from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sqlite3

import pytest

from offchain.research.development_runtime.kernel import RevealedEvent
from offchain.research.development_runtime.registry import production_registry
from offchain.research.rab1.protocol import (
    CONTRACT_HASH, development_gates, evidence_calendar, load_contract,
    protected_partition_specs, protected_rules,
)
from offchain.research.rab1.readiness import select_t0_metadata
from offchain.research.rab1.statistics import (
    NULL_ALGORITHM_ID, PROTECTED_EVALUATOR_ID, STATISTICAL_ADAPTER_ID,
)
from offchain.research.rab1.strategy import FAMILY_ID
from offchain.research.statistical_governance.core import GovernanceError
from offchain.research.statistical_governance.protocol import validate_partition_spec
from offchain.research.statistical_governance.registry import (
    production_protected_evaluator_registry, production_statistical_adapter_registry,
)
from offchain.research.statistical_governance.statistics import build_randomization_plan, holm_step_down


def test_rab1_contract_exactly_authorizes_static_none_authority_registries() -> None:
    contract = load_contract()
    assert contract["contract_hash_sha256"] == CONTRACT_HASH
    assert contract["maximum_verdict"]["authority_effect"] == "NONE"
    assert contract["terminal_policy"] == {
        "failure_verdict": "PROGRAM_REJECTED",
        "success_verdict": "QUALIFIED_FOR_M104_OBSERVATION",
        "no_retuning": True,
        "no_alternate_candidate": True,
        "no_shifted_window": True,
        "no_rescue_attempt": True,
        "mission104_started": False,
        "mission104_authorized": False,
    }
    registry = production_registry()
    assert registry.family_count == 1
    family, _ = registry.resolve(FAMILY_ID, 1, 4)
    assert [registry.resolve(FAMILY_ID, index, 4)[1].variant_id for index in range(1, 5)] == [
        "RAB1_ETH_BTC_168H", "RAB1_ETH_BTC_336H",
        "RAB1_SOL_BTC_168H", "RAB1_SOL_BTC_336H",
    ]
    assert family.definition_hash == contract["production_registry_authorization"]["family_hash"]


def test_rab1_variant_cost_funding_exposure_and_causal_pair_synchronization() -> None:
    family, variant = production_registry().resolve(FAMILY_ID, 1, 4)
    assert variant.fee_bps == variant.slippage_bps == "5"
    assert variant.funding_accounting_applicable is True
    assert variant.initial_research_nav == "10000"
    assert variant.max_gross_research_exposure == "2000"
    assert set(variant.informational_streams) == {"funding_rates"}
    adapter = family.adapter_factory(variant.strategy_parameters)
    targets = adapter._targets(1, Decimal("1.5"))
    assert sum(abs(Decimal(item.target_notional)) for item in targets) == Decimal("2000")
    assert sum(Decimal(item.target_notional) for item in targets) == Decimal("-400")

    state = {"pending_instruments": ()}
    first = RevealedEvent(
        "btc", "perpetual_ohlcv", "BTCUSDT", "1h", 1, "2026-08-13T00:00:01Z", 1,
        {"close_time_ms": 3_600_000, "close": "100"},
    )
    second = RevealedEvent(
        "eth", "perpetual_ohlcv", "ETHUSDT", "1h", 1, "2026-08-13T00:00:02Z", 1,
        {"close_time_ms": 3_600_000, "close": "10"},
    )
    assert adapter.on_event(first, state) == []
    assert adapter.on_event(second, state) == []
    assert adapter.last_processed_hour == 3_600_000


def test_rab1_sign_flip_null_is_exact_9999_deterministic_and_trace_not_output() -> None:
    adapter_registry = production_statistical_adapter_registry()
    contract = load_contract()["production_registry_authorization"]
    adapter = adapter_registry.resolve(STATISTICAL_ADAPTER_ID, contract["statistical_adapter_hash"])
    plan = build_randomization_plan(123, 9_999)
    metrics = {
        "initial_research_nav": "10000", "final_equity": "10060", "gross_pnl": "100",
        "max_drawdown": "10", "net_pnl": "60", "turnover": "500",
    }
    value = {
        "input_schema": "DELTAGRID_M103_STATISTICAL_INPUT_V1",
        "verified_result": {"metrics": metrics},
        "primary_statistic": "net_pnl",
        "direction": "GREATER",
        "null_policy": {"kind": "EMPIRICAL_MONTE_CARLO", "algorithm": NULL_ALGORITHM_ID},
        "randomization_plan": plan,
        "_verified_trace": {
            "trace_schema": "RAB1_VERIFIED_EVENT_LEDGER_TRACE_V1",
            "event_ledger_hash": "a" * 64,
            "daily_net_pnl_blocks": tuple("1" for _ in range(60)),
            "daily_block_count": 60,
        },
    }
    first = adapter.function(value)
    second = adapter.function(value)
    assert first == second
    assert len(first["null_evidence"]["results"]) == 9_999
    assert first["null_evidence"]["observed_statistic"] == "60"
    assert set(first["measurements"]) == {
        "daily_block_count", "gross_pnl", "max_drawdown", "net_pnl", "turnover",
    }
    assert "_verified_trace" not in repr(first)
    with pytest.raises(GovernanceError, match="RAB1_STATISTICAL_INPUT_INVALID"):
        adapter.function({key: item for key, item in value.items() if key != "_verified_trace"})


def test_rab1_program_wide_holm_and_protected_decimal_evaluator() -> None:
    holm = holm_step_down({"h1": "0.001", "h2": "0.02", "h3": "0.03", "h4": "0.9"}, alpha="0.05")
    assert holm["method"] == "HOLM_STEP_DOWN_FWER_PROGRAM_WIDE"
    assert holm["m"] == 4
    contract = load_contract()["production_registry_authorization"]
    evaluator = production_protected_evaluator_registry().resolve(
        PROTECTED_EVALUATOR_ID, contract["protected_evaluator_hash"],
    )
    metrics = {
        "initial_research_nav": "10000", "final_equity": "10001", "gross_pnl": "2",
        "net_pnl": "1", "turnover": "100", "max_drawdown": "5", "fees": "0.5",
    }
    output = evaluator.function({
        "input_schema": "DELTAGRID_M103_POST_EXECUTION_MEASUREMENT_INPUT_V1",
        "candidate_hash": "a" * 64,
        "stage": "REPLICATION",
        "authoritative_metrics": metrics,
        "authoritative_ledger_hash": "b" * 64,
        "execution_evidence_hash": "c" * 64,
    })
    assert output["measurements"] == {
        "final_equity": "10001", "gross_pnl": "2", "max_drawdown": "5",
        "net_pnl": "1", "turnover": "100",
    }
    rules = protected_rules()
    assert set(rules) == {"REPLICATION", "VALIDATION", "HOLDOUT"}
    assert all(rule["measurement_gates"] == rules["REPLICATION"]["measurement_gates"] for rule in rules.values())
    assert {gate["measurement_id"] for gate in development_gates()} == {
        "daily_block_count", "gross_pnl", "max_drawdown", "net_pnl", "turnover",
    }


def test_rab1_calendar_is_180_days_and_partitions_are_prospective_shapes() -> None:
    calendar = evidence_calendar("2026-08-13T00:00:00.000Z")
    assert calendar["warmup"] == ["2026-08-13T00:00:00.000Z", "2026-08-27T00:00:00.000Z"]
    assert calendar["holdout"][1] == "2027-02-09T00:00:00.000Z"
    assert calendar["earliest_terminal_verdict_at"] == "2027-02-10T00:00:00.000Z"
    assert calendar["mission104_authorized"] is False
    specs = protected_partition_specs("2026-08-13T00:00:00.000Z")
    assert [item["stage"] for item in specs] == ["REPLICATION", "VALIDATION", "HOLDOUT"]
    assert all(validate_partition_spec(item)["stage"] == item["stage"] for item in specs)
    for previous, current in zip(specs, specs[1:]):
        assert current["context_start"] >= previous["scoring_end"] + previous["forward_horizon_ms"] + previous["embargo_ms"]


def test_t0_selection_uses_only_healthy_complete_metadata(tmp_path: Path) -> None:
    path = tmp_path / "acquisition.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        PRAGMA application_id=100100;
        CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE capture_batches(batch_id TEXT PRIMARY KEY,status TEXT);
        CREATE TABLE receipts(receipt_hash TEXT PRIMARY KEY,clock_status TEXT);
        CREATE TABLE observations(event_time_ms INTEGER,symbol TEXT,stream TEXT,batch_id TEXT,receipt_hash TEXT);
        INSERT INTO metadata VALUES('created_at','2026-08-13T00:00:00.000Z');
        INSERT INTO capture_batches VALUES('batch','COMPLETE');
        INSERT INTO receipts VALUES('receipt','HEALTHY');
        """
    )
    hour = int(datetime(2026, 8, 13, 8, tzinfo=timezone.utc).timestamp() * 1000)
    for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        connection.execute("INSERT INTO observations VALUES(?,?,?,?,?)", (hour, symbol, "perpetual_ohlcv", "batch", "receipt"))
        connection.execute("INSERT INTO observations VALUES(?,?,?,?,?)", (hour, symbol, "funding_rates", "batch", "receipt"))
    connection.commit()
    connection.close()
    assert select_t0_metadata(path) == "2026-08-13T08:00:00.000Z"
