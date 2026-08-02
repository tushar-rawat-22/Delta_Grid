"""Fail-closed metadata-only dataset catalog resolution."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import re
from types import MappingProxyType
from typing import Any, Mapping

from .models import AdmissionError, DatasetResolution, canonical_hash


CATALOG_FIELDS = frozenset({"schema_version", "records", "catalog_hash_sha256"})
RECORD_FIELDS = frozenset(
    {
        "schema_version",
        "dataset_id",
        "artifact_id",
        "content_sha256",
        "metadata_sha256",
        "data_class",
        "split_identity",
        "artifact_path",
        "allowed_authorization_stages",
        "protected",
        "provenance_reference",
    }
)
KNOWN_DATA_CLASSES = frozenset(
    {
        "SYNTHETIC_FIXTURE",
        "REAL_MARKET_DEVELOPMENT",
        "REAL_MARKET_VALIDATION",
        "REAL_MARKET_HOLDOUT",
    }
)
SHA256_HEX_RE = re.compile(r"[0-9a-f]{64}\Z")


class DatasetResolver:
    """Resolve catalog metadata without ever opening artifact bytes."""

    def __init__(self, catalog: Mapping[str, Any], artifact_root: Path | str) -> None:
        if not isinstance(catalog, Mapping) or set(catalog) != CATALOG_FIELDS:
            raise AdmissionError(
                "INTERNAL_INTEGRITY_FAILURE", "catalog fields are not exact"
            )
        if catalog["schema_version"] != "1.0" or not isinstance(
            catalog["records"], list
        ):
            raise AdmissionError(
                "INTERNAL_INTEGRITY_FAILURE", "catalog schema is invalid"
            )
        core = dict(catalog)
        supplied_hash = core.pop("catalog_hash_sha256")
        if not isinstance(supplied_hash, str) or canonical_hash(core) != supplied_hash:
            raise AdmissionError(
                "INTERNAL_INTEGRITY_FAILURE", "catalog hash does not match"
            )
        records: dict[str, Mapping[str, Any]] = {}
        for record in catalog["records"]:
            validated = self._validate_record(record)
            dataset_id = validated["dataset_id"]
            if dataset_id in records:
                raise AdmissionError(
                    "INTERNAL_INTEGRITY_FAILURE", "duplicate dataset identifier"
                )
            records[dataset_id] = MappingProxyType(validated)
        self._catalog_hash = supplied_hash
        self._records = MappingProxyType(records)
        self._artifact_root = Path(artifact_root).resolve(strict=False)

    @staticmethod
    def _validate_record(record: Any) -> dict[str, Any]:
        if not isinstance(record, Mapping) or set(record) != RECORD_FIELDS:
            raise AdmissionError(
                "INTERNAL_INTEGRITY_FAILURE", "catalog record fields are not exact"
            )
        copied = dict(record)
        if copied["schema_version"] != "1.0":
            raise AdmissionError(
                "INTERNAL_INTEGRITY_FAILURE", "record schema is invalid"
            )
        if type(copied["protected"]) is not bool or not isinstance(
            copied["allowed_authorization_stages"], list
        ):
            raise AdmissionError(
                "INTERNAL_INTEGRITY_FAILURE", "record metadata types are invalid"
            )
        required_strings = RECORD_FIELDS - {
            "protected",
            "allowed_authorization_stages",
            "metadata_sha256",
        }
        if any(
            not isinstance(copied[field], str) or not copied[field]
            for field in required_strings
        ):
            raise AdmissionError(
                "INTERNAL_INTEGRITY_FAILURE", "record strings are invalid"
            )
        if SHA256_HEX_RE.fullmatch(copied["content_sha256"]) is None:
            raise AdmissionError(
                "INTERNAL_INTEGRITY_FAILURE",
                "content_sha256 must be exactly 64 lowercase hexadecimal characters",
            )
        if any(
            not isinstance(stage, str) or not stage
            for stage in copied["allowed_authorization_stages"]
        ):
            raise AdmissionError(
                "INTERNAL_INTEGRITY_FAILURE", "authorization stages are invalid"
            )
        core = dict(copied)
        supplied_hash = core.pop("metadata_sha256")
        if not isinstance(supplied_hash, str) or canonical_hash(core) != supplied_hash:
            raise AdmissionError(
                "INTERNAL_INTEGRITY_FAILURE", "record metadata hash does not match"
            )
        copied["allowed_authorization_stages"] = tuple(
            copied["allowed_authorization_stages"]
        )
        return copied

    @property
    def catalog_hash(self) -> str:
        return self._catalog_hash

    def resolve(
        self,
        *,
        dataset_id: str,
        requested_hash: str,
        data_class: str,
        split_identity: str,
        authorization_stage: str,
    ) -> DatasetResolution:
        """Return authorized metadata or raise a stable fail-closed reason."""

        record = self._records.get(dataset_id)
        if record is None:
            raise AdmissionError("DATASET_UNKNOWN")
        if requested_hash != record["content_sha256"]:
            raise AdmissionError("DATASET_HASH_MISMATCH")
        record_class = record["data_class"]
        if record_class not in KNOWN_DATA_CLASSES or data_class not in KNOWN_DATA_CLASSES:
            raise AdmissionError("DATASET_CLASS_UNAUTHORIZED")
        if record["protected"]:
            raise AdmissionError("PROTECTED_DATA_FORBIDDEN")
        record_split = record["split_identity"]
        if (
            "VALIDATION" in record_split
            or "VALIDATION" in split_identity
            or record_class.endswith("_VALIDATION")
        ):
            raise AdmissionError("VALIDATION_FORBIDDEN")
        if (
            "HOLDOUT" in record_split
            or "HOLDOUT" in split_identity
            or record_class.endswith("_HOLDOUT")
        ):
            raise AdmissionError("HOLDOUT_FORBIDDEN")
        if (
            record_class != "SYNTHETIC_FIXTURE"
            or data_class != record_class
            or record_split != "SYNTHETIC_DEVELOPMENT"
            or split_identity != record_split
        ):
            raise AdmissionError("DATASET_CLASS_UNAUTHORIZED")
        if authorization_stage not in record["allowed_authorization_stages"]:
            raise AdmissionError("AUTHORIZATION_STAGE_MISMATCH")
        artifact_path = record["artifact_path"]
        pure_path = PurePosixPath(artifact_path)
        if pure_path.is_absolute() or ".." in pure_path.parts:
            raise AdmissionError("DATASET_PATH_UNSAFE")
        candidate = (self._artifact_root / Path(*pure_path.parts)).resolve(strict=False)
        if not candidate.is_relative_to(self._artifact_root):
            raise AdmissionError("DATASET_PATH_UNSAFE")
        core = {
            "schema_version": "1.0",
            "dataset_id": dataset_id,
            "artifact_id": record["artifact_id"],
            "content_sha256": record["content_sha256"],
            "metadata_sha256": record["metadata_sha256"],
            "data_class": record_class,
            "split_identity": record_split,
            "artifact_path": artifact_path,
            "authorization_stage": authorization_stage,
            "provenance_reference": record["provenance_reference"],
            "reason_token": "DATASET_AUTHORIZED",
        }
        return DatasetResolution(
            **core,
            canonical_resolution_hash=canonical_hash(core),
        )
