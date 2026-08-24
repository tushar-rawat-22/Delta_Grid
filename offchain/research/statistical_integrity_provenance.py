"""Bind search-adjusted Sharpe diagnostics to preregistered, replay-verified trials."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
import math
import statistics
from typing import Any, Mapping

from offchain.research.statistical_governance.core import GovernanceError, require_decimal_text
from offchain.research.statistical_governance.integrations import (
    M102ResultSource,
    _verified_statistical_trace,
    _verify_finalized_m102_source,
)
from offchain.research.statistical_governance.protocol import (
    proposal_commitment,
    validate_campaign_proposal,
    verify_development_binding,
)

from .statistical_integrity import (
    SearchAdjustedSharpeReport,
    build_search_adjusted_sharpe_report,
)


@dataclass(frozen=True)
class PreregisteredSearchAdjustedSharpeReport:
    """Diagnostic report whose search universe is bound to a frozen M103 proposal."""

    status: str
    diagnostic_only: bool
    search_provenance_bound: bool
    serial_dependence_adjusted: bool
    trial_independence_adjusted: bool
    proposal_id: str
    proposal_hash: str
    selected_hypothesis_id: str
    preregistered_trial_count: int
    verified_success_trial_count: int
    trial_period_sharpes: dict[str, float]
    selected_report: SearchAdjustedSharpeReport

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["selected_report"] = self.selected_report.to_dict()
        return value


def _daily_returns_from_verified_trace(
    verified: Mapping[str, Any], trace: Mapping[str, Any]
) -> list[float]:
    metrics = verified.get("metrics") if isinstance(verified, Mapping) else None
    if not isinstance(metrics, Mapping):
        raise GovernanceError("SEARCH_PROVENANCE_VERIFIED_METRICS_REQUIRED")
    initial_nav = require_decimal_text(
        metrics.get("initial_research_nav"), "initial_research_nav"
    )
    if initial_nav <= 0:
        raise GovernanceError("SEARCH_PROVENANCE_NONPOSITIVE_NAV")

    blocks = trace.get("daily_net_pnl_blocks") if isinstance(trace, Mapping) else None
    count = trace.get("daily_block_count") if isinstance(trace, Mapping) else None
    if not isinstance(blocks, tuple) or type(count) is not int or count != len(blocks) or not blocks:
        raise GovernanceError("SEARCH_PROVENANCE_VERIFIED_TRACE_INVALID")

    nav = initial_nav
    returns: list[float] = []
    for raw_block in blocks:
        block = require_decimal_text(raw_block, "daily_net_pnl_block")
        value = block / nav
        as_float = float(value)
        if not math.isfinite(as_float):
            raise GovernanceError("SEARCH_PROVENANCE_RETURN_INVALID")
        returns.append(as_float)
        nav += block
        if nav <= 0:
            raise GovernanceError("SEARCH_PROVENANCE_NONPOSITIVE_NAV")
    return returns


def _period_sharpe(values: list[float]) -> float:
    if len(values) < 4:
        raise GovernanceError("SEARCH_PROVENANCE_TRIAL_TRACE_TOO_SHORT")
    standard_deviation = statistics.stdev(values)
    if standard_deviation <= 0 or not math.isfinite(standard_deviation):
        raise GovernanceError("SEARCH_PROVENANCE_TRIAL_SHARPE_UNAVAILABLE")
    result = statistics.fmean(values) / standard_deviation
    if not math.isfinite(result):
        raise GovernanceError("SEARCH_PROVENANCE_TRIAL_SHARPE_UNAVAILABLE")
    return result


def build_preregistered_search_adjusted_sharpe_report(
    proposal: Mapping[str, Any],
    *,
    result_sources: Mapping[str, M102ResultSource],
    selected_hypothesis_id: str,
    periods_per_year: int,
) -> PreregisteredSearchAdjustedSharpeReport:
    """Derive PSR/DSR inputs from the complete frozen M103 hypothesis universe.

    Every preregistered hypothesis must have one replay-verified successful M102
    result source. Missing, extra, failed, or mismatched trials are not silently
    dropped. The raw preregistered trial count is disclosed as not adjusted for
    correlation between trials; this function does not estimate an effective
    number of independent trials.
    """

    if not isinstance(result_sources, Mapping):
        raise GovernanceError("SEARCH_PROVENANCE_SOURCE_MAPPING_INVALID")
    validated = validate_campaign_proposal(proposal)
    hypotheses = validated["hypothesis_universe"]
    ordered_ids = [item["hypothesis_id"] for item in hypotheses]
    expected_ids = set(ordered_ids)
    supplied_ids = set(result_sources)
    if supplied_ids != expected_ids:
        raise GovernanceError("SEARCH_PROVENANCE_COVERAGE_MISMATCH")
    if selected_hypothesis_id not in expected_ids:
        raise GovernanceError("SEARCH_PROVENANCE_SELECTED_HYPOTHESIS_INVALID")

    returns_by_hypothesis: dict[str, list[float]] = {}
    sharpes: dict[str, float] = {}
    for hypothesis in hypotheses:
        hypothesis_id = hypothesis["hypothesis_id"]
        source = result_sources[hypothesis_id]
        if type(source) is not M102ResultSource:
            raise GovernanceError("M102_RESULT_SOURCE_INVALID")
        verified = _verify_finalized_m102_source(source)
        bound = verify_development_binding(hypothesis, verified)
        trace = _verified_statistical_trace(source, bound)
        returns = _daily_returns_from_verified_trace(bound, trace)
        returns_by_hypothesis[hypothesis_id] = returns
        sharpes[hypothesis_id] = _period_sharpe(returns)

    selected = build_search_adjusted_sharpe_report(
        returns_by_hypothesis[selected_hypothesis_id],
        trial_period_sharpes=[sharpes[hypothesis_id] for hypothesis_id in ordered_ids],
        periods_per_year=periods_per_year,
    )
    commitment = proposal_commitment(validated)
    return PreregisteredSearchAdjustedSharpeReport(
        status=selected.status,
        diagnostic_only=True,
        search_provenance_bound=True,
        serial_dependence_adjusted=selected.serial_dependence_adjusted,
        trial_independence_adjusted=False,
        proposal_id=validated["proposal_id"],
        proposal_hash=commitment["proposal_hash"],
        selected_hypothesis_id=selected_hypothesis_id,
        preregistered_trial_count=len(ordered_ids),
        verified_success_trial_count=len(sharpes),
        trial_period_sharpes=sharpes,
        selected_report=selected,
    )


__all__ = [
    "PreregisteredSearchAdjustedSharpeReport",
    "build_preregistered_search_adjusted_sharpe_report",
]
