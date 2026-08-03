"""Fixed dispatcher and integer-only long-or-flat synthetic accounting kernel."""

from __future__ import annotations

import hashlib
from types import MappingProxyType
from typing import Any, Callable, Mapping

from offchain.research.admission import canonical_hash

from .models import EngineError, ExecutionOutcome, ExecutionPermit, SyntheticFixture


ENGINE_ID = "deltagrid-canonical-result-engine"
ENGINE_VERSION = "1.0"
KERNEL_ID = "integer-long-flat-synthetic-accounting"
KERNEL_VERSION = "1.0"


def _ceil_div(numerator: int, denominator: int) -> int:
    return (numerator + denominator - 1) // denominator


def _buy_and_hold_targets(fixture: SyntheticFixture, _: Mapping[str, Any]) -> tuple[int, ...]:
    quantity = fixture.trade_quantity_units
    return tuple(quantity if index < len(fixture.events) - 1 else 0 for index in range(len(fixture.events)))


def _no_trade_targets(fixture: SyntheticFixture, _: Mapping[str, Any]) -> tuple[int, ...]:
    return (0,) * len(fixture.events)


def _seeded_targets(fixture: SyntheticFixture, parameters: Mapping[str, Any]) -> tuple[int, ...]:
    seed = parameters["seed"]
    quantity = fixture.trade_quantity_units
    targets = []
    for index in range(len(fixture.events) - 1):
        digest = hashlib.sha256(f"{seed}:{index}".encode("ascii")).digest()
        targets.append(quantity if int.from_bytes(digest[:8], "big") % 2 else 0)
    targets.append(0)
    return tuple(targets)


def _state_machine_targets(
    fixture: SyntheticFixture,
    parameters: Mapping[str, Any],
) -> tuple[int, ...]:
    scenario = parameters["scenario_id"]
    count = len(fixture.events)
    quantity = fixture.trade_quantity_units
    if scenario == "ROUND_TRIP":
        return _buy_and_hold_targets(fixture, parameters)
    if scenario == "STOP_AND_COOLDOWN":
        if count < 5:
            raise EngineError("CONTROL_EXECUTION_FAILED")
        return tuple(
            quantity if index == 0 or 3 <= index < count - 1 else 0
            for index in range(count)
        )
    if scenario == "PARTIAL_FILL_SEQUENCE":
        if count < 4:
            raise EngineError("CONTROL_EXECUTION_FAILED")
        split = count // 2
        return tuple(quantity if index < split else 0 for index in range(count))
    raise EngineError("CONTROL_EXECUTION_FAILED")


TargetBuilder = Callable[[SyntheticFixture, Mapping[str, Any]], tuple[int, ...]]
_DISPATCHER: Mapping[str, TargetBuilder] = MappingProxyType(
    {
        "NO_TRADE_CONTROL": _no_trade_targets,
        "BUY_AND_HOLD_CONTROL": _buy_and_hold_targets,
        "SEEDED_RANDOM_CONTROL": _seeded_targets,
        "SIMULATOR_STATE_MACHINE_CONTROL": _state_machine_targets,
    }
)


def _run_kernel(
    fixture: SyntheticFixture,
    targets: tuple[int, ...],
) -> ExecutionOutcome:
    if len(targets) != len(fixture.events) or any(
        type(target) is not int
        or target not in (0, fixture.trade_quantity_units)
        for target in targets
    ):
        raise EngineError("CONTROL_EXECUTION_FAILED")
    position = 0
    gross_cash = fixture.initial_cash_units
    net_cash = fixture.initial_cash_units
    cumulative_fees = 0
    cumulative_slippage = 0
    turnover = 0
    peak_equity = fixture.initial_cash_units
    maximum_drawdown = 0
    maximum_drawdown_bps = 0
    exposure_sum = 0
    exposure_events = 0
    attempt_count = 0
    fill_count = 0
    trade_count = 0
    entry_count = 0
    exit_count = 0
    partial_entry_count = 0
    partial_exit_count = 0
    rows: list[dict[str, Any]] = []
    for index, (event, target) in enumerate(zip(fixture.events, targets, strict=True)):
        before = position
        state_before = "LONG" if before else "FLAT"
        attempted = target - position
        executed = 0
        execution_price = 0
        fee = 0
        slippage = 0
        event_turnover = 0
        if attempted:
            attempt_count += 1
            magnitude = abs(attempted) * event.available_fill_bps // 10_000
            executed = magnitude if attempted > 0 else -magnitude
        if executed:
            fill_count += 1
            trade_count += 1
            if executed > 0:
                execution_price = _ceil_div(
                    event.mid_price_units * (10_000 + fixture.slippage_bps),
                    10_000,
                )
                mid_notional = event.mid_price_units * executed // 10_000
                actual_notional = execution_price * executed // 10_000
                fee = _ceil_div(actual_notional * fixture.fee_bps, 10_000)
                gross_cash -= mid_notional
                net_cash -= actual_notional + fee
                slippage = max(0, actual_notional - mid_notional)
                entry_count += 1
                if executed != attempted:
                    partial_entry_count += 1
            else:
                sold = -executed
                execution_price = (
                    event.mid_price_units * (10_000 - fixture.slippage_bps)
                    // 10_000
                )
                mid_notional = event.mid_price_units * sold // 10_000
                actual_notional = execution_price * sold // 10_000
                fee = _ceil_div(actual_notional * fixture.fee_bps, 10_000)
                gross_cash += mid_notional
                net_cash += actual_notional - fee
                slippage = max(0, mid_notional - actual_notional)
                exit_count += 1
                if executed != attempted:
                    partial_exit_count += 1
            event_turnover = actual_notional
            cumulative_fees += fee
            cumulative_slippage += slippage
            turnover += event_turnover
            position += executed
            if net_cash < 0 or position < 0 or position > fixture.trade_quantity_units:
                raise EngineError("CONTROL_EXECUTION_FAILED")
        gross_equity = gross_cash + event.mid_price_units * position // 10_000
        net_equity = net_cash + event.mid_price_units * position // 10_000
        peak_equity = max(peak_equity, net_equity)
        drawdown = peak_equity - net_equity
        maximum_drawdown = max(maximum_drawdown, drawdown)
        drawdown_bps = 0 if peak_equity <= 0 else drawdown * 10_000 // peak_equity
        maximum_drawdown_bps = max(maximum_drawdown_bps, drawdown_bps)
        exposure_sum += position
        if position:
            exposure_events += 1
        state_after = "LONG" if position else "FLAT"
        rows.append(
            {
                "event_index": index,
                "event_id": event.event_id,
                "timestamp": event.timestamp,
                "mid_price_units": event.mid_price_units,
                "available_fill_bps": event.available_fill_bps,
                "target_position_units": target,
                "position_before_units": before,
                "attempted_delta_units": attempted,
                "executed_delta_units": executed,
                "execution_price_units": execution_price,
                "fee_cost_units": fee,
                "slippage_cost_units": slippage,
                "event_turnover_units": event_turnover,
                "position_after_units": position,
                "gross_cash_units": gross_cash,
                "net_cash_units": net_cash,
                "gross_equity_units": gross_equity,
                "net_equity_units": net_equity,
                "cumulative_fee_cost_units": cumulative_fees,
                "cumulative_slippage_cost_units": cumulative_slippage,
                "state_before": state_before,
                "state_after": state_after,
            }
        )
    if position != 0:
        raise EngineError("CONTROL_EXECUTION_FAILED")
    gross_result = gross_cash - fixture.initial_cash_units
    net_result = net_cash - fixture.initial_cash_units
    metrics = {
        "initial_cash_units": fixture.initial_cash_units,
        "final_gross_cash_units": gross_cash,
        "final_net_cash_units": net_cash,
        "gross_result_units": gross_result,
        "net_result_units": net_result,
        "fee_cost_units": cumulative_fees,
        "slippage_cost_units": cumulative_slippage,
        "funding_cost_units": 0,
        "borrowing_cost_units": 0,
        "impact_cost_units": 0,
        "latency_cost_units": 0,
        "maximum_drawdown_units": maximum_drawdown,
        "maximum_drawdown_bps": maximum_drawdown_bps,
        "turnover_units": turnover,
        "exposure_position_units_sum": exposure_sum,
        "exposure_event_count": exposure_events,
        "exposure_bps": exposure_sum * 10_000
        // (fixture.trade_quantity_units * len(fixture.events)),
        "concentration_bps": max(
            row["position_after_units"] for row in rows
        )
        * 10_000
        // fixture.trade_quantity_units,
        "attempt_count": attempt_count,
        "fill_count": fill_count,
        "trade_count": trade_count,
        "entry_count": entry_count,
        "exit_count": exit_count,
        "partial_entry_count": partial_entry_count,
        "partial_exit_count": partial_exit_count,
        "final_position_units": position,
        "final_state": "FLAT",
    }
    return ExecutionOutcome(
        rows=tuple(rows),
        metrics=metrics,
        final_state="FLAT",
        targets_hash=canonical_hash(list(targets)),
    )


def execute_control(
    *,
    fixture: SyntheticFixture,
    control_identifier: str,
    control_parameters: Mapping[str, Any],
    permit: ExecutionPermit,
) -> ExecutionOutcome:
    """Execute only one fixed control under a verified narrow permit."""

    permit_core = permit.as_dict()
    supplied_permit_hash = permit_core.pop("canonical_permit_hash")
    if (
        permit.scope != "MISSION_95_SYNTHETIC_CONTROL_ONLY"
        or canonical_hash(permit_core) != supplied_permit_hash
    ):
        raise EngineError("INTERNAL_INTEGRITY_FAILURE")
    builder = _DISPATCHER.get(control_identifier)
    if builder is None:
        raise EngineError("CONTROL_EXECUTION_FAILED")
    targets = builder(fixture, control_parameters)
    outcome = _run_kernel(fixture, targets)
    if (
        control_identifier == "SIMULATOR_STATE_MACHINE_CONTROL"
        and control_parameters.get("scenario_id") == "PARTIAL_FILL_SEQUENCE"
        and (
            outcome.metrics["partial_entry_count"] < 1
            or outcome.metrics["partial_exit_count"] < 1
        )
    ):
        raise EngineError("CONTROL_EXECUTION_FAILED")
    if (
        control_identifier == "SIMULATOR_STATE_MACHINE_CONTROL"
        and control_parameters.get("scenario_id") == "STOP_AND_COOLDOWN"
        and (
            outcome.metrics["entry_count"] < 2
            or outcome.metrics["exit_count"] < 2
            or outcome.rows[2]["position_after_units"] != 0
        )
    ):
        raise EngineError("CONTROL_EXECUTION_FAILED")
    return outcome


def execute_benchmark(fixture: SyntheticFixture) -> ExecutionOutcome:
    """Calculate the fixed buy-and-hold non-trial baseline with the same kernel."""

    return _run_kernel(fixture, _buy_and_hold_targets(fixture, {}))
