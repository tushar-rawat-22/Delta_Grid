from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[2]
SUMMARY_DIR = ROOT / "docs" / "research-summaries"
REGISTRY_PATH = ROOT / "docs" / "documentation-status.json"
BASE_COMMIT = "8d8e0d469a52e8a93382fa92b8117a2b09a10df6"
EXCEPTION = "docs/evidence/alpha_search_b_development/DEVELOPMENT_DECISION.md"

SUMMARY_PATHS = {
    "README.md",
    "PROJECT_AUDIT_TRAIL.md",
    "ALPHA_SEARCH_A.md",
    "ALPHA_SEARCH_B.md",
    "MISSIONS_89_TO_92.md",
    "FINAL_FREEZE.md",
}
SUBSTANTIVE_PATHS = SUMMARY_PATHS - {"README.md"}

SOURCE_GROUPS = {
    "PROJECT_AUDIT_TRAIL.md": {
        "docs/CHANGELOG.md",
        "docs/DECISION_LOG.md",
    },
    "ALPHA_SEARCH_A.md": {
        "docs/ALPHA_SEARCH_A_REJECTION.md",
        "contracts/ALPHA_SEARCH_A_REJECTION_V1.json",
        "docs/evidence/alpha_search_a_feasibility/FEASIBILITY_REJECTION.json",
    },
    "ALPHA_SEARCH_B.md": {
        "docs/ALPHA_SEARCH_B_PROTOCOL.md",
        "docs/evidence/alpha_search_b_development/DEVELOPMENT_DECISION.md",
        "contracts/ALPHA_SEARCH_B_PROTOCOL_V1.json",
        "contracts/ALPHA_SEARCH_B_COST_ATTRIBUTION_V1.json",
        "docs/evidence/alpha_search_b_development/CANDIDATE_DEVELOPMENT_RESULTS.json",
        "docs/evidence/alpha_search_b_development/COST_ATTRIBUTION.json",
        "docs/evidence/alpha_search_b_development/DATA_ACQUISITION_MANIFEST.json",
        "docs/evidence/alpha_search_b_development/DATA_CERTIFICATION.json",
        "docs/evidence/alpha_search_b_development/DEVELOPMENT_DECISION.json",
        "docs/evidence/alpha_search_b_development/FEATURE_ENGINE_MANIFEST.json",
        "docs/evidence/alpha_search_b_development/HOLM_ADJUSTMENT.json",
        "docs/evidence/alpha_search_b_development/NULL_CONTROL_RESULTS.json",
        "docs/evidence/alpha_search_b_development/PNL_ATTRIBUTION.json",
        "docs/evidence/alpha_search_b_development/PROHIBITED_ACCESS_AUDIT.json",
        "docs/evidence/alpha_search_b_development/REPLICATION_RESULTS.json",
        "docs/evidence/alpha_search_b_development/SIMULATOR_MANIFEST.json",
        "docs/evidence/alpha_search_b_development/TEST_RESULTS.json",
    },
    "MISSIONS_89_TO_92.md": {
        "docs/MISSION89_BASELINE_FALSIFICATION.md",
        "docs/MISSION90_DIRECTIONAL_TOURNAMENT.md",
        "docs/MISSION_91_NEW_ECONOMIC_HYPOTHESIS_DISCOVERY.md",
        "docs/MISSION_92_SESSION_PREMIUM_FALSIFICATION.md",
        "contracts/DELTAGRID_PRODUCT_RESET_V1.json",
        "offchain/research/contracts/mission85_funding_carry_charter_v1.json",
        "offchain/research/contracts/mission89_baseline_falsification_protocol_v1.json",
        "offchain/research/contracts/mission90_directional_strategy_charter_v1.json",
        "offchain/research/contracts/mission90_directional_tournament_protocol_v1.json",
    },
    "FINAL_FREEZE.md": {
        "docs/DELTAGRID_FINAL_PROJECT_REPORT.md",
        "contracts/DELTAGRID_FINAL_FREEZE_V1.json",
        "docs/evidence/deltagrid_final_freeze/FINAL_FREEZE_VERIFICATION.json",
    },
}

CANONICAL_SOURCES = set().union(*SOURCE_GROUPS.values())
CHECKSUM_MANIFESTS = {
    "docs/evidence/alpha_search_b_development/SHA256SUMS.txt",
    "docs/evidence/deltagrid_final_freeze/SHA256SUMS.txt",
}

EXPECTED_CHANGED_PATHS = {
    "docs/README.md",
    "offchain/tests/test_human_cli_report_language.py",
    "offchain/tests/test_research_evidence_summaries.py",
    "scripts/mission_control.py",
    "scripts/mission_pack_runner.py",
}

REQUIRED_SECTIONS = (
    "What this record covers",
    "Question investigated",
    "Evidence and controls",
    "Result",
    "Why it matters",
    "What this does not authorize",
    "Source records",
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def base_bytes(path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{BASE_COMMIT}:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout


def base_text(path: str) -> str:
    return base_bytes(path).decode("utf-8")


def registry_by_path(current: bool = True) -> dict[str, dict]:
    data = load_json(REGISTRY_PATH) if current else json.loads(
        base_text("docs/documentation-status.json")
    )
    return {item["path"]: item for item in data["documents"]}


def markdown_links(path: Path) -> list[str]:
    return re.findall(r"\[[^\]]+\]\(([^)]+)\)", path.read_text(encoding="utf-8"))


def heading_slugs(path: Path) -> set[str]:
    slugs: set[str] = set()
    occurrences: Counter[str] = Counter()
    for heading in re.findall(
        r"^#{1,6}\s+(.+?)\s*#*\s*$",
        path.read_text(encoding="utf-8"),
        re.MULTILINE,
    ):
        plain = re.sub(r"[`*_~]", "", heading).casefold()
        base = re.sub(r"[^\w\- ]", "", plain)
        base = re.sub(r"\s+", "-", base.strip())
        if not base:
            continue
        index = occurrences[base]
        occurrences[base] += 1
        slugs.add(base if index == 0 else f"{base}-{index}")
    return slugs


def assigned_sources(summary_name: str) -> set[str]:
    text = (SUMMARY_DIR / summary_name).read_text(encoding="utf-8")
    match = re.search(
        r"^## Source records\s*$\n(.*?)(?=^##\s|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None
    assigned: set[str] = set()
    for link in re.findall(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)", match.group(1)):
        target = (SUMMARY_DIR / unquote(link)).resolve()
        assigned.add(target.relative_to(ROOT.resolve()).as_posix())
    return assigned


def changed_paths() -> set[str]:
    output = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return {line[3:] for line in output.splitlines() if line}


def test_exact_summary_inventory() -> None:
    assert {path.name for path in SUMMARY_DIR.iterdir() if path.is_file()} == SUMMARY_PATHS
    assert SUBSTANTIVE_PATHS == set(SOURCE_GROUPS)


def test_canonical_source_inventory_and_classification_split() -> None:
    registered = registry_by_path()
    assert len(CANONICAL_SOURCES) == 34
    counts = Counter(registered[path]["classification"] for path in CANONICAL_SOURCES)
    assert counts == {"EVIDENCE_IMMUTABLE": 10, "MACHINE_REFERENCE": 24}


def test_base_treatment_queue_and_exact_exception() -> None:
    base = registry_by_path(current=False)
    global_queue = {
        path
        for path, item in base.items()
        if item["recommended_treatment"] == "CREATE_HUMAN_SUMMARY"
    }
    queued = {
        path
        for path in CANONICAL_SOURCES
        if base[path]["recommended_treatment"] == "CREATE_HUMAN_SUMMARY"
    }
    counts = Counter(base[path]["classification"] for path in queued)
    assert len(queued) == 33
    assert global_queue == queued
    assert counts == {"EVIDENCE_IMMUTABLE": 9, "MACHINE_REFERENCE": 24}
    assert CANONICAL_SOURCES - queued == {EXCEPTION}
    assert base[EXCEPTION]["classification"] == "EVIDENCE_IMMUTABLE"
    assert base[EXCEPTION]["recommended_treatment"] == "LEAVE_UNCHANGED"
    note = normalized(base[EXCEPTION]["notes"])
    assert "preserve historical wording" in note
    assert "companion summary" in note


def test_each_source_is_assigned_exactly_once() -> None:
    assignments = [
        source
        for summary_name in SOURCE_GROUPS
        for source in assigned_sources(summary_name)
    ]
    assert set(assignments) == CANONICAL_SOURCES
    assert len(assignments) == len(set(assignments)) == 34


def test_source_group_counts_and_exact_membership() -> None:
    assert [len(SOURCE_GROUPS[name]) for name in (
        "PROJECT_AUDIT_TRAIL.md",
        "ALPHA_SEARCH_A.md",
        "ALPHA_SEARCH_B.md",
        "MISSIONS_89_TO_92.md",
        "FINAL_FREEZE.md",
    )] == [2, 3, 17, 9, 3]
    for summary_name, expected in SOURCE_GROUPS.items():
        assert assigned_sources(summary_name) == expected
    assert EXCEPTION in assigned_sources("ALPHA_SEARCH_B.md")


def test_every_source_link_resolves() -> None:
    for source in CANONICAL_SOURCES:
        assert (ROOT / source).is_file()
    for summary_name in SOURCE_GROUPS:
        for link in markdown_links(SUMMARY_DIR / summary_name):
            target_text = unquote(link.partition("#")[0])
            if target_text:
                assert (SUMMARY_DIR / target_text).exists()


def test_index_links_all_substantive_summaries_and_authorities() -> None:
    links = set(markdown_links(SUMMARY_DIR / "README.md"))
    assert SUBSTANTIVE_PATHS <= {link.partition("#")[0] for link in links}
    assert "../README.md" in links
    assert "../DELTAGRID_FINAL_FREEZE.md" in links
    assert "../documentation-status.json" in links


def test_substantive_summaries_have_standard_structure() -> None:
    for name in SUBSTANTIVE_PATHS:
        text = (SUMMARY_DIR / name).read_text(encoding="utf-8")
        headings = re.findall(r"^##\s+(.+?)\s*$", text, re.MULTILINE)
        assert all(section in headings for section in REQUIRED_SECTIONS)
        assert headings.index("Source records") == len(headings) - 1


def test_every_summary_has_explanatory_authority_notice() -> None:
    for name in SUMMARY_PATHS:
        source = (SUMMARY_DIR / name).read_text(encoding="utf-8")
        text = normalized(source.replace(">", " "))
        assert "explanatory summary" in text
        assert re.search(
            r"(?:does|do) not replace .+?reopen research, or authorize paper "
            r"trading, live trading, capital deployment, ml, or autonomous "
            r"execution",
            text,
        )


def test_raw_source_and_final_freeze_authority_are_explicit() -> None:
    for name in SUBSTANTIVE_PATHS:
        text = normalized((SUMMARY_DIR / name).read_text(encoding="utf-8"))
        assert "exact source records control precise values and historical wording" in text
        assert "final freeze" in text and "controls current authorization" in text
        assert "discrepancy must be resolved in favor of the source record" in text


def test_alpha_search_a_stopped_before_strategy_testing() -> None:
    source = load_json(ROOT / "contracts/ALPHA_SEARCH_A_REJECTION_V1.json")
    text = normalized((SUMMARY_DIR / "ALPHA_SEARCH_A.md").read_text(encoding="utf-8"))
    assert source["status"].casefold() in text
    assert source["failed_required_series"].casefold() in text
    assert "strategy construction and result-bearing testing never occurred" in text
    assert "does not mean a strategy was backtested and found unprofitable" in text
    assert "no conclusion about whether macro regimes can predict btc" in text


def test_alpha_search_b_records_four_development_rejections() -> None:
    decision = load_json(
        ROOT / "docs/evidence/alpha_search_b_development/DEVELOPMENT_DECISION.json"
    )
    results = load_json(
        ROOT / "docs/evidence/alpha_search_b_development/CANDIDATE_DEVELOPMENT_RESULTS.json"
    )
    text = normalized((SUMMARY_DIR / "ALPHA_SEARCH_B.md").read_text(encoding="utf-8"))
    assert len(results) == 4
    assert "all four candidates were rejected in development" in text
    assert decision["decision"].casefold() in text
    assert "no candidate advanced" in text
    assert decision["selected_candidate"] is None and "selected candidate is `null`" in text


def test_alpha_search_b_keeps_validation_and_holdout_sealed() -> None:
    decision = load_json(
        ROOT / "docs/evidence/alpha_search_b_development/DEVELOPMENT_DECISION.json"
    )
    assert decision["validation_performance_accessed"] is False
    assert decision["holdout_performance_accessed"] is False
    text = normalized((SUMMARY_DIR / "ALPHA_SEARCH_B.md").read_text(encoding="utf-8"))
    assert "validation and holdout performance remained sealed" in text


def test_alpha_search_b_distinguishes_controls_and_final_decision() -> None:
    text = normalized((SUMMARY_DIR / "ALPHA_SEARCH_B.md").read_text(encoding="utf-8"))
    for concept in (
        "raw performance",
        "cost-adjusted performance",
        "null controls",
        "holm multiple-testing adjustment",
        "replication",
        "prohibited-access audit",
        "conservative costs control promotion",
        "severe costs are diagnostic",
    ):
        assert concept in text


def test_alpha_search_b_numerical_claims_match_sources() -> None:
    results = load_json(
        ROOT / "docs/evidence/alpha_search_b_development/CANDIDATE_DEVELOPMENT_RESULTS.json"
    )
    holm = load_json(
        ROOT / "docs/evidence/alpha_search_b_development/HOLM_ADJUSTMENT.json"
    )["adjusted_p_values"]
    text = (SUMMARY_DIR / "ALPHA_SEARCH_B.md").read_text(encoding="utf-8")
    for candidate, item in results.items():
        conservative = item["metrics"]["conservative"]
        expected_row = (
            f"| `{candidate}` | {conservative['trade_count']} | "
            f"`{conservative['net_profit']}` | `{holm[candidate]}` | Failed |"
        )
        assert expected_row in text
        assert item["replication_pass"] is False


def test_missions_summary_preserves_chronology_and_results() -> None:
    text = normalized((SUMMARY_DIR / "MISSIONS_89_TO_92.md").read_text(encoding="utf-8"))
    phrases = (
        "product reset: finite falsification",
        "mission 85: funding-carry research charter locked",
        "mission 89: funding and basis carry rejected and archived",
        "mission 90: all directional tournament hypotheses rejected",
        "mission 91: later session-conditional hypothesis recorded and frozen",
        "mission 92: session-premium hypothesis rejected in development",
    )
    positions = [text.index(phrase) for phrase in phrases]
    assert positions == sorted(positions)
    assert "no selected candidate or validated alpha emerged" in text


def test_mission_91_is_frozen_hypothesis_not_validated_alpha() -> None:
    text = normalized((SUMMARY_DIR / "MISSIONS_89_TO_92.md").read_text(encoding="utf-8"))
    assert "mission 91 then recorded one untested" in text
    assert "not a successful strategy" in text
    assert "not validated" in text


def test_final_freeze_separates_platform_completion_from_alpha() -> None:
    contract = load_json(ROOT / "contracts/DELTAGRID_FINAL_FREEZE_V1.json")
    source_text = (SUMMARY_DIR / "FINAL_FREEZE.md").read_text(encoding="utf-8")
    text = normalized(source_text)
    assert contract["final_project_status"] in source_text
    assert contract["validated_profitable_strategy"] is False
    assert "completed infrastructure and passing tests did not change" in text
    assert "do not establish an economic edge" in text
    assert "no candidate was selected" in text


def test_final_freeze_distinguishes_freeze_era_tests() -> None:
    evidence = load_json(
        ROOT / "docs/evidence/deltagrid_final_freeze/FINAL_FREEZE_VERIFICATION.json"
    )
    text = normalized((SUMMARY_DIR / "FINAL_FREEZE.md").read_text(encoding="utf-8"))
    assert evidence["final_actual_pass_count"] == 731
    assert "freeze-era full suite as 731 passed" in text
    assert "later documentation-suite totals" in text
    assert "not part of that immutable freeze-era count" in text


def test_project_audit_does_not_promote_historical_next_actions() -> None:
    text = normalized((SUMMARY_DIR / "PROJECT_AUDIT_TRAIL.md").read_text(encoding="utf-8"))
    assert "preserved audit trails, not a current plan" in text
    assert "later research decisions and the final freeze supersede earlier next actions" in text
    assert "old roadmap" in text and "mistaken for current authority" in text


def test_registry_final_state_and_treatment_transition() -> None:
    current = registry_by_path()
    base = registry_by_path(current=False)
    registry = load_json(REGISTRY_PATH)
    assert len(registry["documents"]) == 165
    counts = Counter(item["classification"] for item in registry["documents"])
    assert counts == {
        "CURRENT_PUBLIC": 10,
        "CURRENT_INTERNAL": 4,
        "HISTORICAL": 97,
        "SUPERSEDED": 8,
        "DESIGN_ONLY": 2,
        "EVIDENCE_IMMUTABLE": 10,
        "MACHINE_REFERENCE": 34,
    }
    transitioned = {
        path
        for path in CANONICAL_SOURCES
        if base[path]["recommended_treatment"] == "CREATE_HUMAN_SUMMARY"
        and current[path]["recommended_treatment"] == "LEAVE_UNCHANGED"
    }
    assert len(transitioned) == 33
    assert current[EXCEPTION]["recommended_treatment"] == "LEAVE_UNCHANGED"
    assert base[EXCEPTION]["recommended_treatment"] == "LEAVE_UNCHANGED"
    assert all(current[path]["recommended_treatment"] == "LEAVE_UNCHANGED" for path in CANONICAL_SOURCES)


def test_registry_preserves_source_metadata_and_conflicts() -> None:
    current = registry_by_path()
    base = registry_by_path(current=False)
    preserved_fields = {
        "classification",
        "audience",
        "purpose",
        "authority_level",
        "conflicts_with_current_state",
        "test_dependent",
        "checksum_dependent",
        "referenced_by_other_records",
        "ai_tone_severity",
        "readability_severity",
    }
    for path in CANONICAL_SOURCES:
        assert {field: current[path][field] for field in preserved_fields} == {
            field: base[path][field] for field in preserved_fields
        }
        assert "research-summaries/" in current[path]["notes"]
        assert "controlling for exact historical facts" in current[path]["notes"]
    assert current[EXCEPTION]["classification"] == "EVIDENCE_IMMUTABLE"


def test_canonical_sources_and_checksum_manifests_match_base_bytes() -> None:
    for path in CANONICAL_SOURCES | CHECKSUM_MANIFESTS:
        current = (ROOT / path).read_bytes()
        expected = base_bytes(path)
        assert hashlib.sha256(current).digest() == hashlib.sha256(expected).digest()
        assert current == expected


def test_changed_scope_excludes_every_protected_path() -> None:
    changed = changed_paths()
    assert changed == EXPECTED_CHANGED_PATHS
    assert changed.isdisjoint(CANONICAL_SOURCES | CHECKSUM_MANIFESTS)
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert staged == ""


def test_all_changed_markdown_links_and_fragments_resolve() -> None:
    sources = {ROOT / "docs/README.md"} | {
        SUMMARY_DIR / name for name in SUMMARY_PATHS
    }
    for source in sources:
        for link in markdown_links(source):
            target_text, separator, fragment = link.partition("#")
            if "://" in target_text or target_text.startswith("mailto:"):
                continue
            target = source if not target_text else source.parent / unquote(target_text)
            assert target.exists(), f"Broken link in {source}: {link}"
            if separator and fragment and target.suffix.casefold() == ".md":
                assert unquote(fragment).casefold() in heading_slugs(target)


def test_summary_prose_contains_no_positive_operational_authorization() -> None:
    combined = normalized(
        "\n".join((SUMMARY_DIR / name).read_text(encoding="utf-8") for name in SUMMARY_PATHS)
    )
    forbidden = (
        "authorizes paper trading",
        "authorizes live trading",
        "authorizes capital deployment",
        "authorizes ml training",
        "authorizes autonomous execution",
        "paper trading is authorized",
        "live trading is authorized",
        "capital deployment is authorized",
        "validated edge",
        "proven alpha",
        "production-ready trader",
        "profitable engine",
    )
    assert not any(phrase in combined for phrase in forbidden)


def test_compatibility_updates_are_exact_and_keep_test_counts() -> None:
    current_policy_path = "offchain/tests/test_current_policy_docs.py"
    banner_path = "offchain/tests/test_document_status_banners.py"
    expected_policy = base_text(current_policy_path).replace(
        'assert len(registry["documents"]) == 159',
        'assert len(registry["documents"]) == 165',
    )
    expected_banner = base_text(banner_path).replace(
        '"CURRENT_PUBLIC": 4,',
        '"CURRENT_PUBLIC": 10,',
    ).replace(
        "assert len(items) == 159",
        "assert len(items) == 165",
    ).replace(
        'assert len({item["path"] for item in items}) == 159',
        'assert len({item["path"] for item in items}) == 165',
    )
    assert (ROOT / current_policy_path).read_text(encoding="utf-8") == expected_policy
    assert (ROOT / banner_path).read_text(encoding="utf-8") == expected_banner

    for relative in (current_policy_path, banner_path):
        old_tree = ast.parse(base_text(relative))
        new_tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        old_tests = [node.name for node in ast.walk(old_tree) if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]
        new_tests = [node.name for node in ast.walk(new_tree) if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]
        assert new_tests == old_tests


def test_tests_are_repository_relative_and_docs_navigation_is_current() -> None:
    own_text = Path(__file__).read_text(encoding="utf-8")
    forbidden_root = "/" + "Users" + "/"
    assert forbidden_root not in own_text
    docs_home = normalized((ROOT / "docs/README.md").read_text(encoding="utf-8"))
    assert "research and evidence summaries" in docs_home
    assert "plain-english companions" in docs_home
    assert "do not reopen research or change any authorization" in docs_home
    assert "a human summary may explain them" not in docs_home
