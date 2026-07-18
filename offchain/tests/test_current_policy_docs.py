from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
POLICY_PATHS = {
    "research": DOCS / "RESEARCH_POLICY.md",
    "risk": DOCS / "RISK_POLICY.md",
    "safety": DOCS / "SAFETY_INVARIANTS.md",
}
REGISTRY_PATH = DOCS / "documentation-status.json"

REQUIRED_H1_TITLES = {
    "research": "Research policy",
    "risk": "Risk policy",
    "safety": "Safety invariants",
}

REQUIRED_HEADINGS = {
    "research": {
        "Purpose",
        "Current state",
        "Research-First Operating Model",
        "Research principles",
        "Research stages",
        "Data boundaries",
        "Costs and execution assumptions",
        "Statistical controls",
        "Promotion and rejection",
        "ML and AI",
        "Evidence and audit trail",
        "Reopening research",
        "What this policy does not authorize",
    },
    "risk": {
        "Purpose",
        "Current risk state",
        "Live Trading Remains Blocked",
        "Core principles",
        "Research risk",
        "Operational risk",
        "Future paper-stage controls",
        "Future proof-capital and live controls",
        "Authority separation",
        "Breach response",
        "What this policy does not authorize",
    },
    "safety": {
        "Current boundary",
        "Non-Negotiable Safety Invariants",
        "Authorization invariants",
        "Data invariants",
        "Execution invariants",
        "Risk invariants",
        "AI and model invariants",
        "Evidence invariants",
        "Changing an invariant",
        "Current non-authorizations",
    },
}

PAPER_NOT_AUTHORIZED = (
    r"\bpaper (?:trading|execution|operation) (?:is|are) not "
    r"(?:currently )?authorized\b",
    r"\bpaper (?:trading|execution|operation) and live "
    r"(?:trading|execution) are not (?:currently )?authorized\b",
)
LIVE_NOT_AUTHORIZED = (
    r"\blive (?:trading|execution) (?:is|are) not (?:currently )?authorized\b",
    r"\bpaper (?:trading|execution|operation) and live "
    r"(?:trading|execution) are not (?:currently )?authorized\b",
)
CAPITAL_NOT_AUTHORIZED = (
    r"\bcapital deployment is blocked\b",
    r"\bno capital authorization\b",
    r"\bcapital authorization (?:is|was) not (?:granted|authorized)\b",
)
RESEARCH_MODEL_PROHIBITION_CLAUSES = (
    "No model or AI component may select its own scope, change its evaluation "
    "policy, refresh protected data, promote itself, authorize capital, or "
    "place an order.",
)
SAFETY_MODEL_PROHIBITION_CLAUSES = (
    "AI and models cannot promote a strategy or model.",
    "They cannot authorize capital or obtain direct order authority.",
)
CODE_AND_TEST_PROHIBITION_CLAUSES = (
    "Code existing in the repository does not authorize its operation.",
    "Passing tests verifies the tested properties and does not authorize "
    "research, protected-data access, trading, or capital.",
)
COORDINATED_BOUNDARY_PROHIBITION_CLAUSES = (
    "No review, readiness score, model output, passing test suite, or "
    "dashboard action can change an authorization boundary by itself.",
)


def normalize_whitespace(text: str) -> str:
    return " ".join(text.casefold().split())


def normalized(path: Path) -> str:
    return normalize_whitespace(path.read_text(encoding="utf-8"))


def policy_text(name: str) -> str:
    return normalized(POLICY_PATHS[name])


def has_bound_statement(text: str, patterns: tuple[str, ...]) -> bool:
    normalized_text = normalize_whitespace(text)
    return any(
        re.search(pattern, normalized_text, re.IGNORECASE) is not None
        for pattern in patterns
    )


def contains_complete_negative_clause(
    text: str,
    accepted_clauses: tuple[str, ...],
) -> bool:
    normalized_text = normalize_whitespace(text)
    return all(
        normalize_whitespace(clause) in normalized_text
        for clause in accepted_clauses
    )


def heading_slugs(path: Path) -> set[str]:
    slugs: set[str] = set()
    occurrences: dict[str, int] = {}
    text = path.read_text(encoding="utf-8")

    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", text, re.MULTILINE):
        plain = re.sub(r"[`*_~]", "", heading).lower()
        base = re.sub(r"[^\w\- ]", "", plain)
        base = re.sub(r"\s+", "-", base.strip())
        if not base:
            continue
        duplicate_index = occurrences.get(base, 0)
        slug = base if duplicate_index == 0 else f"{base}-{duplicate_index}"
        occurrences[base] = duplicate_index + 1
        slugs.add(slug)

    return slugs


def test_policy_files_exist_and_have_required_headings() -> None:
    for name, path in POLICY_PATHS.items():
        assert path.is_file()
        text = path.read_text(encoding="utf-8")
        h1_titles = re.findall(r"^#\s+([^#].*?)\s*#*\s*$", text, re.MULTILINE)
        assert h1_titles == [REQUIRED_H1_TITLES[name]]
        headings = set(
            re.findall(
                r"^#{2,6}\s+(.+?)\s*#*\s*$",
                text,
                re.MULTILINE,
            )
        )
        assert REQUIRED_HEADINGS[name] <= headings


def test_policy_relative_links_and_fragments_resolve() -> None:
    for source in POLICY_PATHS.values():
        text = source.read_text(encoding="utf-8")
        for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            target_text, separator, fragment = link.partition("#")
            if "://" in target_text or target_text.startswith("mailto:"):
                continue
            target = source if not target_text else source.parent / target_text
            assert target.exists(), f"Broken link in {source}: {link}"
            if separator and fragment and target.suffix.lower() == ".md":
                assert unquote(fragment).lower() in heading_slugs(target), (
                    f"Broken fragment in {source}: {link}"
                )


def test_final_freeze_controls_status_without_profitability_claim() -> None:
    research = policy_text("research")
    risk = policy_text("risk")
    safety = policy_text("safety")
    assert "final freeze" in research and "controls present project status" in research
    assert "final freeze" in risk and "controls the present state" in risk
    assert "final freeze" in safety and "control the present state" in safety
    assert "no validated profitable strategy" in research
    assert "no validated profitable strategy" in safety
    assert "has a validated profitable strategy" not in " ".join((research, risk, safety))


def test_current_paper_live_and_capital_boundaries_are_explicit() -> None:
    for text in map(policy_text, POLICY_PATHS):
        assert has_bound_statement(text, PAPER_NOT_AUTHORIZED)
        assert has_bound_statement(text, LIVE_NOT_AUTHORIZED)
        assert has_bound_statement(text, CAPITAL_NOT_AUTHORIZED)


def test_reopening_and_future_stages_require_separate_authority() -> None:
    research = policy_text("research")
    assert "new versioned reopening contract" in research
    assert "genuinely new evidence" in research
    assert "listing a stage" in research and "does not authorize the stage" in research
    assert "separate, explicit authorization" in research
    assert "distinct later authorizations" in research


def test_protected_data_access_and_causal_timing_are_controlled() -> None:
    research = policy_text("research")
    safety = policy_text("safety")
    for text in (research, safety):
        assert "validation and holdout" in text
        assert "explicit authorization" in text
        assert "future information" in text
        assert "provenance" in text


def test_cost_and_statistical_controls_cover_overfitting() -> None:
    research = policy_text("research")
    for term in ("fees", "spread", "slippage", "latency", "market-impact", "stress"):
        assert term in research
    for term in (
        "minimum sample size",
        "multiple-testing correction",
        "null controls",
        "replication",
        "concentration analysis",
        "parameter sensitivity",
        "chronological",
    ):
        assert term in research
    assert "automatic optimization" in research


def test_ml_and_ai_cannot_self_promote_or_trade() -> None:
    research = policy_text("research")
    safety = policy_text("safety")
    assert "ml research and model training are not currently authorized" in research
    assert contains_complete_negative_clause(
        research,
        RESEARCH_MODEL_PROHIBITION_CLAUSES,
    )
    assert contains_complete_negative_clause(
        safety,
        SAFETY_MODEL_PROHIBITION_CLAUSES,
    )


def test_code_tests_and_readiness_do_not_create_authority() -> None:
    safety = policy_text("safety")
    assert contains_complete_negative_clause(
        safety,
        CODE_AND_TEST_PROHIBITION_CLAUSES,
    )
    assert contains_complete_negative_clause(
        safety,
        COORDINATED_BOUNDARY_PROHIBITION_CLAUSES,
    )
    assert "capital-readiness review alone cannot change a boundary" in safety


def test_unsafe_authorization_reversals_do_not_satisfy_boundaries() -> None:
    unsafe_pattern_cases = (
        (
            "Paper trading is authorized; live trading is not authorized.",
            PAPER_NOT_AUTHORIZED,
        ),
        ("Capital authorization is granted.", CAPITAL_NOT_AUTHORIZED),
    )
    unsafe_clause_cases = (
        ("The model may promote itself and place an order.",),
        ("Passing tests authorize operation.",),
        ("AI may promote itself, while a model cannot promote itself.",),
        ("AI may place orders, but ML cannot place orders.",),
        (
            "A dashboard action can change an authorization boundary by itself.",
        ),
        (
            "No review is required, but a dashboard action can change an "
            "authorization boundary by itself.",
        ),
        (
            "No model is currently selected, but a dashboard action can change "
            "an authorization boundary.",
        ),
    )

    for unsafe_text, patterns in unsafe_pattern_cases:
        assert not has_bound_statement(unsafe_text, patterns)

    complete_clauses = (
        RESEARCH_MODEL_PROHIBITION_CLAUSES
        + SAFETY_MODEL_PROHIBITION_CLAUSES
        + CODE_AND_TEST_PROHIBITION_CLAUSES
        + COORDINATED_BOUNDARY_PROHIBITION_CLAUSES
    )
    for unsafe_parts in unsafe_clause_cases:
        unsafe_text = " ".join(unsafe_parts)
        assert not any(
            normalize_whitespace(clause) in normalize_whitespace(unsafe_text)
            for clause in complete_clauses
        )


def test_limits_and_uncertain_state_fail_closed() -> None:
    risk = policy_text("risk")
    safety = policy_text("safety")
    assert "no component may raise its own" in safety
    assert "a safeguard cannot disable or bypass itself" in safety
    assert "unresolved state, recovery, or reconciliation errors cause a pause" in safety
    assert "fail closed" in risk
    assert "uncertain state remains stopped until reconciled" in risk


def test_history_and_negative_evidence_cannot_override_current_contracts() -> None:
    research = policy_text("research")
    safety = policy_text("safety")
    assert "historical next actions" in research and "do not reopen" in research
    assert "historical records cannot override the later controlling contract" in safety
    assert "negative outcomes are preserved" in safety
    assert "not rewrite an established research outcome" in safety


def test_registry_and_docs_home_record_completed_alignment() -> None:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert len(registry["documents"]) == 165
    by_path = {item["path"]: item for item in registry["documents"]}
    for path in (
        "docs/RESEARCH_POLICY.md",
        "docs/RISK_POLICY.md",
        "docs/SAFETY_INVARIANTS.md",
    ):
        item = by_path[path]
        assert item["classification"] == "CURRENT_INTERNAL"
        assert item["recommended_treatment"] == "LEAVE_UNCHANGED"
        assert item["conflicts_with_current_state"] is False
        assert item["ai_tone_severity"] == 1
        assert item["readability_severity"] == 1
        assert "aligned with the final freeze during batch 2" in item["notes"].lower()

    docs_home = normalized(DOCS / "README.md")
    assert "current internal policies aligned with the final freeze" in docs_home
    assert "wording needs later alignment" not in docs_home
