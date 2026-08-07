"""Read-only point-in-time resolution for certified synthetic Mission 99 releases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .certifier import certify_release, load_certified_snapshot
from .core import (
    AvailabilityClass,
    ControlPlaneError,
    canonical_hash,
    canonical_utc,
    deep_freeze,
    load_contracts,
    parse_utc,
)
from .custody import Catalogue


@dataclass(frozen=True)
class Resolution:
    release_id: str
    release_core_hash: str
    decision_time: str
    authorization_stage: str
    selected_record_hashes: tuple[str, ...]
    excluded_future_record_count: int
    resolution_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "release_id": self.release_id,
            "release_core_hash": self.release_core_hash,
            "decision_time": self.decision_time,
            "authorization_stage": self.authorization_stage,
            "selected_record_hashes": list(self.selected_record_hashes),
            "excluded_future_record_count": self.excluded_future_record_count,
            "resolution_hash": self.resolution_hash,
        }


def resolve_release(
    catalogue: Catalogue,
    release_id: str,
    decision_time: str,
    authorization_stage: str,
) -> Resolution:
    """Resolve only causally available synthetic record identities."""

    _autonomy, mission = load_contracts()
    decision_text = canonical_utc(decision_time, "decision_time")
    decision = parse_utc(decision_text, "decision_time")
    permitted = tuple(mission["resolver"]["permitted_authorization_stages"])
    if authorization_stage not in permitted:
        raise ControlPlaneError("AUTHORIZATION_STAGE_DENIED")
    if any(token in authorization_stage.upper() for token in ("VALIDATION", "HOLDOUT", "LIVE", "PAPER", "CAPITAL")):
        raise ControlPlaneError("PROTECTED_STAGE_DENIED")
    record = catalogue.release(release_id)
    if not record["synthetic_fixture"]:
        raise ControlPlaneError("REAL_DATA_RESEARCH_RESOLUTION_UNAUTHORIZED")
    if record["relative_path"] != f"releases/{release_id}":
        raise ControlPlaneError("CATALOGUE_PATH_INVALID")
    directory = catalogue.runtime_root / record["relative_path"]
    certificate = certify_release(directory, runtime_root=catalogue.runtime_root)
    if (
        certificate.release_core_hash != record["release_core_hash"]
        or certificate.certificate_core_hash != record["certificate_core_hash"]
        or certificate.release_id != release_id
    ):
        raise ControlPlaneError("CATALOGUE_RELEASE_DISAGREEMENT")
    snapshot = load_certified_snapshot(directory, runtime_root=catalogue.runtime_root)
    selected: dict[str, tuple[int, str]] = {}
    excluded = 0
    for observation in snapshot["observations"]:
        if observation.availability_class is AvailabilityClass.UNKNOWN:
            raise ControlPlaneError("UNKNOWN_AVAILABILITY")
        if observation.available_at is None:
            raise ControlPlaneError("KNOWN_AVAILABILITY_MISSING_TIME")
        available = parse_utc(observation.available_at, "available_at")
        if available > decision:
            excluded += 1
            continue
        previous = selected.get(observation.logical_id)
        if previous is None or observation.revision_number > previous[0]:
            selected[observation.logical_id] = (
                observation.revision_number,
                observation.record_hash,
            )
    hashes = tuple(
        selected[key][1] for key in sorted(selected)
    )
    core = {
        "release_id": release_id,
        "release_core_hash": certificate.release_core_hash,
        "decision_time": decision_text,
        "authorization_stage": authorization_stage,
        "selected_record_hashes": list(hashes),
        "excluded_future_record_count": excluded,
    }
    return Resolution(
        release_id=release_id,
        release_core_hash=certificate.release_core_hash,
        decision_time=decision_text,
        authorization_stage=authorization_stage,
        selected_record_hashes=hashes,
        excluded_future_record_count=excluded,
        resolution_hash=canonical_hash(core),
    )
