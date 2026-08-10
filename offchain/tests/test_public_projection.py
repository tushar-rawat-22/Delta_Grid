from __future__ import annotations

import ast
import json
from pathlib import Path
import stat

import pytest

from offchain.market_data_acquisition.core import canonical_json, strict_json_load
from offchain.public_projection import (
    CONTRACT_HASH,
    ProjectionError,
    build_projection,
    export_projection,
    load_contracts,
    verify_projection_package,
)
from offchain.public_projection.__main__ import main as projection_main
from offchain.public_projection.core import (
    ALLOWED_PUBLIC_DOCUMENT_PATHS,
    BASE_COMMIT,
    MANIFEST_FILENAME,
    PROJECTION_FILENAME,
    REPOSITORY_ROOT,
    canonical_bytes,
    contract_hash,
    source_file,
)
from offchain.public_projection.schema import validate_projection


ROOT = Path(__file__).resolve().parents[2]
PUBLIC_PROJECTION_ROOT = ROOT / "offchain" / "public_projection"


def test_contract_is_exact_and_non_authorizing() -> None:
    contract, autonomy, mission103 = load_contracts()
    assert contract["contract_hash_sha256"] == CONTRACT_HASH
    assert contract_hash(contract) == CONTRACT_HASH
    assert contract["base_commit"] == BASE_COMMIT
    assert contract["authority_effect"] == "NONE"
    assert contract["authority"]["public_repository_projection"] is True
    assert all(
        contract["authority"][field] is False
        for field in (
            "private_runtime_metadata_projection",
            "market_value_projection",
            "protected_value_projection",
            "network_access",
            "research_execution",
            "validation_or_holdout_opening",
            "model_or_ml",
            "paper_trading",
            "live_trading",
            "exchange_access",
            "credential_access",
            "signed_requests",
            "orders",
            "portfolio_allocation",
            "capital_deployment",
            "self_authorization",
        )
    )
    assert autonomy["contract_id"] == "deltagrid-autonomy-constitution-v5"
    assert mission103["contract_id"] == "deltagrid-independent-research-validation-governance-v1"


def test_p1_1_contract_forbids_private_runtime_and_network_sources() -> None:
    contract, _autonomy, _mission103 = load_contracts()
    scope = contract["source_scope"]
    assert scope["private_runtime_roots"] is False
    assert scope["sqlite_open"] is False
    assert scope["environment_secrets"] is False
    assert scope["git_remote_credentials"] is False
    assert scope["arbitrary_paths"] is False
    assert contract["output"]["network_publish"] is False


def test_projection_package_has_no_network_or_private_runtime_imports() -> None:
    forbidden_modules = {
        "http.client",
        "httpx",
        "requests",
        "socket",
        "sqlite3",
        "urllib.request",
        "websockets",
        "offchain.market_data_acquisition.backup",
        "offchain.market_data_acquisition.journal",
        "offchain.market_data_acquisition.service",
        "offchain.research.research_reopening",
        "offchain.research.statistical_governance.store",
        "offchain.research.statistical_governance.protected",
    }
    for path in sorted(PUBLIC_PROJECTION_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert not (imported & forbidden_modules), f"forbidden import in {path}: {sorted(imported & forbidden_modules)}"


def test_projection_is_deterministic_and_contains_only_allowlisted_sections() -> None:
    first = build_projection()
    second = build_projection()
    assert canonical_bytes(first) == canonical_bytes(second)
    assert set(first) == {
        "schema_id",
        "source_classes",
        "core_identity",
        "authority",
        "contract_identities",
        "public_document_identities",
    }
    assert [item["path"] for item in first["public_document_identities"]] == list(ALLOWED_PUBLIC_DOCUMENT_PATHS)
    assert first["authority"]["maximum_verdict_authority_effect"] == "NONE"
    assert first["authority"]["production_statistical_adapter_count"] == 0
    assert first["authority"]["production_protected_evaluator_count"] == 0
    assert all(
        first["authority"][field] is False
        for field in (
            "m104_observation",
            "model_training_or_ml",
            "paper_trading",
            "live_trading",
            "exchange_account_access",
            "credential_access",
            "signed_exchange_requests",
            "order_placement",
            "portfolio_allocation",
            "capital_deployment",
            "self_authorization",
        )
    )


def test_projection_contains_no_private_runtime_or_market_value_fields() -> None:
    text = canonical_json(build_projection()).lower()
    forbidden = (
        "payload_json",
        "governance.sqlite3",
        "acquisition.sqlite3",
        "research_authority",
        "~/.deltagrid",
        "/users/",
        "api_key",
        "service_role",
        "access_token",
        "refresh_token",
        "founder_nonce",
        "protected_window",
        "market_price",
    )
    assert all(marker not in text for marker in forbidden)


def test_source_file_rejects_arbitrary_paths() -> None:
    with pytest.raises(ProjectionError, match="SOURCE_PATH_NOT_ALLOWED"):
        source_file(ROOT, "offchain/market_data_acquisition/schema.py")



def test_export_rejects_symlink_parent_component(tmp_path: Path) -> None:
    physical = tmp_path / "physical"
    physical.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(physical, target_is_directory=True)

    with pytest.raises(ProjectionError, match="PATH_SYMLINK_FORBIDDEN"):
        export_projection(alias / "projection-package")


def test_verify_rejects_symlink_parent_component(tmp_path: Path) -> None:
    physical = tmp_path / "physical"
    package = physical / "projection-package"
    export_projection(package)

    alias = tmp_path / "alias"
    alias.symlink_to(physical, target_is_directory=True)

    with pytest.raises(ProjectionError, match="PACKAGE_PATH_SYMLINK"):
        verify_projection_package(alias / "projection-package")


def test_export_accepts_canonicalized_physical_destination(tmp_path: Path) -> None:
    physical = tmp_path / "physical"
    physical.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(physical, target_is_directory=True)

    destination = (alias / "projection-package").resolve(strict=False)
    exported = export_projection(destination)
    assert exported["verdict"] == "PASS"
    assert verify_projection_package(destination) == exported

def test_export_and_verify_round_trip(tmp_path: Path) -> None:
    destination = tmp_path / "projection-package"
    exported = export_projection(destination)
    assert exported["verdict"] == "PASS"
    assert exported["file_count"] == 2
    assert {item.name for item in destination.iterdir()} == {PROJECTION_FILENAME, MANIFEST_FILENAME}
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700
    assert stat.S_IMODE((destination / PROJECTION_FILENAME).stat().st_mode) == 0o600
    assert stat.S_IMODE((destination / MANIFEST_FILENAME).stat().st_mode) == 0o600

    verified = verify_projection_package(destination)
    assert verified == exported


def test_export_rejects_destination_inside_repository() -> None:
    with pytest.raises(ProjectionError, match="DESTINATION_INSIDE_REPOSITORY"):
        export_projection(REPOSITORY_ROOT / ".p1-projection-output")


def test_export_rejects_nonempty_existing_destination(tmp_path: Path) -> None:
    destination = tmp_path / "nonempty"
    destination.mkdir()
    (destination / "existing.txt").write_text("do not overwrite", encoding="utf-8")
    with pytest.raises(ProjectionError, match="DESTINATION_NOT_EMPTY"):
        export_projection(destination)
    assert (destination / "existing.txt").read_text(encoding="utf-8") == "do not overwrite"


def test_verify_rejects_extra_package_file(tmp_path: Path) -> None:
    destination = tmp_path / "projection-package"
    export_projection(destination)
    (destination / "unexpected.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ProjectionError, match="PACKAGE_FILE_SET_MISMATCH"):
        verify_projection_package(destination)


def test_verify_rejects_projection_tamper(tmp_path: Path) -> None:
    destination = tmp_path / "projection-package"
    export_projection(destination)
    projection_path = destination / PROJECTION_FILENAME
    projection = strict_json_load(projection_path)
    projection["authority"]["paper_trading"] = True
    projection_path.write_bytes(canonical_bytes(projection))
    with pytest.raises(ProjectionError):
        verify_projection_package(destination)


def test_verify_rejects_manifest_tamper(tmp_path: Path) -> None:
    destination = tmp_path / "projection-package"
    export_projection(destination)
    manifest_path = destination / MANIFEST_FILENAME
    manifest = strict_json_load(manifest_path)
    manifest["projection_sha256"] = "0" * 64
    manifest_path.write_bytes(canonical_bytes(manifest))
    with pytest.raises(ProjectionError, match="PROJECTION_HASH_MISMATCH"):
        verify_projection_package(destination)


def test_verify_rejects_noncanonical_json_bytes(tmp_path: Path) -> None:
    destination = tmp_path / "projection-package"
    export_projection(destination)
    projection_path = destination / PROJECTION_FILENAME
    value = strict_json_load(projection_path)
    projection_path.write_text(json.dumps(value, indent=2), encoding="utf-8")
    with pytest.raises(ProjectionError, match="PACKAGE_NOT_CANONICAL"):
        verify_projection_package(destination)


def test_projection_schema_rejects_unknown_field() -> None:
    projection = build_projection()
    projection["unexpected"] = "forbidden"
    with pytest.raises(ProjectionError, match="PROJECTION_SCHEMA_INVALID"):
        validate_projection(projection)


def test_documentation_registry_classifies_p1_files() -> None:
    registry = json.loads((ROOT / "docs" / "documentation-status.json").read_text(encoding="utf-8"))
    by_path = {item["path"]: item for item in registry["documents"]}
    assert by_path["contracts/DELTAGRID_PUBLIC_PROJECTION_V1.json"]["classification"] == "MACHINE_REFERENCE"
    assert by_path["docs/DELTAGRID_PUBLIC_PROJECTION.md"]["classification"] == "CURRENT_INTERNAL"
    assert all(
        by_path[path]["recommended_treatment"] == "LEAVE_UNCHANGED"
        for path in (
            "contracts/DELTAGRID_PUBLIC_PROJECTION_V1.json",
            "docs/DELTAGRID_PUBLIC_PROJECTION.md",
        )
    )


def test_cli_show_contract_is_machine_safe(capsys: pytest.CaptureFixture[str]) -> None:
    assert projection_main(["show-contract"]) == 0
    captured = capsys.readouterr()
    value = json.loads(captured.out)
    assert value == {
        "authority_effect": "NONE",
        "contract_hash_sha256": CONTRACT_HASH,
        "contract_id": "deltagrid-public-projection-v1",
    }
    assert captured.err == ""
