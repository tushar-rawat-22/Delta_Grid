from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "docs" / "documentation-status.json"
DOCS_HOME = ROOT / "docs" / "README.md"
STYLE_GUIDE = ROOT / "docs" / "DOCUMENTATION_STYLE.md"
APPROVED_BASE_COMMIT = "d25ca877373e384b3d0b7b8780db8e743c9b589b"

ALLOWED_CLASSIFICATIONS = {
    "CURRENT_PUBLIC",
    "CURRENT_INTERNAL",
    "HISTORICAL",
    "SUPERSEDED",
    "DESIGN_ONLY",
    "EVIDENCE_IMMUTABLE",
    "MACHINE_REFERENCE",
}

ALLOWED_TREATMENTS = {
    "REWRITE",
    "ADD_CURRENT_STATUS_BANNER",
    "ADD_HISTORICAL_BANNER",
    "ADD_SUPERSEDED_BANNER",
    "CREATE_HUMAN_SUMMARY",
    "MOVE_ONLY_AFTER_SEPARATE_REVIEW",
    "LEAVE_UNCHANGED",
    "DELETE_NOT_RECOMMENDED",
}

REQUIRED_DOCUMENT_FIELDS = {
    "path",
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
    "recommended_treatment",
    "notes",
}

FOUNDATION_DOCUMENTS = {
    "docs/DOCUMENTATION_STYLE.md": {
        "path": "docs/DOCUMENTATION_STYLE.md",
        "classification": "CURRENT_INTERNAL",
        "audience": "Maintainers and contributors",
        "purpose": (
            "Current writing and historical-integrity standard for "
            "human-facing DeltaGrid documentation"
        ),
        "authority_level": "A1",
        "conflicts_with_current_state": False,
        "test_dependent": True,
        "checksum_dependent": False,
        "referenced_by_other_records": False,
        "ai_tone_severity": 1,
        "readability_severity": 1,
        "recommended_treatment": "LEAVE_UNCHANGED",
        "notes": (
            "Current documentation-writing standard. It does not alter "
            "research, risk, or trading authority."
        ),
    },
    "docs/README.md": {
        "path": "docs/README.md",
        "classification": "CURRENT_PUBLIC",
        "audience": (
            "Public readers, maintainers, researchers, reviewers, and "
            "future team members"
        ),
        "purpose": "Authoritative navigation entrance for DeltaGrid documentation",
        "authority_level": "A1",
        "conflicts_with_current_state": False,
        "test_dependent": True,
        "checksum_dependent": False,
        "referenced_by_other_records": False,
        "ai_tone_severity": 1,
        "readability_severity": 1,
        "recommended_treatment": "LEAVE_UNCHANGED",
        "notes": (
            "Current documentation home created by the "
            "documentation-authority foundation. It explains status and "
            "navigation but does not override the final-freeze contract."
        ),
    },
    "docs/documentation-status.json": {
        "path": "docs/documentation-status.json",
        "classification": "MACHINE_REFERENCE",
        "audience": "Maintainers, automated tests, and future dashboard consumers",
        "purpose": (
            "Machine-readable classification and authority registry for "
            "DeltaGrid documentation"
        ),
        "authority_level": "A1",
        "conflicts_with_current_state": False,
        "test_dependent": True,
        "checksum_dependent": False,
        "referenced_by_other_records": False,
        "ai_tone_severity": 0,
        "readability_severity": 0,
        "recommended_treatment": "LEAVE_UNCHANGED",
        "notes": (
            "The registry classifies current, historical, superseded, "
            "design-only, evidence, and machine-reference documentation. "
            "It is not itself a research or trading authorization."
        ),
    },
}

EXPECTED_CLASSIFICATION_COUNTS = {
    "CURRENT_PUBLIC": 4,
    "CURRENT_INTERNAL": 4,
    "HISTORICAL": 97,
    "SUPERSEDED": 8,
    "DESIGN_ONLY": 2,
    "EVIDENCE_IMMUTABLE": 10,
    "MACHINE_REFERENCE": 34,
}

SUPERSEDED_BANNER_PATHS = {
    "docs/CHARTER.md",
    "docs/DELTAGRID_PRODUCT_RESET.md",
    "docs/DELTA_AUTONOMOUS_BOT_ROADMAP.md",
    "docs/DOCUMENTATION_REGISTRY.md",
    "docs/INSTITUTIONAL_ALPHA_RESEARCH_PLAN.md",
    "docs/PROJECT_SOURCE_OF_TRUTH.md",
    "docs/ROADMAP.md",
    "docs/STRATEGY_RESEARCH_ROADMAP.md",
}
HISTORICAL_TOP_LEVEL_BANNER_PATHS = {
    "docs/ARCHITECTURE_STATE.md",
    "docs/MISSION_INDEX.md",
}
DESIGN_ONLY_BANNER_PATHS = {"docs/DELTA_AUTONOMY_ARCHITECTURE.md"}
EXPECTED_NON_TARGET_REGISTRY_SHA256 = (
    "baed760c8a63b740fa5f2aa8a15197407251267eb7d0bbe9ffc583059bdeda91"
)


def load_registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def documents_by_path() -> dict[str, dict]:
    return {item["path"]: item for item in load_registry()["documents"]}


def repository_relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def approved_inventory() -> set[str]:
    """Return the explicit 156-file inventory approved by the audit."""
    paths = {
        ".gitignore",
        "README.md",
        "contracts/foundry.toml",
        "contracts/remappings.txt",
        "offchain/config/.env.example",
        "offchain/config/seed_pools.json",
        "offchain/config/seed_tokens.json",
        "offchain/requirements.txt",
    }

    paths.update(
        repository_relative(path)
        for path in (ROOT / "contracts").glob("*.json")
    )
    paths.update(
        repository_relative(path)
        for path in (ROOT / "docs").glob("*.md")
        if path.name not in {"README.md", "DOCUMENTATION_STYLE.md"}
    )
    paths.update(
        repository_relative(path)
        for path in (ROOT / "docs" / "ADR").glob("*.md")
    )
    paths.update(
        repository_relative(path)
        for path in (ROOT / "docs" / "evidence").rglob("*")
        if path.is_file()
    )
    paths.update(
        repository_relative(path)
        for path in (ROOT / "offchain" / "research" / "contracts").glob("*.json")
    )
    return paths


def markdown_links(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return re.findall(r"\[[^\]]+\]\(([^)]+)\)", text)


def normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def markdown_heading_slugs(path: Path) -> set[str]:
    """Return GitHub-style slugs sufficient for the repository's headings."""
    slugs: set[str] = set()
    occurrences: dict[str, int] = {}

    for heading in re.findall(
        r"^#{1,6}\s+(.+?)\s*#*\s*$",
        path.read_text(encoding="utf-8"),
        re.MULTILINE,
    ):
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


def test_registry_parses_as_json() -> None:
    assert isinstance(load_registry(), dict)


def test_schema_version_is_exact() -> None:
    assert load_registry()["schema_version"] == "1.0"


def test_authority_paths_exist() -> None:
    authority = load_registry()["authority"]
    authority_paths = [
        value
        for key, value in authority.items()
        if key.endswith("_path")
    ]
    assert authority_paths
    assert all((ROOT / path).is_file() for path in authority_paths)


def test_baseline_commit_is_approved_audit_base() -> None:
    authority = load_registry()["authority"]
    assert authority["baseline_commit"] == APPROVED_BASE_COMMIT
    assert "not a permanent assertion" in authority["baseline_scope"]


def test_document_paths_are_unique() -> None:
    paths = [item["path"] for item in load_registry()["documents"]]
    assert len(paths) == len(set(paths))


def test_every_registered_path_exists() -> None:
    assert all(
        (ROOT / item["path"]).is_file()
        for item in load_registry()["documents"]
    )


def test_documents_are_sorted_lexicographically() -> None:
    paths = [item["path"] for item in load_registry()["documents"]]
    assert paths == sorted(paths)


def test_every_classification_is_allowed() -> None:
    registry = load_registry()
    assert set(registry["classifications"]) == ALLOWED_CLASSIFICATIONS
    assert all(
        item["classification"] in ALLOWED_CLASSIFICATIONS
        for item in registry["documents"]
    )
    actual_counts = {
        classification: sum(
            item["classification"] == classification
            for item in registry["documents"]
        )
        for classification in ALLOWED_CLASSIFICATIONS
    }
    assert actual_counts == EXPECTED_CLASSIFICATION_COUNTS


def test_every_treatment_is_allowed() -> None:
    registry = load_registry()
    assert set(registry["treatments"]) == ALLOWED_TREATMENTS
    assert all(
        item["recommended_treatment"] in ALLOWED_TREATMENTS
        for item in registry["documents"]
    )


def test_severity_values_are_integers_from_zero_to_five() -> None:
    for item in load_registry()["documents"]:
        for field in ("ai_tone_severity", "readability_severity"):
            value = item[field]
            assert type(value) is int
            assert 0 <= value <= 5


def test_dependency_and_conflict_fields_are_booleans() -> None:
    fields = (
        "conflicts_with_current_state",
        "test_dependent",
        "checksum_dependent",
        "referenced_by_other_records",
    )
    for item in load_registry()["documents"]:
        assert all(type(item[field]) is bool for field in fields)


def test_readme_is_current_public() -> None:
    registered = documents_by_path()
    assert registered["README.md"]["classification"] == "CURRENT_PUBLIC"
    assert registered["docs/README.md"]["classification"] == "CURRENT_PUBLIC"


def test_final_freeze_explanation_is_current_public() -> None:
    item = documents_by_path()["docs/DELTAGRID_FINAL_FREEZE.md"]
    assert item["classification"] == "CURRENT_PUBLIC"


def test_future_strategy_intake_is_current_public() -> None:
    item = documents_by_path()["docs/FUTURE_STRATEGY_INTAKE_POLICY.md"]
    assert item["classification"] == "CURRENT_PUBLIC"


def test_ml_adapter_is_design_only() -> None:
    item = documents_by_path()["docs/DELTAGRID_ML_RESEARCH_ADAPTER.md"]
    assert item["classification"] == "DESIGN_ONLY"


def test_banner_target_registry_entries_record_completed_treatment() -> None:
    registered = documents_by_path()
    adr_paths = {
        repository_relative(path)
        for path in (ROOT / "docs" / "ADR").glob("*.md")
    }
    expected_by_classification = {
        "HISTORICAL": (
            "Batch 3 added a historical banner; the historical body remains "
            "preserved."
        ),
        "SUPERSEDED": (
            "Batch 3 added a superseded banner; the historical body remains "
            "preserved."
        ),
        "DESIGN_ONLY": (
            "Batch 3 added a design-only banner; the design body remains preserved."
        ),
    }
    target_paths = (
        SUPERSEDED_BANNER_PATHS
        | HISTORICAL_TOP_LEVEL_BANNER_PATHS
        | DESIGN_ONLY_BANNER_PATHS
        | adr_paths
    )

    assert len(adr_paths) == 95
    assert len(target_paths) == 106
    for path in target_paths:
        item = registered[path]
        assert item["recommended_treatment"] == "LEAVE_UNCHANGED"
        assert item["conflicts_with_current_state"] is False
        assert item["notes"] == expected_by_classification[item["classification"]]

    non_target_entries = [
        item
        for item in load_registry()["documents"]
        if item["path"] not in target_paths
    ]
    canonical = json.dumps(
        non_target_entries,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    assert len(non_target_entries) == 53
    assert hashlib.sha256(canonical).hexdigest() == (
        EXPECTED_NON_TARGET_REGISTRY_SHA256
    )


def test_every_adr_is_registered_and_historical() -> None:
    registered = documents_by_path()
    adr_paths = {
        repository_relative(path)
        for path in (ROOT / "docs" / "ADR").glob("*.md")
    }
    assert adr_paths
    assert all(
        path in registered and registered[path]["classification"] == "HISTORICAL"
        for path in adr_paths
    )


def test_every_evidence_file_is_registered() -> None:
    registered = documents_by_path()
    evidence_paths = {
        repository_relative(path)
        for path in (ROOT / "docs" / "evidence").rglob("*")
        if path.is_file()
    }
    assert evidence_paths
    assert evidence_paths <= set(registered)


def test_no_evidence_file_is_assigned_rewrite() -> None:
    for path, item in documents_by_path().items():
        if path.startswith("docs/evidence/"):
            assert item["recommended_treatment"] != "REWRITE"


def test_top_level_json_contracts_are_machine_references() -> None:
    registered = documents_by_path()
    contract_paths = {
        repository_relative(path)
        for path in (ROOT / "contracts").glob("*.json")
    }
    assert contract_paths
    assert all(
        registered[path]["classification"] == "MACHINE_REFERENCE"
        for path in contract_paths
    )


def test_research_json_contracts_are_machine_references() -> None:
    registered = documents_by_path()
    contract_paths = {
        repository_relative(path)
        for path in (ROOT / "offchain" / "research" / "contracts").glob("*.json")
    }
    assert contract_paths
    assert all(
        registered[path]["classification"] == "MACHINE_REFERENCE"
        for path in contract_paths
    )


def test_registry_paths_are_relative_forward_slash_paths() -> None:
    for item in load_registry()["documents"]:
        path = item["path"]
        pure = PurePosixPath(path)
        assert "\\" not in path
        assert not pure.is_absolute()
        assert ".." not in pure.parts
        assert pure.as_posix() == path


def test_no_implementation_python_file_is_registered() -> None:
    paths = {item["path"] for item in load_registry()["documents"]}
    assert not any(path.endswith(".py") for path in paths)
    assert "offchain/tests/test_documentation_status.py" not in paths


def test_docs_home_explains_every_status_label() -> None:
    text = DOCS_HOME.read_text(encoding="utf-8")
    assert all(label in text for label in ALLOWED_CLASSIFICATIONS)


def test_docs_home_states_final_freeze_conflict_rule() -> None:
    text = normalize_whitespace(DOCS_HOME.read_text(encoding="utf-8"))
    assert normalize_whitespace(
        "When historical documents conflict with the final freeze, "
        "the final freeze controls."
    ) in text


def test_style_guide_protects_history_and_authorization() -> None:
    text = normalize_whitespace(STYLE_GUIDE.read_text(encoding="utf-8"))
    assert "protects historical and research integrity" in text
    assert "must never imply" in text
    assert "Never alter evidence merely to improve style" in text
    assert "Preserve the body text of historical records" in text
    assert (
        documents_by_path()["docs/DOCUMENTATION_STYLE.md"]["classification"]
        == "CURRENT_INTERNAL"
    )


def test_relative_markdown_links_resolve() -> None:
    for source in (DOCS_HOME, STYLE_GUIDE):
        for link in markdown_links(source):
            target_text, separator, fragment = link.partition("#")
            if "://" in target_text or target_text.startswith("mailto:"):
                continue
            target = source if not target_text else source.parent / target_text
            assert target.exists(), f"Broken link in {source}: {link}"
            if separator and fragment and target.suffix.lower() == ".md":
                assert unquote(fragment).lower() in markdown_heading_slugs(target), (
                    f"Broken fragment in {source}: {link}"
                )


def test_registry_documents_have_exact_required_fields() -> None:
    for item in load_registry()["documents"]:
        assert set(item) == REQUIRED_DOCUMENT_FIELDS


def test_registry_covers_exact_approved_inventory() -> None:
    registered = documents_by_path()
    approved = approved_inventory()
    assert len(approved) == 156
    assert approved <= set(registered)
    assert set(registered) == approved | set(FOUNDATION_DOCUMENTS)
    assert len(registered) == 159
    assert all(
        registered[path] == expected
        for path, expected in FOUNDATION_DOCUMENTS.items()
    )
