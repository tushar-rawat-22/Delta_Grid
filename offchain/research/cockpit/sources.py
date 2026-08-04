"""Hash-verified demo and Mission 96A connected snapshot sources."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

from offchain.research.admission import canonical_hash, canonical_json
from offchain.research.control_plane import (
    ControlPlaneError,
    ResearchControlPlaneService,
)

from .models import (
    MISSION_CONTRACT_HASH,
    MISSION_CONTRACT_ID,
    CockpitError,
)


_DEMO_DECLARATIONS = MappingProxyType(
    {
        "HEALTHY": MappingProxyType(
            {
                "filename": "healthy_snapshot.json",
                "byte_sha256": (
                    "19981f5ae6bacf02735eaf90d6a51e0d5096bd23fd42268aadce17a12bd368a9"
                ),
                "canonical_snapshot_hash": (
                    "e4f116dc8a4604a8a831d24aac0fe295ad0dd4ee74eb71e986f64d317eb4f7ed"
                ),
                "snapshot_id": "snapshot-6abde673fc6aaa5ba7e520ec16114d7b",
                "health_token": "HEALTHY",
            }
        ),
        "DEGRADED": MappingProxyType(
            {
                "filename": "degraded_snapshot.json",
                "byte_sha256": (
                    "134d86be360ab1f157f05ee03f765c7024ed3bde2f1baaf8993a4deaedd93067"
                ),
                "canonical_snapshot_hash": (
                    "5f7f8ca4bc9095c75473da84f9ba622b0dc8d191a12384e87c6ae3ad3a646a53"
                ),
                "snapshot_id": "snapshot-9618e1b91f31cb959e59bbc68204ce04",
                "health_token": "DEGRADED",
            }
        ),
    }
)
_MAX_DEMO_BYTES = 1_048_576
_MAX_CONTRACT_BYTES = 1_048_576


def _reject_constant(_: str) -> None:
    raise ValueError("non-finite number")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate object name")
        value[key] = item
    return value


def _detach(value: Any) -> Any:
    def plain(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {str(key): plain(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [plain(child) for child in item]
        return item

    return json.loads(canonical_json(plain(value)))


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _verify_snapshot_identity(value: Mapping[str, Any], declaration: Mapping[str, str]) -> None:
    try:
        core = dict(value)
        supplied_hash = core.pop("canonical_snapshot_hash")
        if (
            value["schema_version"] != "1.0"
            or value["snapshot_version"] != 1
            or supplied_hash != declaration["canonical_snapshot_hash"]
            or canonical_hash(core) != supplied_hash
            or value["snapshot_id"] != declaration["snapshot_id"]
            or value["system"]["snapshot_id"] != value["snapshot_id"]
            or value["system"]["health_token"] != declaration["health_token"]
        ):
            raise CockpitError(
                "SNAPSHOT_INTEGRITY_FAILURE",
                "The demonstration snapshot identity is invalid.",
            )
    except (KeyError, TypeError):
        raise CockpitError(
            "SNAPSHOT_INTEGRITY_FAILURE",
            "The demonstration snapshot structure is invalid.",
        ) from None


def _contract_demo_declarations() -> Mapping[str, Mapping[str, Any]]:
    repository_root = Path(__file__).resolve().parents[3]
    contracts_root = repository_root / "contracts"
    path = contracts_root / "DELTAGRID_RESEARCH_COCKPIT_UI_V1.json"
    try:
        if contracts_root.is_symlink() or path.is_symlink() or not path.is_file():
            raise CockpitError(
                "SNAPSHOT_INTEGRITY_FAILURE",
                "The cockpit contract path is unsafe.",
            )
        raw = path.read_bytes()
    except CockpitError:
        raise
    except OSError as error:
        raise CockpitError(
            "SNAPSHOT_INTEGRITY_FAILURE",
            "The cockpit contract is unavailable.",
        ) from error
    if len(raw) > _MAX_CONTRACT_BYTES or raw.startswith(b"\xef\xbb\xbf"):
        raise CockpitError(
            "SNAPSHOT_INTEGRITY_FAILURE",
            "The cockpit contract bytes are invalid.",
        )
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
        core = dict(value)
        supplied = core.pop("contract_hash_sha256")
        if (
            value["contract_id"] != MISSION_CONTRACT_ID
            or supplied != MISSION_CONTRACT_HASH
            or canonical_hash(core) != supplied
        ):
            raise CockpitError(
                "SNAPSHOT_INTEGRITY_FAILURE",
                "The cockpit contract identity is invalid.",
            )
        demos = value["demonstration_snapshots"]
        declarations = {
            "HEALTHY": demos["healthy"],
            "DEGRADED": demos["degraded"],
        }
        for scenario, expected in _DEMO_DECLARATIONS.items():
            actual = declarations[scenario]
            if any(
                actual[key] != expected[key]
                for key in (
                    "byte_sha256",
                    "canonical_snapshot_hash",
                    "snapshot_id",
                    "health_token",
                )
            ):
                raise CockpitError(
                    "SNAPSHOT_INTEGRITY_FAILURE",
                    "A demonstration declaration is invalid.",
                )
    except CockpitError:
        raise
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        KeyError,
        TypeError,
    ) as error:
        raise CockpitError(
            "SNAPSHOT_INTEGRITY_FAILURE",
            "The cockpit contract structure is invalid.",
        ) from error
    return _freeze(declarations)


class DemoSnapshotSource:
    """Load each committed synthetic demonstration exactly once and detach reads."""

    __slots__ = ("_snapshots", "_sealed")

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("DemoSnapshotSource is immutable")
        object.__setattr__(self, name, value)

    def __init__(self, *, package_root: Path | None = None) -> None:
        root = (
            package_root
            if package_root is not None
            else Path(__file__).resolve().parent
        )
        declarations = _contract_demo_declarations()
        loaded = {
            scenario: self._load_one(root, declaration)
            for scenario, declaration in declarations.items()
        }
        object.__setattr__(self, "_snapshots", _freeze(loaded))
        object.__setattr__(self, "_sealed", True)

    @staticmethod
    def _load_one(root: Path, declaration: Mapping[str, str]) -> Any:
        demo_root = root / "demo"
        path = demo_root / Path(declaration["relative_path"]).name
        try:
            if root.is_symlink() or demo_root.is_symlink() or path.is_symlink():
                raise CockpitError(
                    "SNAPSHOT_INTEGRITY_FAILURE",
                    "A demonstration snapshot path is unsafe.",
                )
            resolved_root = root.resolve(strict=True)
            resolved_demo = demo_root.resolve(strict=True)
            resolved = path.resolve(strict=True)
            if (
                not resolved.is_relative_to(resolved_demo)
                or not resolved_demo.is_relative_to(resolved_root)
                or not resolved.is_file()
            ):
                raise CockpitError(
                    "SNAPSHOT_INTEGRITY_FAILURE",
                    "A demonstration snapshot path is unsafe.",
                )
            raw = resolved.read_bytes()
        except CockpitError:
            raise
        except OSError as error:
            raise CockpitError(
                "SNAPSHOT_UNAVAILABLE",
                "A committed demonstration snapshot is unavailable.",
            ) from error
        if (
            len(raw) > _MAX_DEMO_BYTES
            or raw.startswith(b"\xef\xbb\xbf")
            or hashlib.sha256(raw).hexdigest() != declaration["byte_sha256"]
        ):
            raise CockpitError(
                "SNAPSHOT_INTEGRITY_FAILURE",
                "A demonstration snapshot failed byte verification.",
            )
        try:
            value = json.loads(
                raw.decode("utf-8", errors="strict"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise CockpitError(
                "SNAPSHOT_INTEGRITY_FAILURE",
                "A demonstration snapshot is not strict JSON.",
            ) from error
        if not isinstance(value, dict) or canonical_json(value).encode("utf-8") != raw:
            raise CockpitError(
                "SNAPSHOT_INTEGRITY_FAILURE",
                "A demonstration snapshot is not canonical JSON.",
            )
        _verify_snapshot_identity(value, declaration)
        return value

    def snapshot(self, scenario: str) -> dict[str, Any]:
        if not isinstance(scenario, str) or scenario.upper() not in self._snapshots:
            raise CockpitError(
                "DEMO_SCENARIO_INVALID",
                "The demonstration scenario must be HEALTHY or DEGRADED.",
            )
        return _detach(self._snapshots[scenario.upper()])


def _production_clock() -> datetime:
    return datetime.now(timezone.utc)


def _format_utc(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise CockpitError(
            "SNAPSHOT_UNAVAILABLE",
            "The observation clock did not return an aware UTC timestamp.",
        )
    utc = value.astimezone(timezone.utc)
    if utc.microsecond:
        return utc.isoformat(timespec="microseconds").replace("+00:00", "Z")
    return utc.isoformat(timespec="seconds").replace("+00:00", "Z")


class LiveSnapshotSource:
    """Build connected observations exclusively through Mission 96A."""

    __slots__ = ("_service", "_clock", "_sealed")

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("LiveSnapshotSource is immutable")
        object.__setattr__(self, name, value)

    def __init__(
        self,
        service: ResearchControlPlaneService,
        *,
        clock: Callable[[], datetime] = _production_clock,
    ) -> None:
        if not isinstance(service, ResearchControlPlaneService) or not callable(clock):
            raise CockpitError(
                "COCKPIT_CONFIGURATION_INVALID",
                "Connected mode requires a Mission 96A service and clock.",
            )
        object.__setattr__(self, "_service", service)
        object.__setattr__(self, "_clock", clock)
        object.__setattr__(self, "_sealed", True)

    def snapshot(self) -> dict[str, Any]:
        try:
            return self._service.build_snapshot(
                as_of=_format_utc(self._clock())
            ).as_dict()
        except CockpitError:
            raise
        except ControlPlaneError as error:
            raise CockpitError(
                "SNAPSHOT_UNAVAILABLE",
                "Mission 96A could not build the requested observation.",
            ) from error
