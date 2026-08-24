from __future__ import annotations

from copy import deepcopy

from offchain.safety.operational_release_gate import (
    BLOCKED,
    READY,
    evaluate_operational_release,
)


def _safe_common() -> dict:
    return {
        "live_trading": "DISABLED",
        "live_order_sent": 0,
        "capital_deployment": "BLOCKED",
        "safety_breach_count": 0,
    }


def _ready_inputs() -> tuple[dict, dict, dict, dict]:
    paper = {
        **_safe_common(),
        "global_verdict": "PAPER_SANDBOX_READY_SHADOW_ONLY",
    }
    risk = {
        **_safe_common(),
        "global_verdict": "INSTITUTIONAL_RISK_CONTROL_READY_SHADOW_ONLY",
    }
    capital = {
        **_safe_common(),
        "global_verdict": "CAPITAL_READINESS_REVIEW_PAPER_ONLY_READY",
        "capital_decision": "CAPITAL_READINESS_APPROVED_FOR_EXTENDED_PAPER_OBSERVATION_ONLY",
    }
    kill_switch = {
        **_safe_common(),
        "global_verdict": "PAPER_DRAWDOWN_KILL_SWITCH_ARMED_SHADOW_ONLY",
        "kill_switch_decision": "PAPER_DRAWDOWN_KILL_SWITCH_ARMED_CONTINUE_OBSERVATION",
        "kill_switch_state": "KILL_SWITCH_STATE_ARMED_NOT_TRIGGERED",
    }
    return paper, risk, capital, kill_switch


def test_ready_requires_all_four_paper_only_controls() -> None:
    paper, risk, capital, kill_switch = _ready_inputs()
    report = evaluate_operational_release(
        paper=paper,
        risk=risk,
        capital=capital,
        kill_switch=kill_switch,
    )

    assert report.status == READY
    assert report.ready_for_extended_paper is True
    assert report.safety_invariants_hold is True
    assert report.blockers == ()
    assert report.live_trading_allowed is False
    assert report.exchange_access_allowed is False
    assert report.capital_deployment_allowed is False


def test_missing_kill_switch_blocks_release() -> None:
    paper, risk, capital, _ = _ready_inputs()
    report = evaluate_operational_release(
        paper=paper,
        risk=risk,
        capital=capital,
        kill_switch=None,
    )

    assert report.status == BLOCKED
    assert report.ready_for_extended_paper is False
    assert "KILL_SWITCH:MISSING_OR_INVALID" in report.blockers
    assert "KILL_SWITCH:NOT_ARMED" in report.blockers


def test_triggered_kill_switch_blocks_release() -> None:
    paper, risk, capital, kill_switch = _ready_inputs()
    kill_switch["kill_switch_state"] = "KILL_SWITCH_STATE_TRIGGERED"
    kill_switch["global_verdict"] = "PAPER_DRAWDOWN_KILL_SWITCH_TRIGGERED_SHADOW_ONLY"

    report = evaluate_operational_release(
        paper=paper,
        risk=risk,
        capital=capital,
        kill_switch=kill_switch,
    )

    assert report.status == BLOCKED
    assert report.kill_switch_armed is False
    assert "KILL_SWITCH:NOT_ARMED" in report.blockers


def test_any_authority_or_safety_drift_fails_closed() -> None:
    paper, risk, capital, kill_switch = _ready_inputs()
    mutated = deepcopy(risk)
    mutated["live_trading"] = "ENABLED"

    report = evaluate_operational_release(
        paper=paper,
        risk=mutated,
        capital=capital,
        kill_switch=kill_switch,
    )

    assert report.status == BLOCKED
    assert report.safety_invariants_hold is False
    assert "RISK:SAFETY_INVARIANT_FAILED" in report.blockers


def test_capital_layer_cannot_substitute_a_live_capital_decision() -> None:
    paper, risk, capital, kill_switch = _ready_inputs()
    capital["capital_decision"] = "APPROVED_FOR_REAL_CAPITAL"

    report = evaluate_operational_release(
        paper=paper,
        risk=risk,
        capital=capital,
        kill_switch=kill_switch,
    )

    assert report.status == BLOCKED
    assert report.capital_ready is False
    assert report.capital_deployment_allowed is False
    assert "CAPITAL:NOT_READY_FOR_EXTENDED_PAPER" in report.blockers
