from __future__ import annotations

from copy import deepcopy

import pytest

from offchain.research.statistical_governance.core import GovernanceError
from offchain.research.statistical_governance.integrations import M102ResultSource
from offchain.research import statistical_integrity_provenance as provenance


PROPOSAL_HASH = "a" * 64


def _proposal() -> dict:
    return {
        "proposal_id": "proposal-a",
        "hypothesis_universe": [
            {"hypothesis_id": "hypothesis-1"},
            {"hypothesis_id": "hypothesis-2"},
        ],
    }


def _source(number: int) -> M102ResultSource:
    return M102ResultSource(
        f"/result-{number}", f"trial-{number}", f"/ledger-{number}",
        f"/authority-{number}", {}, f"/release-{number}", f"/custody-{number}",
    )


def _install_verified_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provenance, "validate_campaign_proposal", lambda value: deepcopy(value))
    monkeypatch.setattr(
        provenance,
        "proposal_commitment",
        lambda value: {"proposal_hash": PROPOSAL_HASH},
    )

    def verify_source(source: M102ResultSource) -> dict:
        number = int(source.trial_id.rsplit("-", 1)[1])
        return {
            "terminal_status": "SUCCESS",
            "trial_id": source.trial_id,
            "metrics": {"initial_research_nav": "100"},
            "source_number": number,
        }

    def bind(hypothesis: dict, verified: dict) -> dict:
        expected = int(hypothesis["hypothesis_id"].rsplit("-", 1)[1])
        if verified["source_number"] != expected:
            raise GovernanceError("DEVELOPMENT_RESULT_BINDING_MISMATCH")
        return verified

    def trace(source: M102ResultSource, verified: dict) -> dict:
        if verified["source_number"] == 1:
            blocks = ("1", "-0.4", "1.2", "-0.2", "0.8", "0.3")
        else:
            blocks = ("0.8", "-0.6", "0.5", "0.2", "-0.1", "0.7")
        return {
            "trace_schema": "RAB1_VERIFIED_EVENT_LEDGER_TRACE_V1",
            "event_ledger_hash": "b" * 64,
            "daily_net_pnl_blocks": blocks,
            "daily_block_count": len(blocks),
        }

    monkeypatch.setattr(provenance, "_verify_finalized_m102_source", verify_source)
    monkeypatch.setattr(provenance, "verify_development_binding", bind)
    monkeypatch.setattr(provenance, "_verified_statistical_trace", trace)


def test_complete_preregistered_universe_drives_search_adjustment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_verified_stubs(monkeypatch)
    report = provenance.build_preregistered_search_adjusted_sharpe_report(
        _proposal(),
        result_sources={"hypothesis-2": _source(2), "hypothesis-1": _source(1)},
        selected_hypothesis_id="hypothesis-1",
        periods_per_year=365,
    )
    assert report.status == "COMPLETE"
    assert report.diagnostic_only is True
    assert report.search_provenance_bound is True
    assert report.trial_independence_adjusted is False
    assert report.serial_dependence_adjusted is False
    assert report.proposal_hash == PROPOSAL_HASH
    assert report.preregistered_trial_count == 2
    assert report.verified_success_trial_count == 2
    assert list(report.trial_period_sharpes) == ["hypothesis-1", "hypothesis-2"]
    assert report.selected_report.trial_count == 2


def test_missing_or_extra_preregistered_trial_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_verified_stubs(monkeypatch)
    with pytest.raises(GovernanceError, match="SEARCH_PROVENANCE_COVERAGE_MISMATCH"):
        provenance.build_preregistered_search_adjusted_sharpe_report(
            _proposal(), result_sources={"hypothesis-1": _source(1)},
            selected_hypothesis_id="hypothesis-1", periods_per_year=365,
        )
    with pytest.raises(GovernanceError, match="SEARCH_PROVENANCE_COVERAGE_MISMATCH"):
        provenance.build_preregistered_search_adjusted_sharpe_report(
            _proposal(),
            result_sources={
                "hypothesis-1": _source(1), "hypothesis-2": _source(2),
                "hypothesis-3": _source(3),
            },
            selected_hypothesis_id="hypothesis-1", periods_per_year=365,
        )


def test_selected_hypothesis_must_be_preregistered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_verified_stubs(monkeypatch)
    with pytest.raises(GovernanceError, match="SEARCH_PROVENANCE_SELECTED_HYPOTHESIS_INVALID"):
        provenance.build_preregistered_search_adjusted_sharpe_report(
            _proposal(),
            result_sources={"hypothesis-1": _source(1), "hypothesis-2": _source(2)},
            selected_hypothesis_id="hypothesis-3", periods_per_year=365,
        )


def test_m102_binding_mismatch_is_not_bypassed(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_verified_stubs(monkeypatch)
    with pytest.raises(GovernanceError, match="DEVELOPMENT_RESULT_BINDING_MISMATCH"):
        provenance.build_preregistered_search_adjusted_sharpe_report(
            _proposal(),
            result_sources={"hypothesis-1": _source(2), "hypothesis-2": _source(1)},
            selected_hypothesis_id="hypothesis-1", periods_per_year=365,
        )


def test_nonpositive_nav_and_degenerate_trial_sharpe_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_verified_stubs(monkeypatch)
    monkeypatch.setattr(
        provenance,
        "_verified_statistical_trace",
        lambda source, verified: {
            "daily_net_pnl_blocks": ("-100", "1", "2", "3"),
            "daily_block_count": 4,
        },
    )
    with pytest.raises(GovernanceError, match="SEARCH_PROVENANCE_NONPOSITIVE_NAV"):
        provenance.build_preregistered_search_adjusted_sharpe_report(
            _proposal(),
            result_sources={"hypothesis-1": _source(1), "hypothesis-2": _source(2)},
            selected_hypothesis_id="hypothesis-1", periods_per_year=365,
        )

    _install_verified_stubs(monkeypatch)
    monkeypatch.setattr(
        provenance,
        "_verified_statistical_trace",
        lambda source, verified: {
            "daily_net_pnl_blocks": ("0", "0", "0", "0"),
            "daily_block_count": 4,
        },
    )
    with pytest.raises(GovernanceError, match="SEARCH_PROVENANCE_TRIAL_SHARPE_UNAVAILABLE"):
        provenance.build_preregistered_search_adjusted_sharpe_report(
            _proposal(),
            result_sources={"hypothesis-1": _source(1), "hypothesis-2": _source(2)},
            selected_hypothesis_id="hypothesis-1", periods_per_year=365,
        )


def test_short_or_malformed_verified_trace_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_verified_stubs(monkeypatch)
    monkeypatch.setattr(
        provenance,
        "_verified_statistical_trace",
        lambda source, verified: {
            "daily_net_pnl_blocks": ("1", "-1", "2"),
            "daily_block_count": 3,
        },
    )
    with pytest.raises(GovernanceError, match="SEARCH_PROVENANCE_TRIAL_TRACE_TOO_SHORT"):
        provenance.build_preregistered_search_adjusted_sharpe_report(
            _proposal(),
            result_sources={"hypothesis-1": _source(1), "hypothesis-2": _source(2)},
            selected_hypothesis_id="hypothesis-1", periods_per_year=365,
        )

    _install_verified_stubs(monkeypatch)
    monkeypatch.setattr(
        provenance,
        "_verified_statistical_trace",
        lambda source, verified: {
            "daily_net_pnl_blocks": ["1", "-1", "2", "-2"],
            "daily_block_count": 4,
        },
    )
    with pytest.raises(GovernanceError, match="SEARCH_PROVENANCE_VERIFIED_TRACE_INVALID"):
        provenance.build_preregistered_search_adjusted_sharpe_report(
            _proposal(),
            result_sources={"hypothesis-1": _source(1), "hypothesis-2": _source(2)},
            selected_hypothesis_id="hypothesis-1", periods_per_year=365,
        )
