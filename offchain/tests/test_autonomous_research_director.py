from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
import hashlib
import inspect
import json
from pathlib import Path
import sqlite3

import pytest

import offchain.research.director as director_api
from offchain.orchestration import (
    TickOutcome,
    WorkflowLedger,
    WorkflowOrchestrator,
)
from offchain.research.admission import canonical_hash, canonical_json
from offchain.research.director import (
    ACTION_IDS,
    ACTION_REGISTRY,
    MISSION_CONTRACT_HASH,
    MISSION_CONTRACT_ID,
    DecisionPackage,
    DirectorError,
    ResearchDirectorLedger,
    ResearchDirectorService,
)
from offchain.research.director.action_registry import (
    EXPLANATIONS,
    POLICY_OUTCOMES,
)
from offchain.research.director.evidence import (
    parse_dossier,
    parse_request,
    verify_contract_chain,
)
from offchain.research.director.models import (
    MAX_RECORDED_DECISIONS,
    REJECTED_FAMILY_IDS,
    REQUESTED_AUTHORITY_FIELDS,
    DirectorRequest,
    EvidenceView,
    ResearchDecision,
    ResearchOpportunityDossier,
    VerificationReceipt,
)
from offchain.research.director.verifier import ResearchDirectorVerifier
from offchain.tests.test_research_control_plane import make_ledger


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contracts" / "DELTAGRID_AUTONOMOUS_RESEARCH_DIRECTOR_V1.json"
PACKAGE = ROOT / "offchain" / "research" / "director"
WORKFLOW = ROOT / ".github" / "workflows" / "deltagrid-ci.yml"
IMPLEMENTATION_COMMIT = "1" * 40
OBSERVATION_AS_OF = "2026-08-04T10:00:00Z"
REQUESTED_AT = "2026-08-04T10:00:03Z"
DECISION_AS_OF = "2026-08-04T10:00:04Z"


def _contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def _canonical_write(path: Path, value: dict) -> bytes:
    raw = canonical_json(value).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def _dossier_core(**changes) -> dict:
    value = {
        "schema_version": "1.0",
        "proposal_id": "proposal-1",
        "proposal_kind": "RESEARCH_REOPENING_CANDIDATE",
        "economic_mechanism": "A distinct causal mechanism.",
        "falsifiable_claim": "The stated effect can be rejected.",
        "new_information_type": "INDEPENDENT_ACADEMIC_EVIDENCE",
        "new_information_reference": {
            "reference_id": "reference-1",
            "sha256": "2" * 64,
        },
        "provenance_status": "VERIFIED",
        "causal_availability_status": "SUPPORTED",
        "overlap_audit_status": "NO_MATERIAL_OVERLAP",
        "compared_rejected_family_ids": list(REJECTED_FAMILY_IDS),
        "overlap_evidence_references": [
            {"reference_id": "overlap-1", "sha256": "3" * 64}
        ],
        "requested_stage": "DRAFT_REOPENING_CONTRACT_ONLY",
        "requested_authorities": {
            field: False for field in REQUESTED_AUTHORITY_FIELDS
        },
        "draft_reopening_contract_reference": None,
        "created_at": "2026-08-04T10:00:02Z",
    }
    value.update(changes)
    value["canonical_dossier_hash"] = canonical_hash(value)
    return value


def _request_core(
    manifest_relative_path: str,
    manifest_hash: str,
    *,
    request_id: str = "request-1",
    proposal_relative_path: str | None = None,
    proposal_sha256: str | None = None,
    decision_as_of: str = DECISION_AS_OF,
) -> dict:
    value = {
        "schema_version": "1.0",
        "request_id": request_id,
        "controlling_contract_id": MISSION_CONTRACT_ID,
        "controlling_contract_hash": MISSION_CONTRACT_HASH,
        "repository_commit": IMPLEMENTATION_COMMIT,
        "repository_clean": True,
        "observation_manifest_relative_path": manifest_relative_path,
        "observation_manifest_sha256": manifest_hash,
        "proposal_relative_path": proposal_relative_path,
        "proposal_sha256": proposal_sha256,
        "decision_as_of": decision_as_of,
        "requested_at": REQUESTED_AT,
        "requested_by": "OPERATOR",
    }
    value["canonical_request_hash"] = canonical_hash(value)
    return value


def _environment(
    tmp_path: Path, *, with_dossier: bool = False, busy_timeout_ms: int = 5000
) -> tuple[ResearchDirectorLedger, Path, Path, Path, dict]:
    _, source_path, _ = make_ledger(tmp_path / "mission94")
    result_root = tmp_path / "mission95-results"
    result_root.mkdir()
    mission97_parent = tmp_path / "mission97"
    mission97_parent.mkdir()
    workflow_ledger = WorkflowLedger.initialize(
        database_path=mission97_parent / "workflow.sqlite3",
        output_root=mission97_parent / "artifacts",
        governance_repository_root=ROOT,
        created_at=OBSERVATION_AS_OF,
    )
    orchestrator = WorkflowOrchestrator(workflow_ledger)
    run = orchestrator.create_run(
        run_key="mission98-observation",
        research_ledger_path=source_path,
        result_root=result_root,
        expected_repository_commit=IMPLEMENTATION_COMMIT,
        observation_as_of=OBSERVATION_AS_OF,
        requested_at=OBSERVATION_AS_OF,
        requested_by="LOCAL_OPERATOR",
    )
    final = None
    for index in range(1, 4):
        outcome = orchestrator.tick(
            "mission98-worker", f"2026-08-04T10:00:0{index}Z"
        )
        assert outcome.outcome is TickOutcome.STEP_SUCCEEDED
        final = outcome.run
    assert final is not None
    manifest_relative = final.artifact_identities[-1]["artifact_relative_path"]
    manifest_raw = (workflow_ledger.output_root / manifest_relative).read_bytes()

    input_root = tmp_path / "director-input"
    input_root.mkdir()
    proposal_path = None
    proposal_hash = None
    if with_dossier:
        proposal_path = "dossiers/proposal-1.json"
        dossier_raw = _canonical_write(
            input_root / proposal_path, _dossier_core()
        )
        proposal_hash = hashlib.sha256(dossier_raw).hexdigest()
    request = _request_core(
        manifest_relative,
        hashlib.sha256(manifest_raw).hexdigest(),
        proposal_relative_path=proposal_path,
        proposal_sha256=proposal_hash,
    )
    request_path = input_root / "requests" / "request-1.json"
    _canonical_write(request_path, request)
    database_parent = tmp_path / "director"
    database_parent.mkdir()
    ledger = ResearchDirectorLedger.initialize(
        database_path=database_parent / "director.sqlite3",
        observation_root=workflow_ledger.output_root,
        input_root=input_root,
        repository_root=ROOT,
        expected_repository_commit=IMPLEMENTATION_COMMIT,
        created_at=OBSERVATION_AS_OF,
        busy_timeout_ms=busy_timeout_ms,
    )
    return ledger, input_root, workflow_ledger.output_root, source_path, request


def _rewrite_request(input_root: Path, request: dict) -> None:
    core = dict(request)
    core.pop("canonical_request_hash", None)
    request["canonical_request_hash"] = canonical_hash(core)
    _canonical_write(
        input_root / "requests" / "request-1.json",
        request,
    )


def _rehash_manifest(manifest: dict) -> None:
    identity_core = dict(manifest)
    identity_core.pop("manifest_id", None)
    identity_core.pop("canonical_manifest_hash", None)
    manifest["manifest_id"] = (
        f"manifest-{canonical_hash(identity_core)[:32]}"
    )
    hash_core = dict(manifest)
    hash_core.pop("canonical_manifest_hash", None)
    manifest["canonical_manifest_hash"] = canonical_hash(hash_core)


def _rehash_snapshot(snapshot: dict) -> None:
    identity_system = dict(snapshot["system"])
    identity_system.pop("snapshot_id", None)
    identity_core = {
        "schema_version": snapshot["schema_version"],
        "snapshot_version": snapshot["snapshot_version"],
        "system": identity_system,
        "trials": snapshot["trials"],
        "results": snapshot["results"],
        "incidents": snapshot["incidents"],
    }
    snapshot_id = f"snapshot-{canonical_hash(identity_core)[:32]}"
    snapshot["snapshot_id"] = snapshot_id
    snapshot["system"]["snapshot_id"] = snapshot_id
    hash_core = dict(snapshot)
    hash_core.pop("canonical_snapshot_hash", None)
    snapshot["canonical_snapshot_hash"] = canonical_hash(hash_core)


def _manifest_fixture(
    input_root: Path,
    observation_root: Path,
    request: dict,
) -> tuple[Path, dict]:
    manifest_path = observation_root / request[
        "observation_manifest_relative_path"
    ]
    return manifest_path, json.loads(manifest_path.read_text())


def _rewrite_manifest_fixture(
    input_root: Path,
    observation_root: Path,
    request: dict,
    field: str,
    malformed_value,
) -> None:
    manifest_path, manifest = _manifest_fixture(
        input_root,
        observation_root,
        request,
    )
    manifest[field] = malformed_value
    _rehash_manifest(manifest)
    manifest_raw = _canonical_write(manifest_path, manifest)
    request["observation_manifest_sha256"] = hashlib.sha256(
        manifest_raw
    ).hexdigest()
    _rewrite_request(input_root, request)


def _rewrite_snapshot_fixture(
    input_root: Path,
    observation_root: Path,
    request: dict,
    mutation,
) -> None:
    manifest_path, manifest = _manifest_fixture(
        input_root,
        observation_root,
        request,
    )
    snapshot_path = (
        observation_root
        / "runs"
        / manifest["run_id"]
        / "CAPTURE_CONTROL_PLANE_SNAPSHOT"
        / "result.json"
    )
    snapshot = json.loads(snapshot_path.read_text())
    mutation(snapshot)
    _rehash_snapshot(snapshot)
    snapshot_raw = _canonical_write(snapshot_path, snapshot)
    manifest["source_snapshot_byte_hash"] = hashlib.sha256(
        snapshot_raw
    ).hexdigest()
    manifest["source_canonical_snapshot_hash"] = snapshot[
        "canonical_snapshot_hash"
    ]
    manifest["source_snapshot_id"] = snapshot["snapshot_id"]
    _rehash_manifest(manifest)
    manifest_raw = _canonical_write(manifest_path, manifest)
    request["observation_manifest_sha256"] = hashlib.sha256(
        manifest_raw
    ).hexdigest()
    _rewrite_request(input_root, request)


def _rewrite_dossier_fixture(
    input_root: Path,
    request: dict,
    field: str,
    malformed_value,
) -> None:
    dossier_path = input_root / request["proposal_relative_path"]
    dossier = json.loads(dossier_path.read_text())
    dossier[field] = malformed_value
    dossier_core = dict(dossier)
    dossier_core.pop("canonical_dossier_hash", None)
    dossier["canonical_dossier_hash"] = canonical_hash(dossier_core)
    dossier_raw = _canonical_write(dossier_path, dossier)
    request["proposal_sha256"] = hashlib.sha256(dossier_raw).hexdigest()
    _rewrite_request(input_root, request)


def _incident_with_enum(field: str, malformed_value) -> dict:
    core = {
        "severity": "WARNING",
        "category": "LEDGER_UNAVAILABLE",
        "reason_token": "TEST_INCIDENT",
        "human_explanation": "Test incident.",
        "trial_id": None,
        "detected_at": OBSERVATION_AS_OF,
        "evidence_identities": {},
    }
    core[field] = malformed_value
    incident_id = f"incident-{canonical_hash(core)[:32]}"
    identified = {"incident_id": incident_id, **core}
    return {
        **identified,
        "canonical_incident_hash": canonical_hash(identified),
    }


def _assert_service_failure(
    ledger: ResearchDirectorLedger,
    operation: str,
    reason: str,
) -> None:
    with pytest.raises(DirectorError) as caught:
        getattr(ResearchDirectorService(ledger), operation)(
            "requests/request-1.json"
        )
    assert caught.value.reason_token == reason
    with ledger._connection() as connection:
        assert [
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "director_requests",
                "director_decisions",
                "director_verifications",
            )
        ] == [0, 0, 0]


def _evidence(
    *,
    health: str = "HEALTHY",
    severities: tuple[str, ...] = (),
    observation_as_of: str = OBSERVATION_AS_OF,
) -> EvidenceView:
    return EvidenceView(
        manifest_byte_hash="4" * 64,
        snapshot_canonical_hash="5" * 64,
        observation_as_of=observation_as_of,
        health_token=health,
        incident_severities=severities,
        contract_identities=verify_contract_chain(ROOT),
        manifest_id="manifest-test",
        snapshot_id="snapshot-test",
        verification_id="verification-test",
    )


def _parsed_models(**dossier_changes):
    request_value = _request_core("runs/run/PUBLISH_OBSERVATION_MANIFEST/result.json", "4" * 64)
    request = DirectorRequest(request_value)
    dossier_value = _dossier_core(**dossier_changes)
    return request, ResearchOpportunityDossier(dossier_value, "6" * 64)


def test_contract_hash_authority_package_and_registry() -> None:
    value = _contract()
    core = dict(value)
    supplied = core.pop("contract_hash_sha256")
    assert canonical_hash(core) == supplied == MISSION_CONTRACT_HASH
    assert value["contract_id"] == MISSION_CONTRACT_ID
    assert value["contract_version"] == 1
    assert value["base_commit"] == "eab9ed19a2f77f31eb57daf5929aed479d43c540"
    assert value["preceding_contract"] == (
        "contracts/DELTAGRID_DURABLE_WORKFLOW_ORCHESTRATOR_V1.json"
    )
    assert value["preceding_contract_hash_sha256"] == (
        "c1840ed9f438f520401bbf24e501bb2a327f4718124745f275474ac76eeab272"
    )
    assert not any(value["authorization_state"].values())
    expected_files = {
        "__init__.py", "__main__.py", "action_registry.py", "evidence.py",
        "ledger.py", "models.py", "service.py", "verifier.py",
    }
    assert {path.name for path in PACKAGE.glob("*.py")} == expected_files
    assert tuple(item.action_id for item in ACTION_REGISTRY) == ACTION_IDS == (
        "STOP_NO_ADMISSIBLE_ACTION",
        "REQUEST_OBSERVATION_REFRESH",
        "REQUEST_MISSING_INTAKE_EVIDENCE",
        "REJECT_PROPOSAL_OVERLAP",
        "REJECT_POLICY_CONFLICT",
        "DRAFT_RESEARCH_REOPENING_CONTRACT",
        "QUEUE_FOUNDER_REVIEW",
    )
    assert all(item.recommendation_only for item in ACTION_REGISTRY)
    with pytest.raises(FrozenInstanceError):
        ACTION_REGISTRY[0].action_id = "changed"
    assert POLICY_OUTCOMES == (
        (
            "RULE_1_UPSTREAM_INTEGRITY_STOP",
            "STOP_NO_ADMISSIBLE_ACTION",
            "UPSTREAM_INTEGRITY_STOP",
        ),
        (
            "RULE_2_POLICY_CONFLICT",
            "REJECT_POLICY_CONFLICT",
            "PROPOSAL_REQUESTS_UNAUTHORIZED_STAGE",
        ),
        (
            "RULE_3_OBSERVATION_REFRESH",
            "REQUEST_OBSERVATION_REFRESH",
            "OBSERVATION_REFRESH_REQUIRED",
        ),
        (
            "RULE_4_NO_PROPOSAL",
            "STOP_NO_ADMISSIBLE_ACTION",
            "NO_PROPOSAL_SUPPLIED",
        ),
        (
            "RULE_5_MATERIAL_OVERLAP",
            "REJECT_PROPOSAL_OVERLAP",
            "REJECTED_FAMILY_OVERLAP",
        ),
        (
            "RULE_6_INTAKE_EVIDENCE_INCOMPLETE",
            "REQUEST_MISSING_INTAKE_EVIDENCE",
            "INTAKE_EVIDENCE_INCOMPLETE",
        ),
        (
            "RULE_7_DRAFT_CONTRACT_REQUIRED",
            "DRAFT_RESEARCH_REOPENING_CONTRACT",
            "NOVEL_PROPOSAL_REQUIRES_VERSIONED_CONTRACT",
        ),
        (
            "RULE_8_FOUNDER_REVIEW",
            "QUEUE_FOUNDER_REVIEW",
            "DRAFT_CONTRACT_REQUIRES_FOUNDER_REVIEW",
        ),
    )


def test_exact_supported_public_api_has_no_raw_persistence_boundary() -> None:
    assert director_api.__all__ == [
        "ACTION_IDS",
        "ACTION_REGISTRY",
        "WINNING_RULE_IDS",
        "MISSION_AUTHORIZATION_STAGE",
        "MISSION_BASE_COMMIT",
        "MISSION_CONTRACT_HASH",
        "MISSION_CONTRACT_ID",
        "DecisionPackage",
        "DirectorError",
        "ResearchDirectorLedger",
        "ResearchDirectorService",
    ]
    for name in (
        "DirectorRequest",
        "ResearchOpportunityDossier",
        "EvidenceView",
        "ResearchDecision",
        "VerificationReceipt",
        "ResearchDirectorEvidenceLoader",
        "ResearchDirectorVerifier",
    ):
        assert not hasattr(director_api, name)
    public_methods = {
        name
        for name, value in inspect.getmembers(
            ResearchDirectorLedger, predicate=callable
        )
        if not name.startswith("_")
    }
    assert public_methods == {
        "evidence_loader",
        "get_package",
        "initialize",
        "list_packages",
        "verify_full_ledger",
    }
    assert not hasattr(ResearchDirectorLedger, "record_package")
    signature = inspect.signature(
        ResearchDirectorLedger._record_verified_package
    )
    assert tuple(signature.parameters) == (
        "self",
        "request",
        "dossier",
        "evidence",
        "decision",
    )


def test_production_import_and_execution_boundary() -> None:
    allowed_external = {"offchain.research.admission"}
    forbidden_imports = {
        "subprocess", "socket", "requests", "aiohttp", "web3", "importlib"
    }
    forbidden_calls = {"eval", "exec", "compile", "__import__"}
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = (
                    node.names[0].name if isinstance(node, ast.Import)
                    else node.module or ""
                )
                assert module.split(".")[0] not in forbidden_imports
                if module.startswith("offchain.") and not module.startswith(
                    "offchain.research.director"
                ):
                    assert any(module.startswith(item) for item in allowed_external)
                if module.startswith("offchain."):
                    assert not any(
                        part.startswith("_") for part in module.split(".")
                    )
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_calls
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in PACKAGE.glob("*.py")
    )
    for token in (
        "os.system", "datetime.now", "time.time", "git ", "strategy.",
    ):
        assert token not in combined.lower()


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda raw: b"\xef\xbb\xbf" + raw, "DIRECTOR_INPUT_INVALID"),
        (
            lambda raw: raw.replace(
                b'"request_id":"request-1"',
                b'"request_id":"request-1","request_id":"duplicate"',
            ),
            "DIRECTOR_INPUT_INVALID",
        ),
        (lambda raw: raw[:-1] + b',"extra":1}', "DIRECTOR_INPUT_INVALID"),
        (lambda raw: raw.replace(b'"repository_clean":true', b'"repository_clean":1'), "DIRECTOR_INPUT_INVALID"),
        (lambda raw: raw.replace(b'"requested_by":"OPERATOR"', b'"requested_by":"UNKNOWN"'), "DIRECTOR_INPUT_INVALID"),
    ],
)
def test_strict_request_rejections(mutation, reason) -> None:
    value = _request_core("runs/run/PUBLISH_OBSERVATION_MANIFEST/result.json", "4" * 64)
    raw = canonical_json(value).encode()
    with pytest.raises(DirectorError) as caught:
        parse_request(mutation(raw), expected_commit=IMPLEMENTATION_COMMIT)
    assert caught.value.reason_token == reason


@pytest.mark.parametrize("operation", ("preview", "record"))
@pytest.mark.parametrize("malformed_value", ([], {}))
def test_request_enum_types_are_controlled(
    tmp_path: Path,
    operation: str,
    malformed_value,
) -> None:
    ledger, input_root, _, _, request = _environment(tmp_path)
    request["requested_by"] = malformed_value
    _rewrite_request(input_root, request)
    _assert_service_failure(
        ledger,
        operation,
        "DIRECTOR_INPUT_INVALID",
    )


@pytest.mark.parametrize(
    "path",
    (
        "/absolute/request.json",
        "../request.json",
        "./request.json",
        "requests/../request.json",
        "requests//request.json",
        "requests\\request.json",
    ),
)
def test_unsafe_request_paths(path: str) -> None:
    value = _request_core(path, "4" * 64)
    raw = canonical_json(value).encode()
    with pytest.raises(DirectorError) as caught:
        parse_request(raw, expected_commit=IMPLEMENTATION_COMMIT)
    assert caught.value.reason_token == "DIRECTOR_PATH_UNSAFE"


def test_exact_mission_97_manifest_path_is_accepted() -> None:
    value = _request_core(
        "runs/run-123/PUBLISH_OBSERVATION_MANIFEST/result.json",
        "4" * 64,
    )
    parsed = parse_request(
        canonical_json(value).encode(),
        expected_commit=IMPLEMENTATION_COMMIT,
    )
    assert (
        parsed.as_dict()["observation_manifest_relative_path"]
        == "runs/run-123/PUBLISH_OBSERVATION_MANIFEST/result.json"
    )


@pytest.mark.parametrize(
    "path",
    (
        "manifests/result.json",
        "runs/run-123/PUBLISH_OBSERVATION_MANIFEST",
        "runs/run-123/PUBLISH_OBSERVATION_MANIFEST/result.json/extra",
        "runs/run-123/VERIFY_CONTROL_PLANE_SNAPSHOT/result.json",
        "other/run-123/PUBLISH_OBSERVATION_MANIFEST/result.json",
        "runs/run-123/PUBLISH_OBSERVATION_MANIFEST/manifest.json",
    ),
)
def test_structurally_invalid_manifest_paths_fail_during_request_parsing(
    path: str,
) -> None:
    value = _request_core(path, "4" * 64)
    with pytest.raises(DirectorError) as caught:
        parse_request(
            canonical_json(value).encode(),
            expected_commit=IMPLEMENTATION_COMMIT,
        )
    assert caught.value.reason_token == "DIRECTOR_INPUT_INVALID"


def test_manifest_path_rejects_invalid_run_identifier() -> None:
    value = _request_core(
        "runs/run!invalid/PUBLISH_OBSERVATION_MANIFEST/result.json",
        "4" * 64,
    )
    with pytest.raises(DirectorError) as caught:
        parse_request(
            canonical_json(value).encode(),
            expected_commit=IMPLEMENTATION_COMMIT,
        )
    assert caught.value.reason_token == "DIRECTOR_INPUT_INVALID"


@pytest.mark.parametrize(
    ("changes", "expected_rule"),
    [
        ({"new_information_reference": None}, "RULE_6_INTAKE_EVIDENCE_INCOMPLETE"),
        ({"overlap_evidence_references": []}, "RULE_6_INTAKE_EVIDENCE_INCOMPLETE"),
        ({"economic_mechanism": ""}, "RULE_6_INTAKE_EVIDENCE_INCOMPLETE"),
        ({"falsifiable_claim": " \t "}, "RULE_6_INTAKE_EVIDENCE_INCOMPLETE"),
        ({"compared_rejected_family_ids": list(REJECTED_FAMILY_IDS[:2])}, "RULE_6_INTAKE_EVIDENCE_INCOMPLETE"),
        ({"overlap_audit_status": "MATERIAL_OVERLAP"}, "RULE_5_MATERIAL_OVERLAP"),
        ({"draft_reopening_contract_reference": {"contract_id": "draft-1", "reference_id": "draft-ref", "sha256": "7" * 64}}, "RULE_8_FOUNDER_REVIEW"),
    ],
)
def test_dossier_incomplete_overlap_and_founder_rules(changes, expected_rule) -> None:
    request, dossier = _parsed_models(**changes)
    selected = ResearchDirectorService._select_policy(
        request, dossier, _evidence()
    )
    assert selected[2] == expected_rule


@pytest.mark.parametrize(
    "stage",
    (
        "DEVELOPMENT_RESEARCH",
        "VALIDATION",
        "HOLDOUT",
        "PAPER_TRADING",
        "LIVE_TRADING",
        "CAPITAL_DEPLOYMENT",
    ),
)
def test_every_recognized_non_draft_stage_reaches_rule_2(stage: str) -> None:
    request, dossier = _parsed_models(requested_stage=stage)
    assert ResearchDirectorService._select_policy(
        request, dossier, _evidence()
    )[2] == "RULE_2_POLICY_CONFLICT"


@pytest.mark.parametrize("authority", REQUESTED_AUTHORITY_FIELDS)
def test_each_requested_authority_reaches_rule_2(authority: str) -> None:
    flags = {field: field == authority for field in REQUESTED_AUTHORITY_FIELDS}
    request, dossier = _parsed_models(requested_authorities=flags)
    assert ResearchDirectorService._select_policy(
        request, dossier, _evidence()
    )[2] == "RULE_2_POLICY_CONFLICT"


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value.pop("economic_mechanism"),
        lambda value: value.update(
            compared_rejected_family_ids=[
                REJECTED_FAMILY_IDS[1], REJECTED_FAMILY_IDS[0]
            ]
        ),
        lambda value: value.update(
            compared_rejected_family_ids=[
                REJECTED_FAMILY_IDS[0], REJECTED_FAMILY_IDS[0]
            ]
        ),
        lambda value: value.update(compared_rejected_family_ids=["UNKNOWN"]),
        lambda value: value.update(requested_stage="UNKNOWN"),
        lambda value: value.update(
            overlap_evidence_references=[
                {"reference_id": "same", "sha256": "1" * 64},
                {"reference_id": "same", "sha256": "2" * 64},
            ]
        ),
    ],
)
def test_dossier_structural_errors_are_not_policy_branches(mutator) -> None:
    value = _dossier_core()
    value.pop("canonical_dossier_hash")
    mutator(value)
    value["canonical_dossier_hash"] = canonical_hash(value)
    raw = canonical_json(value).encode()
    with pytest.raises(DirectorError) as caught:
        parse_dossier(
            raw,
            expected_byte_hash=hashlib.sha256(raw).hexdigest(),
            requested_at=REQUESTED_AT,
        )
    assert caught.value.reason_token == "DIRECTOR_INPUT_INVALID"


@pytest.mark.parametrize("operation", ("preview", "record"))
@pytest.mark.parametrize(
    ("field", "malformed_value"),
    tuple(
        (field, malformed_value)
        for field in (
            "new_information_type",
            "provenance_status",
            "causal_availability_status",
            "overlap_audit_status",
            "requested_stage",
        )
        for malformed_value in ([], {})
    ),
)
def test_dossier_enum_types_are_controlled(
    tmp_path: Path,
    operation: str,
    field: str,
    malformed_value,
) -> None:
    ledger, input_root, _, _, request = _environment(
        tmp_path,
        with_dossier=True,
    )
    _rewrite_dossier_fixture(
        input_root,
        request,
        field,
        malformed_value,
    )
    _assert_service_failure(
        ledger,
        operation,
        "DIRECTOR_INPUT_INVALID",
    )


def test_actual_mission_94_through_97_end_to_end_preview_and_record(
    tmp_path: Path,
) -> None:
    ledger, _, _, source_path, _ = _environment(tmp_path)
    before = source_path.read_bytes()
    service = ResearchDirectorService(ledger)
    preview = service.preview("requests/request-1.json")
    assert preview.decision.as_dict()["winning_rule_id"] == "RULE_4_NO_PROPOSAL"
    assert preview.verification_receipt.as_dict()["verification_token"] == "VERIFIED"
    assert preview.verification_receipt.as_dict()["verified_at"] == DECISION_AS_OF
    assert ledger.list_packages() == ()
    recorded = service.record("requests/request-1.json")
    assert recorded.as_dict() == preview.as_dict()
    assert service.record("requests/request-1.json").as_dict() == recorded.as_dict()
    assert source_path.read_bytes() == before
    assert len(ledger.list_packages()) == 1
    assert dict(ledger.verify_full_ledger())["decision_count"] == 1


def test_valid_external_tokens_hashes_and_ledger_remain_accepted(
    tmp_path: Path,
) -> None:
    ledger, _, _, _, _ = _environment(tmp_path, with_dossier=True)
    service = ResearchDirectorService(ledger)
    preview = service.preview("requests/request-1.json")
    recorded = service.record("requests/request-1.json")
    assert recorded.as_dict() == preview.as_dict()
    assert dict(ledger.verify_full_ledger())["decision_count"] == 1


def test_exact_replay_revalidates_current_external_evidence(
    tmp_path: Path,
) -> None:
    ledger, _, observation_root, _, request = _environment(tmp_path)
    service = ResearchDirectorService(ledger)
    recorded = service.record("requests/request-1.json")
    manifest = observation_root / request[
        "observation_manifest_relative_path"
    ]
    manifest.write_bytes(manifest.read_bytes() + b" ")
    with pytest.raises(DirectorError):
        service.record("requests/request-1.json")
    assert len(ledger.list_packages()) == 1
    assert (
        ledger.list_packages()[0].as_dict()
        == recorded.as_dict()
    )


def test_manifest_snapshot_and_verification_tampering_fail_closed(
    tmp_path: Path,
) -> None:
    ledger, input_root, observation_root, _, request = _environment(tmp_path)
    manifest = observation_root / request["observation_manifest_relative_path"]
    original_manifest = manifest.read_bytes()
    manifest.write_bytes(original_manifest + b" ")
    with pytest.raises(DirectorError):
        ResearchDirectorService(ledger).preview("requests/request-1.json")
    manifest.write_bytes(original_manifest)

    manifest_value = json.loads(original_manifest)
    snapshot = (
        observation_root
        / "runs"
        / manifest_value["run_id"]
        / "CAPTURE_CONTROL_PLANE_SNAPSHOT"
        / "result.json"
    )
    original_snapshot = snapshot.read_bytes()
    snapshot.write_bytes(original_snapshot.replace(b'"HEALTHY"', b'"DEGRADED"', 1))
    with pytest.raises(DirectorError) as caught:
        ResearchDirectorService(ledger).preview("requests/request-1.json")
    assert caught.value.reason_token == "OBSERVATION_EVIDENCE_INTEGRITY_FAILURE"
    snapshot.write_bytes(original_snapshot)

    verification = (
        observation_root
        / "runs"
        / manifest_value["run_id"]
        / "VERIFY_CONTROL_PLANE_SNAPSHOT"
        / "result.json"
    )
    verification.write_bytes(verification.read_bytes() + b" ")
    with pytest.raises(DirectorError):
        ResearchDirectorService(ledger).preview("requests/request-1.json")
    assert not ledger.list_packages()
    assert (input_root / "requests" / "request-1.json").is_file()


@pytest.mark.parametrize("operation", ("preview", "record"))
@pytest.mark.parametrize("malformed_value", ([], {}))
def test_manifest_health_enum_types_are_controlled(
    tmp_path: Path,
    operation: str,
    malformed_value,
) -> None:
    ledger, input_root, observation_root, _, request = _environment(
        tmp_path
    )
    _rewrite_manifest_fixture(
        input_root,
        observation_root,
        request,
        "system_health_token",
        malformed_value,
    )
    _assert_service_failure(
        ledger,
        operation,
        "OBSERVATION_EVIDENCE_INTEGRITY_FAILURE",
    )


@pytest.mark.parametrize("operation", ("preview", "record"))
@pytest.mark.parametrize("malformed_value", ([], {}))
@pytest.mark.parametrize(
    ("target", "field"),
    (
        ("system", "health_token"),
        ("incident", "severity"),
        ("incident", "category"),
    ),
)
def test_snapshot_enum_types_are_controlled(
    tmp_path: Path,
    operation: str,
    malformed_value,
    target: str,
    field: str,
) -> None:
    ledger, input_root, observation_root, _, request = _environment(
        tmp_path
    )

    def mutation(snapshot):
        if target == "system":
            snapshot["system"][field] = malformed_value
        else:
            snapshot["incidents"] = [
                _incident_with_enum(field, malformed_value)
            ]

    _rewrite_snapshot_fixture(
        input_root,
        observation_root,
        request,
        mutation,
    )
    _assert_service_failure(
        ledger,
        operation,
        "OBSERVATION_EVIDENCE_INTEGRITY_FAILURE",
    )


@pytest.mark.parametrize(
    "field",
    (
        "source_snapshot_byte_hash",
        "source_canonical_snapshot_hash",
        "verification_artifact_byte_hash",
    ),
)
@pytest.mark.parametrize(
    "malformed_value",
    ([], {}, 7, True, None),
)
def test_manifest_hash_storage_types_are_controlled(
    tmp_path: Path,
    field: str,
    malformed_value,
) -> None:
    ledger, input_root, observation_root, _, request = _environment(
        tmp_path
    )
    _rewrite_manifest_fixture(
        input_root,
        observation_root,
        request,
        field,
        malformed_value,
    )
    _assert_service_failure(
        ledger,
        "record",
        "OBSERVATION_EVIDENCE_INTEGRITY_FAILURE",
    )


@pytest.mark.parametrize(
    "field",
    ("ledger_path_identity", "result_root_path_identity"),
)
@pytest.mark.parametrize(
    "malformed_value",
    ([], {}, 7, True, None),
)
def test_snapshot_path_identity_types_are_controlled(
    tmp_path: Path,
    field: str,
    malformed_value,
) -> None:
    ledger, input_root, observation_root, _, request = _environment(
        tmp_path
    )

    def mutation(snapshot):
        snapshot["system"][field] = malformed_value

    _rewrite_snapshot_fixture(
        input_root,
        observation_root,
        request,
        mutation,
    )
    _assert_service_failure(
        ledger,
        "record",
        "OBSERVATION_EVIDENCE_INTEGRITY_FAILURE",
    )


def test_evidence_loader_never_opens_upstream_ledger_or_result_root(
    tmp_path: Path, monkeypatch
) -> None:
    ledger, _, _, source_path, _ = _environment(tmp_path)
    opened: list[Path] = []
    original_open = Path.open

    def tracking_open(path: Path, *args, **kwargs):
        opened.append(path)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)
    ResearchDirectorService(ledger).preview("requests/request-1.json")
    assert source_path not in opened
    assert not any("mission95-results" in str(path) for path in opened)


def test_all_eight_rules_and_precedence() -> None:
    request, dossier = _parsed_models()
    cases = [
        (_evidence(health="INTEGRITY_FAILURE"), dossier, "RULE_1_UPSTREAM_INTEGRITY_STOP"),
        (_evidence(severities=("ERROR",)), dossier, "RULE_1_UPSTREAM_INTEGRITY_STOP"),
        (_evidence(), _parsed_models(requested_stage="VALIDATION")[1], "RULE_2_POLICY_CONFLICT"),
        (_evidence(health="DEGRADED"), dossier, "RULE_3_OBSERVATION_REFRESH"),
        (_evidence(), None, "RULE_4_NO_PROPOSAL"),
        (_evidence(), _parsed_models(overlap_audit_status="MATERIAL_OVERLAP")[1], "RULE_5_MATERIAL_OVERLAP"),
        (_evidence(), _parsed_models(provenance_status="MISSING")[1], "RULE_6_INTAKE_EVIDENCE_INCOMPLETE"),
        (_evidence(), dossier, "RULE_7_DRAFT_CONTRACT_REQUIRED"),
        (_evidence(), _parsed_models(draft_reopening_contract_reference={"contract_id": "draft", "reference_id": "ref", "sha256": "7" * 64})[1], "RULE_8_FOUNDER_REVIEW"),
    ]
    for evidence, selected_dossier, expected in cases:
        assert ResearchDirectorService._select_policy(
            request, selected_dossier, evidence
        )[2] == expected
    conflict = _parsed_models(requested_stage="VALIDATION")[1]
    assert ResearchDirectorService._select_policy(
        request, conflict, _evidence(health="INTEGRITY_FAILURE")
    )[2] == "RULE_1_UPSTREAM_INTEGRITY_STOP"
    assert ResearchDirectorService._select_policy(
        request, conflict, _evidence(health="DEGRADED")
    )[2] == "RULE_2_POLICY_CONFLICT"


def test_freshness_boundary_and_clock_rules() -> None:
    request, _ = _parsed_models()
    fresh_value = request.as_dict()
    fresh_value["decision_as_of"] = "2026-08-05T10:00:00Z"
    fresh_value["canonical_request_hash"] = canonical_hash(
        {k: v for k, v in fresh_value.items() if k != "canonical_request_hash"}
    )
    assert ResearchDirectorService._select_policy(
        DirectorRequest(fresh_value), None, _evidence()
    )[2] == "RULE_4_NO_PROPOSAL"
    stale_value = dict(fresh_value)
    stale_value["decision_as_of"] = "2026-08-05T10:00:01Z"
    stale_value["canonical_request_hash"] = canonical_hash(
        {k: v for k, v in stale_value.items() if k != "canonical_request_hash"}
    )
    assert ResearchDirectorService._select_policy(
        DirectorRequest(stale_value), None, _evidence()
    )[2] == "RULE_3_OBSERVATION_REFRESH"


def test_decision_determinism_and_independent_verifier_rejects_mutation(
    tmp_path: Path,
) -> None:
    ledger, _, _, _, _ = _environment(tmp_path, with_dossier=True)
    loader = ledger.evidence_loader()
    request, dossier = loader.load_request("requests/request-1.json")
    evidence = loader.verify(request)
    action, reason, rule = ResearchDirectorService._select_policy(
        request, dossier, evidence
    )
    first = ResearchDirectorService._build_decision(
        request, dossier, evidence, action, reason, rule
    )
    second = ResearchDirectorService._build_decision(
        request, dossier, evidence, action, reason, rule
    )
    assert canonical_json(first.as_dict()) == canonical_json(second.as_dict())
    verifier = ResearchDirectorVerifier()
    receipt = verifier.verify(
        request=request, dossier=dossier, evidence=evidence, decision=first
    )
    assert receipt.as_dict()["verified_at"] == first.as_dict()["decision_as_of"]
    for field, changed in (
        ("selected_action_id", "STOP_NO_ADMISSIBLE_ACTION"),
        ("reason_token", "NO_PROPOSAL_SUPPLIED"),
        ("winning_rule_id", "RULE_4_NO_PROPOSAL"),
        ("decision_id", "decision-bad"),
        ("human_explanation", "caller supplied"),
        ("canonical_decision_hash", "0" * 64),
    ):
        altered = first.as_dict()
        altered[field] = changed
        with pytest.raises(DirectorError):
            verifier.verify(
                request=request,
                dossier=dossier,
                evidence=evidence,
                decision=ResearchDecision(altered),
            )
    assert "preview" not in ast.unparse(
        ast.parse((PACKAGE / "verifier.py").read_text())
    )
    assert "record" not in ast.unparse(
        ast.parse((PACKAGE / "verifier.py").read_text())
    )


def test_private_persistence_verifies_before_opening_mutation(
    tmp_path: Path, monkeypatch
) -> None:
    ledger, _, _, _, _ = _environment(tmp_path)
    request, dossier, evidence, decision = ResearchDirectorService(
        ledger
    )._evaluate("requests/request-1.json")
    mutation_opened = False

    def reject(*args, **kwargs):
        raise DirectorError("DECISION_INTEGRITY_FAILURE")

    def forbidden_mutation():
        nonlocal mutation_opened
        mutation_opened = True
        raise AssertionError("mutation opened before verifier succeeded")

    monkeypatch.setattr(ResearchDirectorVerifier, "verify", reject)
    monkeypatch.setattr(ledger, "_mutation", forbidden_mutation)
    with pytest.raises(DirectorError) as caught:
        ledger._record_verified_package(
            request=request,
            dossier=dossier,
            evidence=evidence,
            decision=decision,
        )
    assert caught.value.reason_token == "DECISION_INTEGRITY_FAILURE"
    assert mutation_opened is False
    with ledger._connection() as connection:
        assert [
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "director_requests",
                "director_decisions",
                "director_verifications",
            )
        ] == [0, 0, 0]


def test_ledger_binding_schema_immutability_and_conflicts(tmp_path: Path) -> None:
    ledger, _, _, _, _ = _environment(tmp_path)
    matching = ResearchDirectorLedger.initialize(
        database_path=ledger.database_path,
        observation_root=ledger.metadata["observation_root"],
        input_root=ledger.metadata["input_root"],
        repository_root=ROOT,
        expected_repository_commit=IMPLEMENTATION_COMMIT,
        created_at=OBSERVATION_AS_OF,
    )
    assert dict(matching.metadata) == dict(ledger.metadata)
    with pytest.raises(DirectorError):
        ResearchDirectorLedger.initialize(
            database_path=ledger.database_path,
            observation_root=ledger.metadata["observation_root"],
            input_root=ledger.metadata["input_root"],
            repository_root=ROOT,
            expected_repository_commit="2" * 40,
            created_at=OBSERVATION_AS_OF,
        )
    with ledger._connection() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 3
        triggers = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        }
        assert len(triggers) == 8
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE director_metadata SET created_at='changed'"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM director_metadata")


def test_untouched_exact_schema_inventory_verifies(tmp_path: Path) -> None:
    ledger, _, _, _, _ = _environment(tmp_path)
    assert dict(ledger.verify_full_ledger())["status"] == "LEDGER_VERIFIED"


@pytest.mark.parametrize(
    "mutation_sql",
    (
        """
        DROP TRIGGER director_requests_no_update;
        CREATE TRIGGER director_requests_no_update
        BEFORE UPDATE ON director_requests BEGIN SELECT 1; END;
        """,
        """
        DROP TRIGGER director_requests_no_update;
        CREATE TRIGGER director_requests_no_update
        BEFORE UPDATE ON director_requests
        BEGIN SELECT RAISE(ABORT, 'different'); END;
        """,
        """
        DROP TRIGGER director_requests_no_update;
        CREATE TRIGGER director_requests_no_update
        BEFORE UPDATE ON director_decisions
        BEGIN SELECT RAISE(ABORT, 'immutable'); END;
        """,
        """
        DROP INDEX director_requests_hash_idx;
        CREATE UNIQUE INDEX director_requests_hash_idx
        ON director_requests(request_id);
        """,
        """
        DROP INDEX director_requests_hash_idx;
        CREATE INDEX director_requests_hash_idx
        ON director_requests(canonical_request_hash);
        """,
        """
        DROP INDEX director_requests_hash_idx;
        CREATE UNIQUE INDEX director_requests_hash_idx
        ON director_requests(canonical_request_hash)
        WHERE request_id <> '';
        """,
        """
        DROP INDEX director_requests_hash_idx;
        CREATE UNIQUE INDEX director_requests_hash_idx
        ON director_requests(lower(canonical_request_hash));
        """,
    ),
)
def test_exact_schema_inventory_rejects_same_named_definition_mutations(
    tmp_path: Path, mutation_sql: str
) -> None:
    ledger, _, _, _, _ = _environment(tmp_path)
    connection = sqlite3.connect(str(ledger.database_path))
    try:
        connection.executescript(mutation_sql)
    finally:
        connection.close()
    with pytest.raises(DirectorError) as caught:
        ledger.verify_full_ledger()
    assert caught.value.reason_token == "DIRECTOR_SCHEMA_INCOMPATIBLE"


def test_current_ledger_rejects_rehashed_metadata_mutation(
    tmp_path: Path,
) -> None:
    ledger, _, _, _, _ = _environment(tmp_path)
    altered = dict(ledger.metadata)
    altered.pop("canonical_metadata_hash")
    altered["created_at"] = "2026-08-04T09:59:59Z"
    altered_hash = canonical_hash(altered)
    connection = sqlite3.connect(str(ledger.database_path))
    try:
        connection.executescript(
            """
            DROP TRIGGER director_metadata_no_update;
            """
        )
        connection.execute(
            "UPDATE director_metadata SET created_at=?, "
            "canonical_metadata_hash=?",
            (altered["created_at"], altered_hash),
        )
        connection.executescript(
            """
CREATE TRIGGER director_metadata_no_update BEFORE UPDATE ON director_metadata
 BEGIN SELECT RAISE(ABORT, 'immutable'); END;
            """
        )
        connection.commit()
    finally:
        connection.close()
    with ledger._connection() as verified_connection:
        ledger._verify_schema(verified_connection)
    with pytest.raises(DirectorError) as caught:
        ledger.verify_full_ledger()
    assert caught.value.reason_token == "DIRECTOR_ROW_INTEGRITY_FAILURE"


def _corrupt_immutable_row(
    ledger: ResearchDirectorLedger,
    *,
    table: str,
    column: str,
    malformed_value,
) -> None:
    trigger = f"{table}_no_update"
    connection = sqlite3.connect(str(ledger.database_path))
    try:
        trigger_sql = connection.execute(
            "SELECT sql FROM sqlite_schema "
            "WHERE type='trigger' AND name=?",
            (trigger,),
        ).fetchone()[0]
        connection.execute(f'DROP TRIGGER "{trigger}"')
        connection.execute(
            f'UPDATE "{table}" SET "{column}"=?',
            (malformed_value,),
        )
        connection.execute(trigger_sql)
        connection.commit()
    finally:
        connection.close()


def test_blob_metadata_corruption_is_normalized_for_api_and_cli(
    tmp_path: Path, capsys
) -> None:
    from offchain.research.director.__main__ import main

    ledger, _, _, _, _ = _environment(tmp_path)
    _corrupt_immutable_row(
        ledger,
        table="director_metadata",
        column="repository_root",
        malformed_value=sqlite3.Binary(b"corrupt"),
    )
    with pytest.raises(DirectorError) as caught:
        ledger.verify_full_ledger()
    assert caught.value.reason_token == "DIRECTOR_ROW_INTEGRITY_FAILURE"
    with pytest.raises(DirectorError) as caught:
        ResearchDirectorLedger(ledger.database_path)
    assert caught.value.reason_token == "DIRECTOR_ROW_INTEGRITY_FAILURE"
    assert main(
        ["status", "--database", str(ledger.database_path)]
    ) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("\n") == 1
    failure = json.loads(captured.err)
    assert failure["reason_token"] == "DIRECTOR_ROW_INTEGRITY_FAILURE"
    assert canonical_json(failure) + "\n" == captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    ("table", "column"),
    (
        ("director_requests", "canonical_request_hash"),
        ("director_decisions", "canonical_decision_hash"),
        (
            "director_verifications",
            "canonical_verification_hash",
        ),
    ),
)
def test_blob_package_row_corruption_is_normalized_for_every_reader(
    tmp_path: Path,
    table: str,
    column: str,
) -> None:
    ledger, _, _, _, _ = _environment(tmp_path)
    package = ResearchDirectorService(ledger).record(
        "requests/request-1.json"
    )
    decision_id = package.decision.as_dict()["decision_id"]
    _corrupt_immutable_row(
        ledger,
        table=table,
        column=column,
        malformed_value=sqlite3.Binary(b"corrupt"),
    )
    readers = (
        lambda: ledger.get_package(decision_id),
        ledger.list_packages,
        ledger.verify_full_ledger,
    )
    for reader in readers:
        with pytest.raises(DirectorError) as caught:
            reader()
        assert (
            caught.value.reason_token
            == "DIRECTOR_ROW_INTEGRITY_FAILURE"
        )


def test_record_atomicity_row_tampering_and_missing_package(
    tmp_path: Path, monkeypatch
) -> None:
    ledger, _, _, _, _ = _environment(tmp_path)
    service = ResearchDirectorService(ledger)
    original_insert = ledger._insert

    def fail_on_decision(connection, table, value):
        if table == "director_decisions":
            raise sqlite3.OperationalError("injected")
        return original_insert(connection, table, value)

    monkeypatch.setattr(ledger, "_insert", fail_on_decision)
    with pytest.raises(sqlite3.OperationalError):
        service.record("requests/request-1.json")
    with ledger._connection() as connection:
        assert all(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            for table in (
                "director_requests", "director_decisions",
                "director_verifications",
            )
        )
    monkeypatch.setattr(ledger, "_insert", original_insert)
    package = service.record("requests/request-1.json")
    with pytest.raises(DirectorError) as caught:
        ledger.get_package("decision-" + "0" * 32)
    assert caught.value.reason_token == "DECISION_NOT_FOUND"
    with ledger._connection() as connection:
        connection.execute("DROP TRIGGER director_decisions_no_update")
        connection.execute(
            "UPDATE director_decisions SET canonical_row_hash=? WHERE decision_id=?",
            ("0" * 64, package.decision.as_dict()["decision_id"]),
        )
    with pytest.raises(DirectorError):
        ledger.verify_full_ledger()


def _rehash_decision(value: dict) -> dict:
    core = dict(value)
    core.pop("decision_id", None)
    core.pop("canonical_decision_hash", None)
    decision_id = f"decision-{canonical_hash(core)[:32]}"
    identified = {
        "schema_version": core.pop("schema_version"),
        "decision_id": decision_id,
        **core,
    }
    return {
        **identified,
        "canonical_decision_hash": canonical_hash(identified),
    }


def _rehash_receipt(value: dict) -> dict:
    core = dict(value)
    core.pop("verification_id", None)
    core.pop("canonical_verification_hash", None)
    verification_id = f"verification-{canonical_hash(core)[:32]}"
    identified = {
        "schema_version": core.pop("schema_version"),
        "verification_id": verification_id,
        **core,
    }
    return {
        **identified,
        "canonical_verification_hash": canonical_hash(identified),
    }


def _inject_hash_consistent_package(
    ledger: ResearchDirectorLedger,
    package: DecisionPackage,
    *,
    decision_changes: dict | None = None,
    receipt_changes: dict | None = None,
    forced_decision_id: str | None = None,
) -> str:
    original_decision_id = package.decision.as_dict()["decision_id"]
    decision = package.decision.as_dict()
    decision.update(decision_changes or {})
    decision = _rehash_decision(decision)
    if forced_decision_id is not None:
        decision["decision_id"] = forced_decision_id
        identified = dict(decision)
        identified.pop("canonical_decision_hash")
        decision["canonical_decision_hash"] = canonical_hash(identified)
    receipt = package.verification_receipt.as_dict()
    receipt.update(
        {
            "decision_id": decision["decision_id"],
            "decision_hash": decision["canonical_decision_hash"],
            "independently_recomputed_action_id": decision[
                "selected_action_id"
            ],
            "independently_recomputed_reason_token": decision[
                "reason_token"
            ],
            "independently_recomputed_rule_id": decision[
                "winning_rule_id"
            ],
        }
    )
    receipt.update(receipt_changes or {})
    receipt = _rehash_receipt(receipt)
    decision_row = ledger._decision_row(ResearchDecision(decision))
    verification_row = ledger._verification_row(
        VerificationReceipt(receipt)
    )
    connection = sqlite3.connect(str(ledger.database_path))
    try:
        connection.execute("DROP TRIGGER director_decisions_no_update")
        connection.execute(
            "DROP TRIGGER director_verifications_no_update"
        )
        connection.execute(
            "UPDATE director_decisions SET decision_id=?, request_id=?, "
            "canonical_decision_json=?, canonical_decision_hash=?, "
            "canonical_row_hash=? WHERE decision_id=?",
            (*decision_row.values(), original_decision_id),
        )
        connection.execute(
            "UPDATE director_verifications SET verification_id=?, "
            "decision_id=?, canonical_verification_json=?, "
            "canonical_verification_hash=?, canonical_row_hash=? "
            "WHERE decision_id=?",
            (*verification_row.values(), original_decision_id),
        )
        connection.commit()
    finally:
        connection.close()
    return decision["decision_id"]


def _policy_decision_changes(
    rule: str,
    *,
    observation_as_of: str | None = None,
) -> dict:
    action, reason = next(
        (action, reason)
        for registered_rule, action, reason in POLICY_OUTCOMES
        if registered_rule == rule
    )
    changes = {
        "selected_action_id": action,
        "reason_token": reason,
        "winning_rule_id": rule,
        "human_explanation": EXPLANATIONS[(action, reason)],
    }
    if observation_as_of is not None:
        changes["observation_as_of"] = observation_as_of
    return changes


def test_valid_stored_observation_snapshot_hash_is_accepted(
    tmp_path: Path,
) -> None:
    ledger, _, _, _, _ = _environment(tmp_path)
    package = ResearchDirectorService(ledger).record(
        "requests/request-1.json"
    )
    assert (
        ledger.get_package(
            package.decision.as_dict()["decision_id"]
        ).as_dict()
        == package.as_dict()
    )


@pytest.mark.parametrize(
    "snapshot_hash",
    (
        "a" * 63,
        "A" * 64,
        True,
        64,
    ),
)
def test_invalid_stored_observation_snapshot_hash_is_rejected(
    tmp_path: Path, snapshot_hash
) -> None:
    ledger, _, _, _, _ = _environment(tmp_path)
    package = ResearchDirectorService(ledger).record(
        "requests/request-1.json"
    )
    decision_id = _inject_hash_consistent_package(
        ledger,
        package,
        decision_changes={
            "observation_snapshot_canonical_hash": snapshot_hash
        },
    )
    with pytest.raises(DirectorError) as caught:
        ledger.get_package(decision_id)
    assert caught.value.reason_token == "DIRECTOR_ROW_INTEGRITY_FAILURE"


@pytest.mark.parametrize(
    "observation_as_of",
    (
        "not-a-timestamp",
        True,
        "2026-08-04T10:00:03.1Z",
        "2026-08-04T10:00:05Z",
    ),
)
def test_invalid_stored_observation_timestamp_is_rejected(
    tmp_path: Path, observation_as_of
) -> None:
    ledger, _, _, _, _ = _environment(tmp_path)
    package = ResearchDirectorService(ledger).record(
        "requests/request-1.json"
    )
    decision_id = _inject_hash_consistent_package(
        ledger,
        package,
        decision_changes={"observation_as_of": observation_as_of},
    )
    with pytest.raises(DirectorError) as caught:
        ledger.get_package(decision_id)
    assert caught.value.reason_token == "DIRECTOR_ROW_INTEGRITY_FAILURE"


@pytest.mark.parametrize(
    "rule",
    (
        "RULE_2_POLICY_CONFLICT",
        "RULE_5_MATERIAL_OVERLAP",
        "RULE_6_INTAKE_EVIDENCE_INCOMPLETE",
        "RULE_7_DRAFT_CONTRACT_REQUIRED",
        "RULE_8_FOUNDER_REVIEW",
    ),
)
def test_no_proposal_rejects_incompatible_hash_consistent_rules(
    tmp_path: Path, rule: str
) -> None:
    ledger, _, _, _, _ = _environment(tmp_path)
    package = ResearchDirectorService(ledger).record(
        "requests/request-1.json"
    )
    decision_id = _inject_hash_consistent_package(
        ledger,
        package,
        decision_changes=_policy_decision_changes(rule),
    )
    with pytest.raises(DirectorError) as caught:
        ledger.get_package(decision_id)
    assert caught.value.reason_token == "DIRECTOR_ROW_INTEGRITY_FAILURE"


def test_proposal_rejects_hash_consistent_no_proposal_rule(
    tmp_path: Path,
) -> None:
    ledger, _, _, _, _ = _environment(tmp_path, with_dossier=True)
    package = ResearchDirectorService(ledger).record(
        "requests/request-1.json"
    )
    decision_id = _inject_hash_consistent_package(
        ledger,
        package,
        decision_changes=_policy_decision_changes(
            "RULE_4_NO_PROPOSAL"
        ),
    )
    with pytest.raises(DirectorError) as caught:
        ledger.get_package(decision_id)
    assert caught.value.reason_token == "DIRECTOR_ROW_INTEGRITY_FAILURE"


@pytest.mark.parametrize(
    "rule",
    (
        "RULE_1_UPSTREAM_INTEGRITY_STOP",
        "RULE_3_OBSERVATION_REFRESH",
        "RULE_4_NO_PROPOSAL",
    ),
)
def test_no_proposal_accepts_every_structurally_possible_rule(
    tmp_path: Path, rule: str
) -> None:
    ledger, _, _, _, _ = _environment(tmp_path)
    package = ResearchDirectorService(ledger).record(
        "requests/request-1.json"
    )
    decision_id = _inject_hash_consistent_package(
        ledger,
        package,
        decision_changes=_policy_decision_changes(rule),
    )
    assert ledger.get_package(decision_id).decision.as_dict()[
        "winning_rule_id"
    ] == rule


@pytest.mark.parametrize(
    "rule",
    (
        "RULE_1_UPSTREAM_INTEGRITY_STOP",
        "RULE_2_POLICY_CONFLICT",
        "RULE_3_OBSERVATION_REFRESH",
        "RULE_5_MATERIAL_OVERLAP",
        "RULE_6_INTAKE_EVIDENCE_INCOMPLETE",
        "RULE_7_DRAFT_CONTRACT_REQUIRED",
        "RULE_8_FOUNDER_REVIEW",
    ),
)
def test_proposal_accepts_every_structurally_possible_rule(
    tmp_path: Path, rule: str
) -> None:
    ledger, _, _, _, _ = _environment(tmp_path, with_dossier=True)
    package = ResearchDirectorService(ledger).record(
        "requests/request-1.json"
    )
    decision_id = _inject_hash_consistent_package(
        ledger,
        package,
        decision_changes=_policy_decision_changes(rule),
    )
    assert ledger.get_package(decision_id).decision.as_dict()[
        "winning_rule_id"
    ] == rule


@pytest.mark.parametrize(
    "rule",
    (
        "RULE_4_NO_PROPOSAL",
        "RULE_5_MATERIAL_OVERLAP",
        "RULE_6_INTAKE_EVIDENCE_INCOMPLETE",
        "RULE_7_DRAFT_CONTRACT_REQUIRED",
        "RULE_8_FOUNDER_REVIEW",
    ),
)
def test_lower_precedence_rules_accept_exact_freshness_boundary(
    tmp_path: Path, rule: str
) -> None:
    with_dossier = rule != "RULE_4_NO_PROPOSAL"
    ledger, _, _, _, _ = _environment(
        tmp_path,
        with_dossier=with_dossier,
    )
    package = ResearchDirectorService(ledger).record(
        "requests/request-1.json"
    )
    changes = _policy_decision_changes(
        rule,
        observation_as_of="2026-08-03T10:00:04Z",
    )
    decision_id = _inject_hash_consistent_package(
        ledger,
        package,
        decision_changes=changes,
    )
    assert ledger.get_package(decision_id).decision.as_dict()[
        "winning_rule_id"
    ] == rule


@pytest.mark.parametrize(
    "rule",
    (
        "RULE_4_NO_PROPOSAL",
        "RULE_5_MATERIAL_OVERLAP",
        "RULE_6_INTAKE_EVIDENCE_INCOMPLETE",
        "RULE_7_DRAFT_CONTRACT_REQUIRED",
        "RULE_8_FOUNDER_REVIEW",
    ),
)
def test_lower_precedence_rules_reject_stale_observation(
    tmp_path: Path, rule: str
) -> None:
    with_dossier = rule != "RULE_4_NO_PROPOSAL"
    ledger, _, _, _, _ = _environment(
        tmp_path,
        with_dossier=with_dossier,
    )
    package = ResearchDirectorService(ledger).record(
        "requests/request-1.json"
    )
    changes = _policy_decision_changes(
        rule,
        observation_as_of="2026-08-03T10:00:03Z",
    )
    decision_id = _inject_hash_consistent_package(
        ledger,
        package,
        decision_changes=changes,
    )
    with pytest.raises(DirectorError) as caught:
        ledger.get_package(decision_id)
    assert caught.value.reason_token == "DIRECTOR_ROW_INTEGRITY_FAILURE"


@pytest.mark.parametrize(
    "rule",
    (
        "RULE_1_UPSTREAM_INTEGRITY_STOP",
        "RULE_2_POLICY_CONFLICT",
        "RULE_3_OBSERVATION_REFRESH",
    ),
)
def test_higher_precedence_rules_allow_stale_observation(
    tmp_path: Path, rule: str
) -> None:
    with_dossier = rule == "RULE_2_POLICY_CONFLICT"
    ledger, _, _, _, _ = _environment(
        tmp_path,
        with_dossier=with_dossier,
    )
    package = ResearchDirectorService(ledger).record(
        "requests/request-1.json"
    )
    changes = _policy_decision_changes(
        rule,
        observation_as_of="2026-08-01T10:00:00Z",
    )
    decision_id = _inject_hash_consistent_package(
        ledger,
        package,
        decision_changes=changes,
    )
    assert ledger.get_package(decision_id).decision.as_dict()[
        "winning_rule_id"
    ] == rule


def test_public_lookup_accepts_deterministic_decision_identifier(
    tmp_path: Path,
) -> None:
    ledger, _, _, _, _ = _environment(tmp_path)
    package = ResearchDirectorService(ledger).record(
        "requests/request-1.json"
    )
    decision_id = package.decision.as_dict()["decision_id"]
    assert ledger.get_package(decision_id).as_dict() == package.as_dict()


@pytest.mark.parametrize(
    "decision_id",
    (
        "",
        "decision-bad",
        "decision-" + "A" * 32,
        "decision-" + "a" * 33,
        "arbitrary",
        None,
        True,
        7,
    ),
)
def test_public_lookup_rejects_invalid_decision_identifier(
    tmp_path: Path, decision_id
) -> None:
    ledger, _, _, _, _ = _environment(tmp_path)
    with pytest.raises(DirectorError) as caught:
        ledger.get_package(decision_id)
    assert caught.value.reason_token == "DIRECTOR_INPUT_INVALID"


def test_cli_status_invalid_decision_identifier_is_controlled_json(
    tmp_path: Path, capsys
) -> None:
    from offchain.research.director.__main__ import main

    ledger, _, _, _, _ = _environment(tmp_path)
    assert main(
        [
            "status",
            "--database",
            str(ledger.database_path),
            "--decision-id",
            "decision-invalid",
        ]
    ) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("\n") == 1
    failure = json.loads(captured.err)
    assert failure["reason_token"] == "DIRECTOR_INPUT_INVALID"
    assert canonical_json(failure) + "\n" == captured.err
    assert "Traceback" not in captured.err


def test_malformed_stored_decision_identifier_is_row_integrity_failure(
    tmp_path: Path,
) -> None:
    ledger, _, _, _, _ = _environment(tmp_path)
    package = ResearchDirectorService(ledger).record(
        "requests/request-1.json"
    )
    _inject_hash_consistent_package(
        ledger,
        package,
        forced_decision_id="decision-malformed",
    )
    with pytest.raises(DirectorError) as caught:
        ledger.list_packages()
    assert caught.value.reason_token == "DIRECTOR_ROW_INTEGRITY_FAILURE"


@pytest.mark.parametrize(
    "decision_changes",
    (
        {"reason_token": "FABRICATED_REASON"},
        {"winning_rule_id": "RULE_0_FABRICATED"},
        {
            "selected_action_id": "QUEUE_FOUNDER_REVIEW",
            "reason_token": "NO_PROPOSAL_SUPPLIED",
            "winning_rule_id": "RULE_4_NO_PROPOSAL",
        },
        {"human_explanation": "Fabricated explanation."},
        {"repository_commit": "2" * 40},
    ),
)
def test_hash_consistent_semantic_decision_fabrication_is_rejected(
    tmp_path: Path, decision_changes: dict
) -> None:
    ledger, _, _, _, _ = _environment(tmp_path)
    package = ResearchDirectorService(ledger).record(
        "requests/request-1.json"
    )
    decision_id = _inject_hash_consistent_package(
        ledger,
        package,
        decision_changes=decision_changes,
    )
    with pytest.raises(DirectorError) as caught:
        ledger.get_package(decision_id)
    assert caught.value.reason_token == "DIRECTOR_ROW_INTEGRITY_FAILURE"


@pytest.mark.parametrize(
    "field",
    tuple(
        f"mission_{mission}_contract_{kind}"
        for mission in ("93", "94", "95", "96a", "96b", "97", "98")
        for kind in ("id", "hash")
    ),
)
def test_every_compiled_contract_identity_is_enforced(
    tmp_path: Path, field: str
) -> None:
    ledger, _, _, _, _ = _environment(tmp_path)
    package = ResearchDirectorService(ledger).record(
        "requests/request-1.json"
    )
    replacement = "fabricated-contract" if field.endswith("_id") else "0" * 64
    decision_id = _inject_hash_consistent_package(
        ledger,
        package,
        decision_changes={field: replacement},
    )
    with pytest.raises(DirectorError) as caught:
        ledger.get_package(decision_id)
    assert caught.value.reason_token == "DIRECTOR_ROW_INTEGRITY_FAILURE"


@pytest.mark.parametrize(
    "receipt_changes",
    (
        {"verifier_version": 2},
        {"verifier_version": True},
        {"verified_at": "2026-08-04T10:00:05Z"},
    ),
)
def test_hash_consistent_receipt_semantic_fabrication_is_rejected(
    tmp_path: Path, receipt_changes: dict
) -> None:
    ledger, _, _, _, _ = _environment(tmp_path)
    package = ResearchDirectorService(ledger).record(
        "requests/request-1.json"
    )
    decision_id = _inject_hash_consistent_package(
        ledger,
        package,
        receipt_changes=receipt_changes,
    )
    with pytest.raises(DirectorError) as caught:
        ledger.get_package(decision_id)
    assert caught.value.reason_token == "DIRECTOR_ROW_INTEGRITY_FAILURE"


def test_supported_record_rejects_fabricated_decision_without_partial_rows(
    tmp_path: Path, monkeypatch
) -> None:
    ledger, _, _, _, _ = _environment(tmp_path)
    service = ResearchDirectorService(ledger)
    original = service._build_decision

    def fabricated(*args, **kwargs):
        value = original(*args, **kwargs).as_dict()
        value["reason_token"] = "FABRICATED_REASON"
        return ResearchDecision(_rehash_decision(value))

    monkeypatch.setattr(service, "_build_decision", fabricated)
    with pytest.raises(DirectorError) as caught:
        service.record("requests/request-1.json")
    assert caught.value.reason_token == "DECISION_INTEGRITY_FAILURE"
    with ledger._connection() as connection:
        assert [
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "director_requests",
                "director_decisions",
                "director_verifications",
            )
        ] == [0, 0, 0]


def _direct_prior_rows(package: DecisionPackage, count: int):
    request_base = package.request.as_dict()
    decision_base = package.decision.as_dict()
    receipt_base = package.verification_receipt.as_dict()
    requests = []
    decisions = []
    receipts = []
    for index in range(count):
        request = dict(request_base)
        request["request_id"] = f"prior-{index:05d}"
        request_core = dict(request)
        request_core.pop("canonical_request_hash")
        request["canonical_request_hash"] = canonical_hash(request_core)
        request_json = canonical_json(request)
        request_row = {
            "request_id": request["request_id"],
            "canonical_request_json": request_json,
            "canonical_request_hash": request["canonical_request_hash"],
        }
        requests.append((*request_row.values(), canonical_hash(request_row)))

        decision = dict(decision_base)
        decision["request_id"] = request["request_id"]
        decision_core = dict(decision)
        decision_core.pop("decision_id")
        decision_core.pop("canonical_decision_hash")
        decision["decision_id"] = f"decision-{canonical_hash(decision_core)[:32]}"
        decision_identified = dict(decision)
        decision_identified.pop("canonical_decision_hash")
        decision["canonical_decision_hash"] = canonical_hash(decision_identified)
        decision_json = canonical_json(decision)
        decision_row = {
            "decision_id": decision["decision_id"],
            "request_id": request["request_id"],
            "canonical_decision_json": decision_json,
            "canonical_decision_hash": decision["canonical_decision_hash"],
        }
        decisions.append((*decision_row.values(), canonical_hash(decision_row)))

        receipt = dict(receipt_base)
        receipt["decision_id"] = decision["decision_id"]
        receipt["decision_hash"] = decision["canonical_decision_hash"]
        receipt_core = dict(receipt)
        receipt_core.pop("verification_id")
        receipt_core.pop("canonical_verification_hash")
        receipt["verification_id"] = (
            f"verification-{canonical_hash(receipt_core)[:32]}"
        )
        receipt_identified = dict(receipt)
        receipt_identified.pop("canonical_verification_hash")
        receipt["canonical_verification_hash"] = canonical_hash(
            receipt_identified
        )
        receipt_json = canonical_json(receipt)
        receipt_row = {
            "verification_id": receipt["verification_id"],
            "decision_id": decision["decision_id"],
            "canonical_verification_json": receipt_json,
            "canonical_verification_hash": receipt[
                "canonical_verification_hash"
            ],
        }
        receipts.append((*receipt_row.values(), canonical_hash(receipt_row)))
    return requests, decisions, receipts


def test_fixed_ten_thousand_decision_budget_and_replay(tmp_path: Path) -> None:
    ledger, input_root, _, _, request = _environment(tmp_path)
    preview = ResearchDirectorService(ledger).preview("requests/request-1.json")
    requests, decisions, receipts = _direct_prior_rows(preview, 9_999)
    with ledger._mutation() as connection:
        connection.executemany(
            "INSERT INTO director_requests VALUES (?,?,?,?)", requests
        )
        connection.executemany(
            "INSERT INTO director_decisions VALUES (?,?,?,?,?)", decisions
        )
        connection.executemany(
            "INSERT INTO director_verifications VALUES (?,?,?,?,?)", receipts
        )
    service = ResearchDirectorService(ledger)
    ten_thousandth = service.record("requests/request-1.json")
    assert len(ledger.list_packages()) == MAX_RECORDED_DECISIONS
    assert service.record("requests/request-1.json").as_dict() == ten_thousandth.as_dict()
    next_request = dict(request)
    next_request["request_id"] = "request-10001"
    request_core = dict(next_request)
    request_core.pop("canonical_request_hash")
    next_request["canonical_request_hash"] = canonical_hash(request_core)
    _canonical_write(
        input_root / "requests" / "request-10001.json", next_request
    )
    with pytest.raises(DirectorError) as caught:
        service.record("requests/request-10001.json")
    assert caught.value.reason_token == "DECISION_BUDGET_EXHAUSTED"
    with ledger._connection() as connection:
        counts = [
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "director_requests", "director_decisions",
                "director_verifications",
            )
        ]
    assert counts == [10_000, 10_000, 10_000]


def test_cli_all_commands_canonical_output_and_controlled_failure(
    tmp_path: Path, capsys
) -> None:
    from offchain.research.director.__main__ import main

    ledger, _, _, _, _ = _environment(tmp_path)
    assert main(
        [
            "preview", "--database", str(ledger.database_path),
            "--request-relative-path", "requests/request-1.json",
        ]
    ) == 0
    preview_output = capsys.readouterr().out
    assert preview_output.count("\n") == 1
    assert canonical_json(json.loads(preview_output)) + "\n" == preview_output
    assert main(
        [
            "record", "--database", str(ledger.database_path),
            "--request-relative-path", "requests/request-1.json",
        ]
    ) == 0
    record_output = capsys.readouterr().out
    decision_id = json.loads(record_output)["decision"]["decision_id"]
    assert main(
        ["status", "--database", str(ledger.database_path)]
    ) == 0
    assert len(json.loads(capsys.readouterr().out)["packages"]) == 1
    assert main(
        [
            "status", "--database", str(ledger.database_path),
            "--decision-id", decision_id,
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["decision"]["decision_id"] == decision_id
    assert main(
        ["verify-ledger", "--database", str(ledger.database_path)]
    ) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "LEDGER_VERIFIED"
    assert main(["unknown"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("\n") == 1
    assert "Traceback" not in captured.err


def test_ci_workflow_is_exact_read_only_and_event_aware() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert text.startswith("name: DeltaGrid CI\n")
    assert "  offchain-tests:\n    name: offchain-tests\n" in text
    assert "runs-on: ubuntu-24.04" in text
    assert "timeout-minutes: 20" in text
    assert "permissions:\n  contents: read" in text
    assert "pull_request_target" not in text
    assert "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683" in text
    assert "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065" in text
    assert "actions/checkout v4.2.2" in text
    assert "actions/setup-python v5.6.0" in text
    assert "fetch-depth: 0" in text
    assert "persist-credentials: false" in text
    assert 'python-version: "3.12"' in text
    assert "pip install --disable-pip-version-check -r offchain/requirements.txt" in text
    assert "python -m pip freeze" in text
    assert 'git diff --check "$PR_BASE_SHA...$PR_HEAD_SHA"' in text
    assert 'git diff --check "$PUSH_BEFORE_SHA..$HEAD_SHA"' in text
    assert 'git show -m --check --format= --no-renames "$HEAD_SHA"' in text
    assert "[[ \"$1\" =~ ^[0-9a-f]{40}$ ]]" in text
    assert "offchain/tests \\" in text
    for forbidden in (
        "secrets.", "permissions: write", "actions/upload-artifact",
        "git commit", "git push", "cache:", "pull_request_target",
    ):
        assert forbidden not in text


def test_documentation_registry_identity_lock_and_current_boundaries() -> None:
    tree = ast.parse(
        (ROOT / "offchain" / "tests" / "test_documentation_status.py").read_text()
    )
    names = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]
    assert len(names) == 29
    registry = json.loads(
        (ROOT / "docs" / "documentation-status.json").read_text()
    )
    by_path = {item["path"]: item for item in registry["documents"]}
    assert by_path[
        "contracts/DELTAGRID_AUTONOMOUS_RESEARCH_DIRECTOR_V1.json"
    ]["classification"] == "MACHINE_REFERENCE"
    assert by_path[
        "docs/DELTAGRID_AUTONOMOUS_RESEARCH_DIRECTOR.md"
    ]["classification"] == "CURRENT_INTERNAL"
    readme = (ROOT / "README.md").read_text()
    assert "There is no validated profitable strategy. No candidate is selected." in readme
    assert "Paper trading and live trading are not authorized." in readme
    assert "Mission 99" in readme
