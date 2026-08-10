"""Build public projection values from exact allowlisted repository sources."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import (
    ALLOWED_PUBLIC_DOCUMENT_PATHS,
    AUTONOMY_V5_HASH,
    CONTRACT_HASH,
    CONTRACT_ID,
    MISSION103_HASH,
    PROJECTION_SCHEMA_ID,
    REPOSITORY_ROOT,
    SOURCE_CLASSES,
    public_file_sha256,
    load_contracts,
    repository_identity,
)
from .schema import validate_projection


def _contract_identity(path: str, value: dict[str, Any]) -> dict[str, str]:
    return {
        "path": path,
        "contract_id": str(value["contract_id"]),
        "contract_hash_sha256": str(value["contract_hash_sha256"]),
    }


def build_projection(repository_root: Path | None = None) -> dict[str, Any]:
    """Return the deterministic P1.1 repository/public-contract projection."""

    root = (repository_root or REPOSITORY_ROOT).resolve(strict=True)
    contract, autonomy, mission103 = load_contracts(root)
    commit = repository_identity(root)

    mission_authority = autonomy.get("mission103_authority")
    maximum = mission103.get("maximum_verdict")
    registries = mission103.get("registries")
    if not isinstance(mission_authority, dict) or not isinstance(maximum, dict) or not isinstance(registries, dict):
        raise ValueError("controlling contract structure invalid")

    projection: dict[str, Any] = {
        "schema_id": PROJECTION_SCHEMA_ID,
        "source_classes": list(SOURCE_CLASSES),
        "core_identity": {
            "repository_commit": commit,
        },
        "authority": {
            "maximum_verdict": str(maximum["verdict"]),
            "maximum_verdict_authority_effect": str(maximum["authority_effect"]),
            "production_statistical_adapter_count": int(registries["statistical_adapter_production_entry_count"]),
            "production_protected_evaluator_count": int(registries["protected_evaluator_production_entry_count"]),
            "m104_observation": bool(mission_authority["m104_observation"]),
            "model_training_or_ml": bool(mission_authority["model_training_or_ml"]),
            "paper_trading": bool(mission_authority["paper_trading"]),
            "live_trading": bool(mission_authority["live_trading"]),
            "exchange_account_access": bool(mission_authority["exchange_account_access"]),
            "credential_access": bool(mission_authority["credential_access"]),
            "signed_exchange_requests": bool(mission_authority["signed_exchange_requests"]),
            "order_placement": bool(mission_authority["order_placement"]),
            "portfolio_allocation": bool(mission_authority["portfolio_allocation"]),
            "capital_deployment": bool(mission_authority["capital_deployment"]),
            "self_authorization": bool(mission_authority["self_authorization"]),
        },
        "contract_identities": [
            {
                "path": "contracts/DELTAGRID_PUBLIC_PROJECTION_V1.json",
                "contract_id": CONTRACT_ID,
                "contract_hash_sha256": CONTRACT_HASH,
            },
            _contract_identity("contracts/DELTAGRID_AUTONOMY_CONSTITUTION_V5.json", autonomy),
            _contract_identity(
                "contracts/DELTAGRID_INDEPENDENT_RESEARCH_VALIDATION_GOVERNANCE_V1.json",
                mission103,
            ),
        ],
        "public_document_identities": [
            {"path": relative, "sha256": public_file_sha256(root, relative)}
            for relative in ALLOWED_PUBLIC_DOCUMENT_PATHS
        ],
    }

    if projection["contract_identities"][1]["contract_hash_sha256"] != AUTONOMY_V5_HASH:
        raise ValueError("autonomy identity mismatch")
    if projection["contract_identities"][2]["contract_hash_sha256"] != MISSION103_HASH:
        raise ValueError("mission103 identity mismatch")
    validate_projection(projection)
    return projection
