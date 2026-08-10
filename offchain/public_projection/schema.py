"""Exact schemas for deterministic DeltaGrid public-projection packages."""

from __future__ import annotations

from typing import Any, Mapping

from .core import (
    CONTRACT_HASH,
    MANIFEST_SCHEMA_ID,
    PROJECTION_SCHEMA_ID,
    SOURCE_CLASSES,
    ProjectionError,
    require_commit,
    require_hash,
)


PROJECTION_KEYS = {
    "schema_id",
    "source_classes",
    "core_identity",
    "authority",
    "contract_identities",
    "public_document_identities",
}
CORE_IDENTITY_KEYS = {"repository_commit"}
AUTHORITY_KEYS = {
    "maximum_verdict",
    "maximum_verdict_authority_effect",
    "production_statistical_adapter_count",
    "production_protected_evaluator_count",
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
}
CONTRACT_IDENTITY_KEYS = {"path", "contract_id", "contract_hash_sha256"}
DOCUMENT_IDENTITY_KEYS = {"path", "sha256"}
MANIFEST_KEYS = {
    "manifest_schema",
    "public_projection_contract_hash",
    "repository_commit",
    "projection_sha256",
}


def _exact_mapping(value: Any, expected: set[str], reason: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ProjectionError(reason)
    return value


def _require_bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise ProjectionError("PROJECTION_BOOLEAN_INVALID", field)
    return value


def _require_nonnegative_int(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ProjectionError("PROJECTION_INTEGER_INVALID", field)
    return value


def _require_text(value: Any, field: str, *, maximum: int = 512) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        raise ProjectionError("PROJECTION_TEXT_INVALID", field)
    return value


def validate_projection(value: Any) -> dict[str, Any]:
    projection = dict(_exact_mapping(value, PROJECTION_KEYS, "PROJECTION_SCHEMA_INVALID"))
    if projection["schema_id"] != PROJECTION_SCHEMA_ID:
        raise ProjectionError("PROJECTION_SCHEMA_INVALID")
    source_classes = projection["source_classes"]
    if type(source_classes) is not list or tuple(source_classes) != SOURCE_CLASSES:
        raise ProjectionError("PROJECTION_SOURCE_CLASSES_INVALID")

    core = _exact_mapping(projection["core_identity"], CORE_IDENTITY_KEYS, "PROJECTION_CORE_IDENTITY_INVALID")
    require_commit(core["repository_commit"])

    authority = _exact_mapping(projection["authority"], AUTHORITY_KEYS, "PROJECTION_AUTHORITY_INVALID")
    _require_text(authority["maximum_verdict"], "maximum_verdict")
    if authority["maximum_verdict_authority_effect"] != "NONE":
        raise ProjectionError("PROJECTION_AUTHORITY_INVALID")
    _require_nonnegative_int(authority["production_statistical_adapter_count"], "production_statistical_adapter_count")
    _require_nonnegative_int(authority["production_protected_evaluator_count"], "production_protected_evaluator_count")
    for field in AUTHORITY_KEYS - {
        "maximum_verdict",
        "maximum_verdict_authority_effect",
        "production_statistical_adapter_count",
        "production_protected_evaluator_count",
    }:
        if _require_bool(authority[field], field) is not False:
            raise ProjectionError("PROJECTION_AUTHORITY_INVALID", field)

    contracts = projection["contract_identities"]
    if type(contracts) is not list or not contracts or len(contracts) > 16:
        raise ProjectionError("PROJECTION_CONTRACT_IDENTITIES_INVALID")
    contract_paths: set[str] = set()
    for item in contracts:
        identity = _exact_mapping(item, CONTRACT_IDENTITY_KEYS, "PROJECTION_CONTRACT_IDENTITY_INVALID")
        path = _require_text(identity["path"], "contract_path")
        if path in contract_paths:
            raise ProjectionError("PROJECTION_CONTRACT_IDENTITY_DUPLICATE")
        contract_paths.add(path)
        _require_text(identity["contract_id"], "contract_id")
        require_hash(identity["contract_hash_sha256"], "contract_hash_sha256")

    documents = projection["public_document_identities"]
    if type(documents) is not list or not documents or len(documents) > 32:
        raise ProjectionError("PROJECTION_DOCUMENT_IDENTITIES_INVALID")
    document_paths: set[str] = set()
    for item in documents:
        identity = _exact_mapping(item, DOCUMENT_IDENTITY_KEYS, "PROJECTION_DOCUMENT_IDENTITY_INVALID")
        path = _require_text(identity["path"], "document_path")
        if path in document_paths:
            raise ProjectionError("PROJECTION_DOCUMENT_IDENTITY_DUPLICATE")
        document_paths.add(path)
        require_hash(identity["sha256"], "document_sha256")
    return projection


def validate_manifest(value: Any) -> dict[str, Any]:
    manifest = dict(_exact_mapping(value, MANIFEST_KEYS, "MANIFEST_SCHEMA_INVALID"))
    if manifest["manifest_schema"] != MANIFEST_SCHEMA_ID:
        raise ProjectionError("MANIFEST_SCHEMA_INVALID")
    if manifest["public_projection_contract_hash"] != CONTRACT_HASH:
        raise ProjectionError("MANIFEST_CONTRACT_HASH_MISMATCH")
    require_commit(manifest["repository_commit"])
    require_hash(manifest["projection_sha256"], "projection_sha256")
    return manifest
