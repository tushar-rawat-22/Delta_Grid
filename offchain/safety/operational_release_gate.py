"""Deterministic release gate over DeltaGrid's paper-only operating controls.

This module does not run a strategy, open an exchange connection, or authorize
capital. It reduces four existing paper-only control outputs to one explicit
operator verdict so a release cannot be called ready while a paper, risk,
capital-readiness, or drawdown-kill-switch control is missing or unsafe.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

PAPER_READY = "PAPER_SANDBOX_READY_SHADOW_ONLY"
RISK_READY = "INSTITUTIONAL_RISK_CONTROL_READY_SHADOW_ONLY"
CAPITAL_READY = "CAPITAL_READINESS_REVIEW_PAPER_ONLY_READY"
CAPITAL_DECISION_EXTENDED_PAPER = (
    "CAPITAL_READINESS_APPROVED_FOR_EXTENDED_PAPER_OBSERVATION_ONLY"
)
KILL_SWITCH_VERDICT_ARMED = "PAPER_DRAWDOWN_KILL_SWITCH_ARMED_SHADOW_ONLY"
KILL_SWITCH_DECISION_ARMED = (
    "PAPER_DRAWDOWN_KILL_SWITCH_ARMED_CONTINUE_OBSERVATION"
)
KILL_SWITCH_STATE_ARMED = "KILL_SWITCH_STATE_ARMED_NOT_TRIGGERED"

LIVE_TRADING_DISABLED = "DISABLED"
CAPITAL_DEPLOYMENT_BLOCKED = "BLOCKED"

READY = "OPERATIONAL_RELEASE_READY_FOR_EXTENDED_PAPER_ONLY"
BLOCKED = "OPERATIONAL_RELEASE_BLOCKED"


@dataclass(frozen=True)
class OperationalReleaseReport:
    """One fail-closed operator verdict over the existing paper control chain."""

    status: str
    ready_for_extended_paper: bool
    paper_ready: bool
    risk_ready: bool
    capital_ready: bool
    kill_switch_armed: bool
    safety_invariants_hold: bool
    blockers: tuple[str, ...]
    live_trading_allowed: bool = False
    exchange_access_allowed: bool = False
    capital_deployment_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safety_invariants(
    value: Mapping[str, Any] | None,
    *,
    name: str,
    blockers: list[str],
) -> bool:
    if not isinstance(value, Mapping):
        blockers.append(f"{name}:MISSING_OR_INVALID")
        return False

    safe = (
        value.get("live_trading") == LIVE_TRADING_DISABLED
        and value.get("live_order_sent") == 0
        and value.get("capital_deployment") == CAPITAL_DEPLOYMENT_BLOCKED
        and value.get("safety_breach_count", 0) == 0
    )
    if not safe:
        blockers.append(f"{name}:SAFETY_INVARIANT_FAILED")
    return safe


def evaluate_operational_release(
    *,
    paper: Mapping[str, Any] | None,
    risk: Mapping[str, Any] | None,
    capital: Mapping[str, Any] | None,
    kill_switch: Mapping[str, Any] | None,
) -> OperationalReleaseReport:
    """Return one paper-only release verdict from four existing control outputs.

    Missing or malformed evidence is a blocker. No field in these inputs can
    authorize live trading, exchange access, credentials, orders, or capital.
    """

    blockers: list[str] = []
    safety_checks = (
        _safety_invariants(paper, name="PAPER", blockers=blockers),
        _safety_invariants(risk, name="RISK", blockers=blockers),
        _safety_invariants(capital, name="CAPITAL", blockers=blockers),
        _safety_invariants(kill_switch, name="KILL_SWITCH", blockers=blockers),
    )

    paper_ready = isinstance(paper, Mapping) and paper.get("global_verdict") == PAPER_READY
    if not paper_ready:
        blockers.append("PAPER:NOT_READY")

    risk_ready = isinstance(risk, Mapping) and risk.get("global_verdict") == RISK_READY
    if not risk_ready:
        blockers.append("RISK:NOT_READY")

    capital_ready = (
        isinstance(capital, Mapping)
        and capital.get("global_verdict") == CAPITAL_READY
        and capital.get("capital_decision") == CAPITAL_DECISION_EXTENDED_PAPER
    )
    if not capital_ready:
        blockers.append("CAPITAL:NOT_READY_FOR_EXTENDED_PAPER")

    kill_switch_armed = (
        isinstance(kill_switch, Mapping)
        and kill_switch.get("global_verdict") == KILL_SWITCH_VERDICT_ARMED
        and kill_switch.get("kill_switch_decision") == KILL_SWITCH_DECISION_ARMED
        and kill_switch.get("kill_switch_state") == KILL_SWITCH_STATE_ARMED
    )
    if not kill_switch_armed:
        blockers.append("KILL_SWITCH:NOT_ARMED")

    safety_invariants_hold = all(safety_checks)
    ready = (
        safety_invariants_hold
        and paper_ready
        and risk_ready
        and capital_ready
        and kill_switch_armed
    )

    return OperationalReleaseReport(
        status=READY if ready else BLOCKED,
        ready_for_extended_paper=ready,
        paper_ready=paper_ready,
        risk_ready=risk_ready,
        capital_ready=capital_ready,
        kill_switch_armed=kill_switch_armed,
        safety_invariants_hold=safety_invariants_hold,
        blockers=tuple(dict.fromkeys(blockers)),
    )


__all__ = [
    "OperationalReleaseReport",
    "evaluate_operational_release",
    "READY",
    "BLOCKED",
]
