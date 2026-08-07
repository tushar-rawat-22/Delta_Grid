"""Strict serialization and immutable temporal evidence for Mission 99."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import calendar
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping, TypeAlias
from urllib.parse import urlsplit


SCHEMA_VERSION = "1.0"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AUTONOMY_CONTRACT_PATH = (
    REPOSITORY_ROOT / "contracts" / "DELTAGRID_AUTONOMY_CONSTITUTION_V1.json"
)
MISSION_CONTRACT_PATH = (
    REPOSITORY_ROOT
    / "contracts"
    / "DELTAGRID_TEMPORAL_MARKET_DATA_CONTROL_PLANE_V1.json"
)

# Recomputed after the final contract contents are frozen.
AUTONOMY_CONTRACT_HASH = "b9b1d48dd3f65ac492b287e9d5dcebe11f69063138698bf37432c11869a3da5b"
MISSION_CONTRACT_HASH = "159a822f77e3c6bf6409e04b2c25a61c5c7232cf6e73ea160ffb6cbf167d5d4c"

PROVIDERS = frozenset({"BINANCE_PUBLIC"})
HOSTS = frozenset(
    {
        "api.binance.com",
        "data-api.binance.vision",
        "fapi.binance.com",
    }
)
SYMBOLS = frozenset({"BTCUSDT", "ETHUSDT", "SOLUSDT"})
STREAMS = frozenset(
    {
        "spot_ohlcv",
        "perpetual_ohlcv",
        "mark_price_ohlcv",
        "index_price_ohlcv",
        "funding_rates",
    }
)
BAR_STREAMS = STREAMS - {"funding_rates"}
INTERVALS = frozenset({"1h"})
NORMALIZER_ID = "deltagrid-mission99-normalizer-v1"
AVAILABILITY_POLICY_ID = "deltagrid-mission99-legacy-unknown-v1"
FORWARD_AVAILABILITY_POLICY_ID = "deltagrid-mission99-forward-observed-v1"
RELEASE_KIND = "FULL_SNAPSHOT_V1"
PROTECTED_BOUNDARY = {
    "network_collection": False,
    "real_data_research_resolution": False,
    "development_access": False,
    "validation_access": False,
    "holdout_access": False,
    "strategy_authority": False,
    "return_or_performance_calculation": False,
    "performance_authority": False,
    "model_or_ml_authority": False,
    "signal_authority": False,
    "paper_trading": False,
    "live_trading": False,
    "exchange_access": False,
    "credential_access": False,
    "order_placement": False,
    "portfolio_authority": False,
    "capital_deployment": False,
    "profitability_claim": False,
    "self_authorization": False,
}

MAX_JSON_NESTING = 64
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_HEADERS = 32
MAX_HEADER_BYTES = 16 * 1024
MAX_REQUEST_PARAM_KEYS = 64
MAX_STRING_BYTES = 16 * 1024
MAX_RETRY_COUNT = 3
MAX_ATTEMPT_NUMBER = MAX_RETRY_COUNT + 1
MAX_MONOTONIC_DURATION_MS = 300_000
MAX_CLOCK_DURATION_DRIFT_MS = 5_000
INTERVAL_MS = 60 * 60 * 1000
RETRYABLE_HTTP_STATUSES = frozenset({418, 429, 500, 502, 503, 504})

_HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_UTC_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z"
)
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,255}\Z")
_ENDPOINT_RE = re.compile(r"/[A-Za-z0-9._~!$&'()*+,;=:@%/-]{1,511}\Z")


class ControlPlaneError(ValueError):
    """Fail-closed error with a stable machine-readable reason."""

    def __init__(self, reason: str, explanation: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.explanation = explanation


class AvailabilityClass(str, Enum):
    OBSERVED_LIVE = "OBSERVED_LIVE"
    SOURCE_DECLARED = "SOURCE_DECLARED"
    CONSERVATIVE_RECONSTRUCTION = "CONSERVATIVE_RECONSTRUCTION"
    UNKNOWN = "UNKNOWN"


class ClockHealth(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"


class ReceiptKind(str, Enum):
    FORWARD_CAPTURE_V1 = "FORWARD_CAPTURE_V1"
    LEGACY_CAPTURE_V1 = "LEGACY_CAPTURE_V1"


def _reject_constant(value: str) -> Any:
    raise ControlPlaneError("JSON_NON_FINITE_NUMBER", value)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ControlPlaneError("JSON_DUPLICATE_KEY", key)
        result[key] = value
    return result


def _validate_json_value(value: Any, *, level: int = 0) -> None:
    if level > MAX_JSON_NESTING:
        raise ControlPlaneError("JSON_NESTING_LIMIT")
    if value is None or type(value) in {bool, int, str}:
        if type(value) is str and len(value.encode("utf-8")) > MAX_STRING_BYTES:
            raise ControlPlaneError("JSON_STRING_LIMIT")
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ControlPlaneError("JSON_NON_FINITE_NUMBER")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if type(key) is not str:
                raise ControlPlaneError("JSON_OBJECT_KEY_INVALID")
            _validate_json_value(child, level=level + 1)
        return
    if isinstance(value, (list, tuple)):
        for child in value:
            _validate_json_value(child, level=level + 1)
        return
    raise ControlPlaneError("JSON_TYPE_UNSUPPORTED", type(value).__name__)


def deep_freeze(value: Any) -> Any:
    """Return a recursively immutable JSON-compatible value."""

    _validate_json_value(value)
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): deep_freeze(child) for key, child in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(deep_freeze(child) for child in value)
    return value


def deep_thaw(value: Any) -> Any:
    """Return an independent mutable JSON-compatible copy."""

    if isinstance(value, Mapping):
        return {str(key): deep_thaw(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [deep_thaw(child) for child in value]
    if isinstance(value, list):
        return [deep_thaw(child) for child in value]
    return value


def read_bounded_regular_file(
    path: str | Path,
    *,
    maximum_bytes: int,
    size_reason: str = "FILE_SIZE_LIMIT",
    invalid_reason: str = "FILE_INPUT_INVALID",
) -> bytes:
    """Read one regular file without following a final symlink and with a hard byte cap."""

    source = Path(path)
    if type(maximum_bytes) is not int or maximum_bytes < 0:
        raise ControlPlaneError("FILE_SIZE_LIMIT_INVALID")
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(source, flags)
    except OSError as error:
        raise ControlPlaneError(invalid_reason) from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ControlPlaneError(invalid_reason)
        if metadata.st_size > maximum_bytes:
            raise ControlPlaneError(size_reason)
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(maximum_bytes + 1)
        if len(raw) > maximum_bytes:
            raise ControlPlaneError(size_reason)
        return raw
    finally:
        os.close(descriptor)


def strict_json_load(
    source: str | bytes | Path,
    *,
    maximum_bytes: int = MAX_JSON_BYTES,
) -> Any:
    """Load strict UTF-8 JSON with duplicate, type, and non-finite rejection."""

    if isinstance(source, Path):
        if source.is_symlink():
            raise ControlPlaneError("SYMLINK_REJECTED")
        raw = read_bounded_regular_file(
            source,
            maximum_bytes=maximum_bytes,
            size_reason="JSON_SIZE_LIMIT",
            invalid_reason="JSON_INPUT_INVALID",
        )
    elif isinstance(source, bytes):
        raw = source
    elif isinstance(source, str):
        raw = source.encode("utf-8")
    else:
        raise ControlPlaneError("JSON_INPUT_INVALID")
    if len(raw) > maximum_bytes:
        raise ControlPlaneError("JSON_SIZE_LIMIT")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ControlPlaneError("JSON_BOM_REJECTED")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except ControlPlaneError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ControlPlaneError("JSON_MALFORMED", str(error)) from error
    _validate_json_value(value)
    return value


def canonical_json(value: Any) -> str:
    """Return deterministic compact JSON for JSON-compatible input."""

    thawed = deep_thaw(value)
    _validate_json_value(thawed)
    try:
        return json.dumps(
            thawed,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ControlPlaneError("CANONICAL_JSON_INVALID", str(error)) from error


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require_hash(value: Any, field_name: str) -> str:
    if type(value) is not str or _HASH_RE.fullmatch(value) is None:
        raise ControlPlaneError("HASH_MALFORMED", field_name)
    return value


def require_git_commit(value: Any, field_name: str) -> str:
    if type(value) is not str or _COMMIT_RE.fullmatch(value) is None:
        raise ControlPlaneError("GIT_COMMIT_MALFORMED", field_name)
    return value


def require_identifier(value: Any, field_name: str) -> str:
    if type(value) is not str or _ID_RE.fullmatch(value) is None:
        raise ControlPlaneError("IDENTIFIER_INVALID", field_name)
    return value


def require_bool(value: Any, field_name: str) -> bool:
    if type(value) is not bool:
        raise ControlPlaneError("BOOLEAN_INVALID", field_name)
    return value


def require_int(
    value: Any,
    field_name: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if type(value) is not int:
        raise ControlPlaneError("INTEGER_INVALID", field_name)
    if minimum is not None and value < minimum:
        raise ControlPlaneError("INTEGER_RANGE_INVALID", field_name)
    if maximum is not None and value > maximum:
        raise ControlPlaneError("INTEGER_RANGE_INVALID", field_name)
    return value


def parse_utc(value: Any, field_name: str) -> datetime:
    if type(value) is not str or _UTC_RE.fullmatch(value) is None:
        raise ControlPlaneError("TIMESTAMP_INVALID", field_name)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ControlPlaneError("TIMESTAMP_INVALID", field_name) from error
    if parsed.tzinfo != timezone.utc:
        raise ControlPlaneError("TIMESTAMP_INVALID", field_name)
    return parsed


def utc_milliseconds(value: str, field_name: str) -> int:
    """Return exact millisecond UTC epoch time for a validated timestamp."""

    parsed = parse_utc(value, field_name)
    if parsed.microsecond % 1000:
        raise ControlPlaneError("TIMESTAMP_SUBMILLISECOND_UNSUPPORTED", field_name)
    return (
        calendar.timegm(parsed.utctimetuple()) * 1000
        + parsed.microsecond // 1000
    )


def canonical_utc(value: Any, field_name: str) -> str:
    """Normalize one UTC timestamp to exact millisecond precision."""

    parsed = parse_utc(value, field_name)
    if parsed.microsecond % 1000:
        raise ControlPlaneError("TIMESTAMP_SUBMILLISECOND_UNSUPPORTED", field_name)
    return (
        parsed.strftime("%Y-%m-%dT%H:%M:%S")
        + f".{parsed.microsecond // 1000:03d}Z"
    )


def _contract_hash(value: Mapping[str, Any]) -> str:
    core = deep_thaw(value)
    core.pop("contract_hash_sha256", None)
    return canonical_hash(core)


def _verify_autonomy_code_alignment(autonomy: Mapping[str, Any]) -> None:
    """Reject drift between the constitution text and permanent code boundaries."""

    expected_root = {
        "holder": "FOUNDER",
        "delegation_must_be_explicit_and_versioned": True,
        "uncertainty_behavior": "FAIL_CLOSED",
        "software_error_free_guarantee": False,
    }
    expected_proposal = {
        "system_may_propose": True,
        "system_may_approve_own_proposal": False,
        "system_may_activate_own_proposal": False,
        "proposal_is_authority": False,
        "permanent_self_authorization_prohibition": True,
    }
    expected_current = {
        "paper_trading": False,
        "live_trading": False,
        "exchange_connectivity": False,
        "credential_access": False,
        "order_authorization": False,
        "capital_deployment": False,
    }
    expected_change = {
        "reviewed_pull_request_required": True,
        "ci_required": True,
        "founder_approval_required": True,
        "authority_version_increment_required": True,
        "automatic_activation": False,
    }
    if autonomy.get("root_authority") != expected_root:
        raise ControlPlaneError("CONSTITUTION_CODE_ROOT_AUTHORITY_MISMATCH")
    if autonomy.get("proposal_activation_separation") != expected_proposal:
        raise ControlPlaneError("CONSTITUTION_CODE_PROPOSAL_MISMATCH")
    if autonomy.get("current_authority") != expected_current:
        raise ControlPlaneError("CONSTITUTION_CODE_CURRENT_AUTHORITY_MISMATCH")
    if autonomy.get("change_control") != expected_change:
        raise ControlPlaneError("CONSTITUTION_CODE_CHANGE_CONTROL_MISMATCH")
    purpose = autonomy.get("purpose")
    if not isinstance(purpose, Mapping):
        raise ControlPlaneError("CONSTITUTION_CODE_PURPOSE_MISMATCH")
    if (
        purpose.get("tenant_model") != "SINGLE_TENANT"
        or purpose.get("owner") != "Tushar Rawat"
        or purpose.get("capital_scope")
        != "FOUNDERS_OWN_CAPITAL_ONLY_IF_SEPARATELY_AUTHORIZED"
    ):
        raise ControlPlaneError("CONSTITUTION_CODE_PURPOSE_MISMATCH")


def _verify_contract_code_alignment(mission: Mapping[str, Any]) -> None:
    """Reject any drift between the immutable contract and hard code invariants."""

    try:
        scope = mission["source_scope"]
        temporal = mission["temporal_semantics"]
        receipts = mission["receipt_evidence"]
        release_model = mission["release_model"]
        resolver = mission["resolver"]
        bounds = mission["resource_bounds"]
        authority = mission["authorization_state"]
        protected = mission["protected_data"]
    except (KeyError, TypeError) as error:
        raise ControlPlaneError("CONTRACT_SCHEMA_INVALID") from error
    exact_sets = (
        (set(scope.get("providers", ())), set(PROVIDERS)),
        (set(scope.get("allowed_hosts", ())), set(HOSTS)),
        (set(scope.get("symbols", ())), set(SYMBOLS)),
        (set(scope.get("streams", ())), set(STREAMS)),
        (set(scope.get("bar_intervals", ())), set(INTERVALS)),
        (set(temporal.get("availability_classes", ())), {item.value for item in AvailabilityClass}),
        (set(receipts.get("kinds", ())), {item.value for item in ReceiptKind}),
        (set(resolver.get("permitted_authorization_stages", ())), {"SYNTHETIC_TEST_ONLY"}),
    )
    if any(actual != expected for actual, expected in exact_sets):
        raise ControlPlaneError("CONTRACT_CODE_SCOPE_MISMATCH")
    expected_bounds = {
        "allowed_provider_count": len(PROVIDERS),
        "allowed_host_count": len(HOSTS),
        "allowed_symbol_count": len(SYMBOLS),
        "allowed_stream_count": len(STREAMS),
        "allowed_interval_count": len(INTERVALS),
        "maximum_retry_count": MAX_RETRY_COUNT,
        "maximum_request_count": 0,
        "maximum_json_bytes": MAX_JSON_BYTES,
        "maximum_json_nesting": MAX_JSON_NESTING,
        "maximum_header_count": MAX_HEADERS,
        "maximum_header_bytes": MAX_HEADER_BYTES,
    }
    if any(bounds.get(key) != value for key, value in expected_bounds.items()):
        raise ControlPlaneError("CONTRACT_CODE_BOUND_MISMATCH")
    if release_model.get("release_kind") != RELEASE_KIND:
        raise ControlPlaneError("CONTRACT_CODE_RELEASE_KIND_MISMATCH")
    if temporal.get("production_reconstruction_policy_activated") is not False:
        raise ControlPlaneError("CONTRACT_CODE_TEMPORAL_MISMATCH")
    if protected != {
        "development_research_access": False,
        "validation_research_access": False,
        "holdout_research_access": False,
        "protected_observation_output": False,
        "legacy_audit_output_metadata_only": True,
        "custody_integrity_rehash_without_value_output": True,
        "custody_integrity_rehash_is_research_access": False,
    }:
        raise ControlPlaneError("CONTRACT_CODE_PROTECTED_DATA_MISMATCH")
    expected_true = {
        "market_data_custody",
        "metadata_safe_legacy_audit",
        "synthetic_release_testing",
    }
    for key, value in authority.items():
        if type(value) is not bool or value is not (key in expected_true):
            raise ControlPlaneError("CONTRACT_CODE_AUTHORITY_MISMATCH")
    if set(authority) != {
        "market_data_custody",
        "metadata_safe_legacy_audit",
        "synthetic_release_testing",
        "live_refresh",
        "real_data_research_resolution",
        "strategy_authority",
        "performance_authority",
        "model_or_ml_authority",
        "signal_authority",
        "paper_trading",
        "live_trading",
        "exchange_access",
        "credential_access",
        "order_placement",
        "portfolio_authority",
        "capital_deployment",
        "profitability_claim",
        "self_authorization",
    }:
        raise ControlPlaneError("CONTRACT_CODE_AUTHORITY_MISMATCH")
    if scope.get("live_public_refresh_execution") is not False:
        raise ControlPlaneError("CONTRACT_CODE_NETWORK_SCOPE_MISMATCH")
    if scope.get("mission_99_network_request_limit") != 0:
        raise ControlPlaneError("CONTRACT_CODE_NETWORK_SCOPE_MISMATCH")
    if receipts != {
        "kinds": [item.value for item in ReceiptKind],
        "legacy_forward_only_fields_may_be_fabricated": False,
        "observation_requires_receipt": True,
        "observation_requires_source_response_match": True,
        "receipt_requires_raw_object": True,
    }:
        raise ControlPlaneError("CONTRACT_CODE_RECEIPT_MISMATCH")
    if release_model != {
        "release_kind": RELEASE_KIND,
        "child_contains_complete_parent_evidence": True,
        "shared_content_addressed_raw_object_store": True,
        "synthetic_and_real_lineage_may_mix": False,
    }:
        raise ControlPlaneError("CONTRACT_CODE_RELEASE_MODEL_MISMATCH")
    release_identity = mission.get("release_identity")
    if release_identity != {
        "semantic_core_contains_release_id": False,
        "semantic_core_contains_release_core_hash": False,
        "release_core_hash": "SHA256_CANONICAL_RELEASE_SEMANTIC_CORE",
        "release_id": "m99-<release_core_hash>",
        "wall_clock_publication_in_semantic_identity": False,
        "sqlite_physical_hash_is_semantic_identity": False,
        "staging_identity_is_semantic_identity": False,
    }:
        raise ControlPlaneError("CONTRACT_CODE_RELEASE_IDENTITY_MISMATCH")
    runtime = mission.get("runtime")
    if not isinstance(runtime, Mapping) or any(
        (
            runtime.get("root_inside_repository_permitted") is not False,
            runtime.get("symlinks_permitted") is not False,
            runtime.get("path_traversal_permitted") is not False,
            runtime.get("silent_file_replacement_permitted") is not False,
            runtime.get("publication_atomic_same_filesystem_staging") is not True,
            runtime.get("publication_single_writer_lock") != "POSIX_FLOCK",
            runtime.get("automatic_evidence_deletion") is not False,
            runtime.get("required_directory_fsync_fail_closed") is not True,
            runtime.get("publication_lock_is_security_sandbox") is not False,
        )
    ):
        raise ControlPlaneError("CONTRACT_CODE_RUNTIME_MISMATCH")
    publication_visibility = mission.get("publication_visibility")
    if publication_visibility != {
        "resolver_discovers_only_catalogued_certified_releases": True,
        "staging_visible_to_resolver": False,
        "renamed_uncatalogued_release_visible_to_resolver": False,
        "catalogue_insert_before_final_published_verification": False,
    }:
        raise ControlPlaneError("CONTRACT_CODE_VISIBILITY_MISMATCH")
    certification = mission.get("certification")
    if certification != {
        "public_certifier_requires_certificate_file": True,
        "public_certifier_creates_or_repairs_certificate": False,
        "independent_persisted_evidence_reconstruction": True,
        "exact_sqlite_schema_required": True,
        "unexpected_tables_views_triggers_or_indexes": "REJECT",
        "full_snapshot_parent_verification": True,
        "raw_gzip_and_decompressed_hash_verification": True,
        "public_certifier_published_release_only": True,
        "staged_verifier_separate": True,
    }:
        raise ControlPlaneError("CONTRACT_CODE_CERTIFICATION_MISMATCH")
    legacy_build = mission.get("legacy_build")
    if not isinstance(legacy_build, Mapping) or any(
        (
            legacy_build.get("real_builder_is_separate_narrow_path") is not True,
            legacy_build.get("explicit_acknowledgement") != "BUILD_LEGACY_RELEASE",
            legacy_build.get("requires_clean_repository") is not True,
            legacy_build.get("repository_identity_is_read_from_git") is not True,
            legacy_build.get("re_runs_exact_audit_before_publication") is not True,
            legacy_build.get("legacy_availability_class") != "UNKNOWN",
            legacy_build.get("real_data_research_resolution") is not False,
            legacy_build.get("mission_99_execution_performs_real_build") is not False,
            legacy_build.get("metadata_safe_audit_proof_persisted_in_release") is not True,
        )
    ):
        raise ControlPlaneError("CONTRACT_CODE_LEGACY_BUILD_MISMATCH")
    recovery = mission.get("recovery")
    if not isinstance(recovery, Mapping) or any(
        (
            recovery.get("inspection_only") is not True,
            recovery.get("automatic_repair") is not False,
            recovery.get("automatic_delete") is not False,
        )
    ):
        raise ControlPlaneError("CONTRACT_CODE_RECOVERY_MISMATCH")
    if mission.get("prohibited_capabilities") != [
        "NETWORK_COLLECTION",
        "GENERIC_PROVIDER_PLUGIN",
        "BACKGROUND_DAEMON",
        "WEBSOCKET_COLLECTOR",
        "STRATEGY",
        "RETURN_OR_PERFORMANCE_CALCULATION",
        "MODEL_OR_ML",
        "SIGNAL",
        "PORTFOLIO",
        "PAPER_OR_LIVE_TRADING",
        "EXCHANGE_CREDENTIAL_OR_ORDER_ACCESS",
        "CAPITAL_DEPLOYMENT",
        "SELF_AUTHORIZATION",
    ]:
        raise ControlPlaneError("CONTRACT_CODE_PROHIBITED_CAPABILITY_MISMATCH")


def load_contracts(
    autonomy_path: Path = AUTONOMY_CONTRACT_PATH,
    mission_path: Path = MISSION_CONTRACT_PATH,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Load and recursively freeze both exact Mission 99 contracts."""

    autonomy = strict_json_load(autonomy_path, maximum_bytes=256 * 1024)
    mission = strict_json_load(mission_path, maximum_bytes=512 * 1024)
    if not isinstance(autonomy, dict) or not isinstance(mission, dict):
        raise ControlPlaneError("CONTRACT_SCHEMA_INVALID")
    if autonomy.get("schema_version") != SCHEMA_VERSION:
        raise ControlPlaneError("CONTRACT_SCHEMA_UNKNOWN")
    if mission.get("schema_version") != SCHEMA_VERSION:
        raise ControlPlaneError("CONTRACT_SCHEMA_UNKNOWN")
    if autonomy.get("contract_id") != "deltagrid-autonomy-constitution-v1":
        raise ControlPlaneError("CONTRACT_ID_INVALID")
    if mission.get("contract_id") != "deltagrid-temporal-market-data-control-plane-v1":
        raise ControlPlaneError("CONTRACT_ID_INVALID")
    actual_autonomy = _contract_hash(autonomy)
    actual_mission = _contract_hash(mission)
    if actual_autonomy != AUTONOMY_CONTRACT_HASH:
        raise ControlPlaneError("AUTONOMY_CONTRACT_HASH_MISMATCH")
    if actual_mission != MISSION_CONTRACT_HASH:
        raise ControlPlaneError("MISSION_CONTRACT_HASH_MISMATCH")
    if autonomy.get("contract_hash_sha256") != actual_autonomy:
        raise ControlPlaneError("AUTONOMY_CONTRACT_SELF_HASH_MISMATCH")
    if mission.get("contract_hash_sha256") != actual_mission:
        raise ControlPlaneError("MISSION_CONTRACT_SELF_HASH_MISMATCH")
    if mission.get("autonomy_constitution_id") != autonomy.get("contract_id"):
        raise ControlPlaneError("CONSTITUTION_LINEAGE_MISMATCH")
    if mission.get("autonomy_constitution_hash_sha256") != actual_autonomy:
        raise ControlPlaneError("CONSTITUTION_LINEAGE_MISMATCH")
    _verify_autonomy_code_alignment(autonomy)
    _verify_contract_code_alignment(mission)
    return deep_freeze(autonomy), deep_freeze(mission)


def _validated_string_map(
    value: Mapping[str, Any],
    field_name: str,
    *,
    maximum_keys: int,
    maximum_bytes: int,
) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise ControlPlaneError("MAPPING_INVALID", field_name)
    if len(value) > maximum_keys:
        raise ControlPlaneError("MAPPING_KEY_LIMIT", field_name)
    result: dict[str, str] = {}
    total = 0
    for key, child in value.items():
        if type(key) is not str or type(child) is not str:
            raise ControlPlaneError("MAPPING_TYPE_INVALID", field_name)
        total += len(key.encode("utf-8")) + len(child.encode("utf-8"))
        if total > maximum_bytes:
            raise ControlPlaneError("MAPPING_SIZE_LIMIT", field_name)
        result[key] = child
    return deep_freeze(result)


def _validated_request_params(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ControlPlaneError("REQUEST_PARAMS_INVALID")
    if len(value) > MAX_REQUEST_PARAM_KEYS:
        raise ControlPlaneError("REQUEST_PARAMS_LIMIT")
    frozen = deep_freeze(value)
    if len(canonical_json(frozen).encode("utf-8")) > MAX_HEADER_BYTES:
        raise ControlPlaneError("REQUEST_PARAMS_LIMIT")
    return frozen


def _request_hash(
    *,
    provider: str,
    host: str,
    method: str,
    endpoint_path: str,
    request_params: Mapping[str, Any],
) -> str:
    return canonical_hash(
        {
            "provider": provider,
            "host": host,
            "method": method,
            "endpoint_path": endpoint_path,
            "request_params": request_params,
        }
    )


@dataclass(frozen=True)
class AcquisitionReceipt:
    """Forward-capture evidence. Mission 99 itself never performs collection."""

    request_id: str
    provider: str
    host: str
    method: str
    endpoint_path: str
    request_params: Mapping[str, Any]
    requested_at: str
    received_at: str
    monotonic_duration_ms: int
    clock_health: ClockHealth
    http_status: int
    response_headers: Mapping[str, str]
    request_weight: Mapping[str, int]
    retry_after_seconds: int | None
    attempt_number: int
    retry_budget_exhausted: bool
    body_sha256: str
    compressed_object_sha256: str
    collector_id: str
    repository_commit: str
    request_hash: str = field(default="")
    source_response_hash: str = field(default="")
    receipt_hash: str = field(default="")
    receipt_kind: ReceiptKind = field(
        default=ReceiptKind.FORWARD_CAPTURE_V1,
        init=False,
    )

    def __post_init__(self) -> None:
        require_identifier(self.request_id, "request_id")
        if self.provider not in PROVIDERS:
            raise ControlPlaneError("PROVIDER_UNRECOGNIZED")
        if self.host not in HOSTS:
            raise ControlPlaneError("HOST_UNRECOGNIZED")
        if self.method != "GET":
            raise ControlPlaneError("HTTP_METHOD_INVALID")
        if type(self.endpoint_path) is not str or _ENDPOINT_RE.fullmatch(self.endpoint_path) is None:
            raise ControlPlaneError("ENDPOINT_PATH_INVALID")
        if "?" in self.endpoint_path or "#" in self.endpoint_path:
            raise ControlPlaneError("ENDPOINT_PATH_INVALID")
        params = _validated_request_params(self.request_params)
        object.__setattr__(self, "request_params", params)
        requested_text = canonical_utc(self.requested_at, "requested_at")
        received_text = canonical_utc(self.received_at, "received_at")
        object.__setattr__(self, "requested_at", requested_text)
        object.__setattr__(self, "received_at", received_text)
        requested = parse_utc(requested_text, "requested_at")
        received = parse_utc(received_text, "received_at")
        if received < requested:
            raise ControlPlaneError("RECEIPT_TIME_REVERSED")
        require_int(
            self.monotonic_duration_ms,
            "monotonic_duration_ms",
            minimum=0,
            maximum=MAX_MONOTONIC_DURATION_MS,
        )
        try:
            object.__setattr__(self, "clock_health", ClockHealth(self.clock_health))
        except (TypeError, ValueError) as error:
            raise ControlPlaneError("CLOCK_HEALTH_INVALID") from error
        wall_duration_ms = int((received - requested).total_seconds() * 1000)
        if (
            self.clock_health is ClockHealth.HEALTHY
            and abs(wall_duration_ms - self.monotonic_duration_ms)
            > MAX_CLOCK_DURATION_DRIFT_MS
        ):
            raise ControlPlaneError("CLOCK_DURATION_INCONSISTENT")
        require_int(self.http_status, "http_status", minimum=100, maximum=599)
        headers = _validated_string_map(
            self.response_headers,
            "response_headers",
            maximum_keys=MAX_HEADERS,
            maximum_bytes=MAX_HEADER_BYTES,
        )
        object.__setattr__(self, "response_headers", headers)
        if not isinstance(self.request_weight, Mapping) or len(self.request_weight) > 16:
            raise ControlPlaneError("REQUEST_WEIGHT_INVALID")
        weights: dict[str, int] = {}
        for key, value in self.request_weight.items():
            if type(key) is not str:
                raise ControlPlaneError("REQUEST_WEIGHT_INVALID")
            weights[key] = require_int(value, f"request_weight.{key}", minimum=0)
        object.__setattr__(self, "request_weight", deep_freeze(weights))
        if self.retry_after_seconds is not None:
            require_int(self.retry_after_seconds, "retry_after_seconds", minimum=0, maximum=86400)
            if self.http_status not in {418, 429, 503}:
                raise ControlPlaneError("RETRY_AFTER_STATUS_INVALID")
        require_int(
            self.attempt_number,
            "attempt_number",
            minimum=1,
            maximum=MAX_ATTEMPT_NUMBER,
        )
        require_bool(self.retry_budget_exhausted, "retry_budget_exhausted")
        if self.retry_budget_exhausted:
            if (
                self.attempt_number != MAX_ATTEMPT_NUMBER
                or self.http_status not in RETRYABLE_HTTP_STATUSES
            ):
                raise ControlPlaneError("RETRY_EXHAUSTION_INCONSISTENT")
        elif (
            self.attempt_number == MAX_ATTEMPT_NUMBER
            and self.http_status in RETRYABLE_HTTP_STATUSES
        ):
            raise ControlPlaneError("RETRY_EXHAUSTION_INCONSISTENT")
        require_hash(self.body_sha256, "body_sha256")
        require_hash(self.compressed_object_sha256, "compressed_object_sha256")
        require_identifier(self.collector_id, "collector_id")
        require_git_commit(self.repository_commit, "repository_commit")
        expected_request_hash = _request_hash(
            provider=self.provider,
            host=self.host,
            method=self.method,
            endpoint_path=self.endpoint_path,
            request_params=params,
        )
        if self.request_hash:
            require_hash(self.request_hash, "request_hash")
            if self.request_hash != expected_request_hash:
                raise ControlPlaneError("REQUEST_HASH_MISMATCH")
        else:
            object.__setattr__(self, "request_hash", expected_request_hash)
        expected_response_hash = canonical_hash(
            {
                "request_hash": expected_request_hash,
                "received_at": self.received_at,
                "http_status": self.http_status,
                "body_sha256": self.body_sha256,
            }
        )
        if self.source_response_hash:
            require_hash(self.source_response_hash, "source_response_hash")
            if self.source_response_hash != expected_response_hash:
                raise ControlPlaneError("SOURCE_RESPONSE_HASH_MISMATCH")
        else:
            object.__setattr__(self, "source_response_hash", expected_response_hash)
        calculated = canonical_hash(self.as_dict(include_hash=False))
        if self.receipt_hash:
            require_hash(self.receipt_hash, "receipt_hash")
            if self.receipt_hash != calculated:
                raise ControlPlaneError("RECEIPT_HASH_MISMATCH")
        else:
            object.__setattr__(self, "receipt_hash", calculated)

    def as_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        value = {
            "receipt_kind": self.receipt_kind.value,
            "request_id": self.request_id,
            "provider": self.provider,
            "host": self.host,
            "method": self.method,
            "endpoint_path": self.endpoint_path,
            "request_params": deep_thaw(self.request_params),
            "request_hash": self.request_hash,
            "requested_at": self.requested_at,
            "received_at": self.received_at,
            "monotonic_duration_ms": self.monotonic_duration_ms,
            "clock_health": self.clock_health.value,
            "http_status": self.http_status,
            "response_headers": deep_thaw(self.response_headers),
            "request_weight": deep_thaw(self.request_weight),
            "retry_after_seconds": self.retry_after_seconds,
            "attempt_number": self.attempt_number,
            "retry_budget_exhausted": self.retry_budget_exhausted,
            "source_response_hash": self.source_response_hash,
            "body_sha256": self.body_sha256,
            "compressed_object_sha256": self.compressed_object_sha256,
            "collector_id": self.collector_id,
            "repository_commit": self.repository_commit,
        }
        if include_hash:
            value["receipt_hash"] = self.receipt_hash
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AcquisitionReceipt":
        expected = {
            "receipt_kind",
            "request_id",
            "provider",
            "host",
            "method",
            "endpoint_path",
            "request_params",
            "request_hash",
            "requested_at",
            "received_at",
            "monotonic_duration_ms",
            "clock_health",
            "http_status",
            "response_headers",
            "request_weight",
            "retry_after_seconds",
            "attempt_number",
            "retry_budget_exhausted",
            "source_response_hash",
            "body_sha256",
            "compressed_object_sha256",
            "collector_id",
            "repository_commit",
            "receipt_hash",
        }
        if set(value) != expected or value.get("receipt_kind") != ReceiptKind.FORWARD_CAPTURE_V1.value:
            raise ControlPlaneError("RECEIPT_SCHEMA_INVALID")
        return cls(
            request_id=value["request_id"],
            provider=value["provider"],
            host=value["host"],
            method=value["method"],
            endpoint_path=value["endpoint_path"],
            request_params=value["request_params"],
            request_hash=value["request_hash"],
            requested_at=value["requested_at"],
            received_at=value["received_at"],
            monotonic_duration_ms=value["monotonic_duration_ms"],
            clock_health=value["clock_health"],
            http_status=value["http_status"],
            response_headers=value["response_headers"],
            request_weight=value["request_weight"],
            retry_after_seconds=value["retry_after_seconds"],
            attempt_number=value["attempt_number"],
            retry_budget_exhausted=value["retry_budget_exhausted"],
            source_response_hash=value["source_response_hash"],
            body_sha256=value["body_sha256"],
            compressed_object_sha256=value["compressed_object_sha256"],
            collector_id=value["collector_id"],
            repository_commit=value["repository_commit"],
            receipt_hash=value["receipt_hash"],
        )


@dataclass(frozen=True)
class LegacyAcquisitionReceipt:
    """Receipt built only from evidence actually retained by Mission 86."""

    request_id: str
    provider: str
    request_url: str
    method: str
    request_params: Mapping[str, Any]
    http_status: int
    captured_at: str
    response_headers: Mapping[str, str]
    response_row_count: int
    source_response_hash: str
    body_sha256: str
    compressed_object_sha256: str
    raw_relative_path: str
    source_run_label: str
    source_contract_id: str
    source_contract_hash: str
    source_manifest_hash: str
    collector_id: str
    repository_commit: str | None = None
    receipt_hash: str = field(default="")
    receipt_kind: ReceiptKind = field(
        default=ReceiptKind.LEGACY_CAPTURE_V1,
        init=False,
    )

    def __post_init__(self) -> None:
        require_identifier(self.request_id, "request_id")
        if self.provider not in PROVIDERS:
            raise ControlPlaneError("PROVIDER_UNRECOGNIZED")
        if self.method != "GET":
            raise ControlPlaneError("HTTP_METHOD_INVALID")
        if type(self.request_url) is not str:
            raise ControlPlaneError("REQUEST_URL_INVALID")
        parsed = urlsplit(self.request_url)
        try:
            port = parsed.port
        except ValueError as error:
            raise ControlPlaneError("REQUEST_URL_INVALID") from error
        if (
            parsed.scheme != "https"
            or parsed.hostname not in HOSTS
            or port not in {None, 443}
            or not parsed.path
        ):
            raise ControlPlaneError("REQUEST_URL_INVALID")
        if parsed.username or parsed.password or parsed.fragment or parsed.query:
            raise ControlPlaneError("REQUEST_URL_INVALID")
        params = _validated_request_params(self.request_params)
        object.__setattr__(self, "request_params", params)
        require_int(self.http_status, "http_status", minimum=100, maximum=599)
        captured_text = canonical_utc(self.captured_at, "captured_at")
        object.__setattr__(self, "captured_at", captured_text)
        headers = _validated_string_map(
            self.response_headers,
            "response_headers",
            maximum_keys=MAX_HEADERS,
            maximum_bytes=MAX_HEADER_BYTES,
        )
        object.__setattr__(self, "response_headers", headers)
        require_int(self.response_row_count, "response_row_count", minimum=0, maximum=1_000_000)
        require_hash(self.source_response_hash, "source_response_hash")
        require_hash(self.body_sha256, "body_sha256")
        require_hash(self.compressed_object_sha256, "compressed_object_sha256")
        if (
            type(self.raw_relative_path) is not str
            or self.raw_relative_path.startswith("/")
            or not self.raw_relative_path.endswith(".json.gz")
        ):
            raise ControlPlaneError("LEGACY_RAW_PATH_INVALID")
        if ".." in Path(self.raw_relative_path).parts:
            raise ControlPlaneError("LEGACY_RAW_PATH_INVALID")
        if Path(self.raw_relative_path).name != f"{self.source_response_hash}.json.gz":
            raise ControlPlaneError("LEGACY_RAW_PATH_IDENTITY_MISMATCH")
        require_identifier(self.source_run_label, "source_run_label")
        require_identifier(self.source_contract_id, "source_contract_id")
        require_hash(self.source_contract_hash, "source_contract_hash")
        require_hash(self.source_manifest_hash, "source_manifest_hash")
        require_identifier(self.collector_id, "collector_id")
        if self.repository_commit is not None:
            require_git_commit(self.repository_commit, "repository_commit")
        calculated = canonical_hash(self.as_dict(include_hash=False))
        if self.receipt_hash:
            require_hash(self.receipt_hash, "receipt_hash")
            if self.receipt_hash != calculated:
                raise ControlPlaneError("RECEIPT_HASH_MISMATCH")
        else:
            object.__setattr__(self, "receipt_hash", calculated)

    @property
    def host(self) -> str:
        return str(urlsplit(self.request_url).hostname)

    @property
    def endpoint_path(self) -> str:
        return urlsplit(self.request_url).path

    def as_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        value = {
            "receipt_kind": self.receipt_kind.value,
            "request_id": self.request_id,
            "provider": self.provider,
            "request_url": self.request_url,
            "method": self.method,
            "request_params": deep_thaw(self.request_params),
            "http_status": self.http_status,
            "captured_at": self.captured_at,
            "response_headers": deep_thaw(self.response_headers),
            "response_row_count": self.response_row_count,
            "source_response_hash": self.source_response_hash,
            "body_sha256": self.body_sha256,
            "compressed_object_sha256": self.compressed_object_sha256,
            "raw_relative_path": self.raw_relative_path,
            "source_run_label": self.source_run_label,
            "source_contract_id": self.source_contract_id,
            "source_contract_hash": self.source_contract_hash,
            "source_manifest_hash": self.source_manifest_hash,
            "collector_id": self.collector_id,
            "repository_commit": self.repository_commit,
        }
        if include_hash:
            value["receipt_hash"] = self.receipt_hash
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LegacyAcquisitionReceipt":
        expected = {
            "receipt_kind",
            "request_id",
            "provider",
            "request_url",
            "method",
            "request_params",
            "http_status",
            "captured_at",
            "response_headers",
            "response_row_count",
            "source_response_hash",
            "body_sha256",
            "compressed_object_sha256",
            "raw_relative_path",
            "source_run_label",
            "source_contract_id",
            "source_contract_hash",
            "source_manifest_hash",
            "collector_id",
            "repository_commit",
            "receipt_hash",
        }
        if set(value) != expected or value.get("receipt_kind") != ReceiptKind.LEGACY_CAPTURE_V1.value:
            raise ControlPlaneError("RECEIPT_SCHEMA_INVALID")
        return cls(
            request_id=value["request_id"],
            provider=value["provider"],
            request_url=value["request_url"],
            method=value["method"],
            request_params=value["request_params"],
            http_status=value["http_status"],
            captured_at=value["captured_at"],
            response_headers=value["response_headers"],
            response_row_count=value["response_row_count"],
            source_response_hash=value["source_response_hash"],
            body_sha256=value["body_sha256"],
            compressed_object_sha256=value["compressed_object_sha256"],
            raw_relative_path=value["raw_relative_path"],
            source_run_label=value["source_run_label"],
            source_contract_id=value["source_contract_id"],
            source_contract_hash=value["source_contract_hash"],
            source_manifest_hash=value["source_manifest_hash"],
            collector_id=value["collector_id"],
            repository_commit=value["repository_commit"],
            receipt_hash=value["receipt_hash"],
        )


ReceiptEvidence: TypeAlias = AcquisitionReceipt | LegacyAcquisitionReceipt


def receipt_from_dict(value: Mapping[str, Any]) -> ReceiptEvidence:
    kind = value.get("receipt_kind") if isinstance(value, Mapping) else None
    if kind == ReceiptKind.FORWARD_CAPTURE_V1.value:
        return AcquisitionReceipt.from_dict(value)
    if kind == ReceiptKind.LEGACY_CAPTURE_V1.value:
        return LegacyAcquisitionReceipt.from_dict(value)
    raise ControlPlaneError("RECEIPT_KIND_INVALID")


@dataclass(frozen=True)
class ObservationVersion:
    """One immutable semantic version of a logical market observation."""

    logical_id: str
    provider: str
    stream: str
    symbol: str
    interval: str | None
    event_time: str
    source_time: str | None
    available_at: str | None
    availability_class: AvailabilityClass
    availability_policy_id: str
    first_observed_at: str
    last_verified_at: str
    revision_number: int
    supersedes_record_hash: str | None
    source_response_hash: str
    receipt_hash: str
    normalizer_id: str
    normalized_payload: Mapping[str, Any]
    clock_health: ClockHealth
    record_hash: str = field(default="")

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "availability_class", AvailabilityClass(self.availability_class))
            object.__setattr__(self, "clock_health", ClockHealth(self.clock_health))
        except (TypeError, ValueError) as error:
            raise ControlPlaneError("OBSERVATION_ENUM_INVALID") from error
        require_identifier(self.logical_id, "logical_id")
        if self.provider not in PROVIDERS:
            raise ControlPlaneError("PROVIDER_UNRECOGNIZED")
        if self.stream not in STREAMS:
            raise ControlPlaneError("STREAM_UNRECOGNIZED")
        if self.symbol not in SYMBOLS:
            raise ControlPlaneError("SYMBOL_UNRECOGNIZED")
        expected_interval = "1h" if self.stream in BAR_STREAMS else None
        if self.interval != expected_interval:
            raise ControlPlaneError("INTERVAL_UNRECOGNIZED")
        event_text = canonical_utc(self.event_time, "event_time")
        source_text = (
            canonical_utc(self.source_time, "source_time")
            if self.source_time is not None
            else None
        )
        available_text = (
            canonical_utc(self.available_at, "available_at")
            if self.available_at is not None
            else None
        )
        first_text = canonical_utc(self.first_observed_at, "first_observed_at")
        last_text = canonical_utc(self.last_verified_at, "last_verified_at")
        object.__setattr__(self, "event_time", event_text)
        object.__setattr__(self, "source_time", source_text)
        object.__setattr__(self, "available_at", available_text)
        object.__setattr__(self, "first_observed_at", first_text)
        object.__setattr__(self, "last_verified_at", last_text)
        event = parse_utc(event_text, "event_time")
        event_ms = utc_milliseconds(event_text, "event_time")
        if self.stream in BAR_STREAMS:
            payload_for_time = self.normalized_payload
            if not isinstance(payload_for_time, Mapping):
                raise ControlPlaneError("NORMALIZED_PAYLOAD_INVALID")
            period_start_ms = payload_for_time.get("period_start_ms")
            require_int(period_start_ms, "period_start_ms", minimum=0)
            if event_ms != period_start_ms + INTERVAL_MS - 1:
                raise ControlPlaneError("BAR_EVENT_TIME_NOT_COMPLETED_CLOSE")
            expected_logical_id = (
                f"{self.provider}/{self.stream}/{self.symbol}/1h/{period_start_ms}"
            )
        else:
            expected_logical_id = (
                f"{self.provider}/funding_rates/{self.symbol}/{event_ms}"
            )
        if self.logical_id != expected_logical_id:
            raise ControlPlaneError("LOGICAL_ID_TIME_IDENTITY_MISMATCH")
        source = parse_utc(source_text, "source_time") if source_text is not None else None
        available = parse_utc(available_text, "available_at") if available_text is not None else None
        first = parse_utc(first_text, "first_observed_at")
        last = parse_utc(last_text, "last_verified_at")
        if source is not None and source < event:
            raise ControlPlaneError("SOURCE_TIME_PRECEDES_EVENT")
        if first < event:
            raise ControlPlaneError("FIRST_OBSERVATION_PRECEDES_EVENT")
        if source is not None and first < source:
            raise ControlPlaneError("FIRST_OBSERVATION_PRECEDES_SOURCE")
        if last < first:
            raise ControlPlaneError("VERIFICATION_TIME_INVALID")
        if self.availability_class is AvailabilityClass.UNKNOWN:
            if available is not None:
                raise ControlPlaneError("UNKNOWN_AVAILABILITY_HAS_TIME")
        else:
            if available is None:
                raise ControlPlaneError("KNOWN_AVAILABILITY_MISSING_TIME")
            if available < event:
                raise ControlPlaneError("AVAILABILITY_PRECEDES_EVENT")
            if source is not None and available < source:
                raise ControlPlaneError("AVAILABILITY_PRECEDES_SOURCE")
            if available > first:
                raise ControlPlaneError("AVAILABILITY_AFTER_FIRST_OBSERVATION")
        if self.availability_class is AvailabilityClass.OBSERVED_LIVE:
            if self.clock_health is not ClockHealth.HEALTHY:
                raise ControlPlaneError("CLOCK_HEALTH_UNTRUSTWORTHY")
            if self.availability_policy_id != FORWARD_AVAILABILITY_POLICY_ID:
                raise ControlPlaneError("OBSERVED_LIVE_POLICY_INVALID")
        if self.availability_class is AvailabilityClass.UNKNOWN:
            if self.availability_policy_id != AVAILABILITY_POLICY_ID:
                raise ControlPlaneError("UNKNOWN_AVAILABILITY_POLICY_INVALID")
        if self.availability_class is AvailabilityClass.SOURCE_DECLARED and source is None:
            raise ControlPlaneError("SOURCE_DECLARED_REQUIRES_SOURCE_TIME")
        if self.availability_class is AvailabilityClass.CONSERVATIVE_RECONSTRUCTION:
            if self.availability_policy_id in {AVAILABILITY_POLICY_ID, FORWARD_AVAILABILITY_POLICY_ID}:
                raise ControlPlaneError("RECONSTRUCTION_POLICY_INVALID")
        require_identifier(self.availability_policy_id, "availability_policy_id")
        require_identifier(self.normalizer_id, "normalizer_id")
        if self.normalizer_id != NORMALIZER_ID:
            raise ControlPlaneError("NORMALIZER_ID_UNSUPPORTED")
        require_hash(self.source_response_hash, "source_response_hash")
        require_hash(self.receipt_hash, "receipt_hash")
        require_int(self.revision_number, "revision_number", minimum=0)
        if self.supersedes_record_hash is not None:
            require_hash(self.supersedes_record_hash, "supersedes_record_hash")
        if (self.revision_number == 0) != (self.supersedes_record_hash is None):
            raise ControlPlaneError("REVISION_PARENT_INVALID")
        frozen_payload = deep_freeze(self.normalized_payload)
        if not isinstance(frozen_payload, Mapping):
            raise ControlPlaneError("NORMALIZED_PAYLOAD_INVALID")
        object.__setattr__(self, "normalized_payload", frozen_payload)
        calculated = canonical_hash(self.as_dict(include_hash=False))
        if self.record_hash:
            require_hash(self.record_hash, "record_hash")
            if self.record_hash != calculated:
                raise ControlPlaneError("RECORD_HASH_MISMATCH")
        else:
            object.__setattr__(self, "record_hash", calculated)

    def as_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        value = {
            "logical_id": self.logical_id,
            "provider": self.provider,
            "stream": self.stream,
            "symbol": self.symbol,
            "interval": self.interval,
            "event_time": self.event_time,
            "source_time": self.source_time,
            "available_at": self.available_at,
            "availability_class": self.availability_class.value,
            "availability_policy_id": self.availability_policy_id,
            "first_observed_at": self.first_observed_at,
            "last_verified_at": self.last_verified_at,
            "revision_number": self.revision_number,
            "supersedes_record_hash": self.supersedes_record_hash,
            "source_response_hash": self.source_response_hash,
            "receipt_hash": self.receipt_hash,
            "normalizer_id": self.normalizer_id,
            "normalized_payload": deep_thaw(self.normalized_payload),
            "clock_health": self.clock_health.value,
        }
        if include_hash:
            value["record_hash"] = self.record_hash
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ObservationVersion":
        required = {
            "logical_id",
            "provider",
            "stream",
            "symbol",
            "interval",
            "event_time",
            "source_time",
            "available_at",
            "availability_class",
            "availability_policy_id",
            "first_observed_at",
            "last_verified_at",
            "revision_number",
            "supersedes_record_hash",
            "source_response_hash",
            "receipt_hash",
            "normalizer_id",
            "normalized_payload",
            "clock_health",
            "record_hash",
        }
        if set(value) != required:
            raise ControlPlaneError("OBSERVATION_SCHEMA_INVALID")
        return cls(
            logical_id=value["logical_id"],
            provider=value["provider"],
            stream=value["stream"],
            symbol=value["symbol"],
            interval=value["interval"],
            event_time=value["event_time"],
            source_time=value["source_time"],
            available_at=value["available_at"],
            availability_class=value["availability_class"],
            availability_policy_id=value["availability_policy_id"],
            first_observed_at=value["first_observed_at"],
            last_verified_at=value["last_verified_at"],
            revision_number=value["revision_number"],
            supersedes_record_hash=value["supersedes_record_hash"],
            source_response_hash=value["source_response_hash"],
            receipt_hash=value["receipt_hash"],
            normalizer_id=value["normalizer_id"],
            normalized_payload=value["normalized_payload"],
            clock_health=value["clock_health"],
            record_hash=value["record_hash"],
        )


def validate_revision_chains(
    observations: Iterable[ObservationVersion],
) -> tuple[ObservationVersion, ...]:
    """Return canonical order after coalescing exact duplicates and rejecting conflicts."""

    unique_by_hash: dict[str, ObservationVersion] = {}
    logical_revision_hash: dict[tuple[str, int], str] = {}
    for record in observations:
        existing = unique_by_hash.get(record.record_hash)
        if existing is not None:
            if existing.as_dict() != record.as_dict():
                raise ControlPlaneError("RECORD_HASH_COLLISION")
            continue
        key = (record.logical_id, record.revision_number)
        previous_hash = logical_revision_hash.get(key)
        if previous_hash is not None and previous_hash != record.record_hash:
            raise ControlPlaneError("REVISION_FORK")
        logical_revision_hash[key] = record.record_hash
        unique_by_hash[record.record_hash] = record

    by_logical: dict[str, list[ObservationVersion]] = {}
    for record in unique_by_hash.values():
        by_logical.setdefault(record.logical_id, []).append(record)

    ordered: list[ObservationVersion] = []
    for logical_id in sorted(by_logical):
        chain = sorted(by_logical[logical_id], key=lambda item: item.revision_number)
        for index, record in enumerate(chain):
            if record.revision_number != index:
                raise ControlPlaneError("REVISION_MISSING_PARENT")
            expected_parent = None if index == 0 else chain[index - 1].record_hash
            if record.supersedes_record_hash != expected_parent:
                future_hashes = {item.record_hash for item in chain[index:]}
                if record.supersedes_record_hash in future_hashes:
                    raise ControlPlaneError("REVISION_CYCLE")
                raise ControlPlaneError("REVISION_MISSING_PARENT")
            if index:
                first_record = chain[0]
                if (
                    record.provider,
                    record.stream,
                    record.symbol,
                    record.interval,
                    record.event_time,
                ) != (
                    first_record.provider,
                    first_record.stream,
                    first_record.symbol,
                    first_record.interval,
                    first_record.event_time,
                ):
                    raise ControlPlaneError("REVISION_LOGICAL_IDENTITY_CHANGED")
                previous = chain[index - 1]
                if (
                    record.availability_class is not previous.availability_class
                    or record.availability_policy_id != previous.availability_policy_id
                    or record.normalizer_id != previous.normalizer_id
                ):
                    raise ControlPlaneError("REVISION_POLICY_IDENTITY_CHANGED")
                if parse_utc(record.first_observed_at, "first_observed_at") < parse_utc(
                    previous.first_observed_at, "previous_first_observed_at"
                ):
                    raise ControlPlaneError("REVISION_TIME_REGRESSION")
                if parse_utc(record.last_verified_at, "last_verified_at") < parse_utc(
                    previous.last_verified_at, "previous_last_verified_at"
                ):
                    raise ControlPlaneError("REVISION_TIME_REGRESSION")
                if previous.source_time is not None and record.source_time is not None:
                    if parse_utc(record.source_time, "source_time") < parse_utc(
                        previous.source_time, "previous_source_time"
                    ):
                        raise ControlPlaneError("REVISION_TIME_REGRESSION")
                if previous.available_at is not None:
                    if record.available_at is None:
                        raise ControlPlaneError("REVISION_AVAILABILITY_REGRESSION")
                    if parse_utc(record.available_at, "available_at") < parse_utc(
                        previous.available_at, "previous_available_at"
                    ):
                        raise ControlPlaneError("REVISION_AVAILABILITY_REGRESSION")
        ordered.extend(chain)
    return tuple(ordered)


def strict_gzip_body(raw: bytes, *, maximum_decompressed_bytes: int) -> bytes:
    """Return one strict gzip member after bounding expansion and trailing data."""

    import zlib

    if type(raw) is not bytes:
        raise ControlPlaneError("GZIP_INPUT_INVALID")
    if not raw:
        raise ControlPlaneError("GZIP_INVALID")
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        body = decompressor.decompress(raw, maximum_decompressed_bytes + 1)
        if len(body) > maximum_decompressed_bytes or decompressor.unconsumed_tail:
            raise ControlPlaneError("GZIP_DECOMPRESSED_SIZE_LIMIT")
        body += decompressor.flush()
    except zlib.error as error:
        raise ControlPlaneError("GZIP_INVALID") from error
    if len(body) > maximum_decompressed_bytes:
        raise ControlPlaneError("GZIP_DECOMPRESSED_SIZE_LIMIT")
    if not decompressor.eof or decompressor.unused_data:
        raise ControlPlaneError("GZIP_INVALID")
    return body
