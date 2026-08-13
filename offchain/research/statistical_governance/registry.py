"""Static Mission 103 service definitions and production resolvers."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping

from .core import GovernanceError, canonical_hash, freeze_json, require_identifier


ServiceFunction = Callable[[Mapping[str, Any]], Mapping[str, Any]]
_STATIC_REGISTRY_SEAL = object()


@dataclass(frozen=True)
class StatisticalAdapter:
    adapter_id: str
    definition: Mapping[str, Any]
    function: ServiceFunction

    def __post_init__(self) -> None:
        require_identifier(self.adapter_id, "adapter_id")
        definition = freeze_json(dict(self.definition))
        if set(definition) != {"version", "input_schema", "output_schema", "null_algorithm", "measurement_algorithm", "deterministic"}:
            raise GovernanceError("STATISTICAL_ADAPTER_DEFINITION_INVALID")
        for field in ("version", "input_schema", "output_schema", "measurement_algorithm"):
            require_identifier(definition[field], "adapter_definition")
        if definition["deterministic"] is not True or not isinstance(definition["null_algorithm"], dict):
            raise GovernanceError("STATISTICAL_ADAPTER_DEFINITION_INVALID")
        algorithm = definition["null_algorithm"]
        if algorithm.get("kind") == "M103_SHA256_COUNTER_ORDINAL_PLAN_V1":
            if set(algorithm) != {"kind", "algorithm_id", "plan_definition"} or algorithm["plan_definition"] != "ORDINAL_AND_U256_DRAW_V1":
                raise GovernanceError("STATISTICAL_ADAPTER_DEFINITION_INVALID")
        elif algorithm.get("kind") == "PREREGISTERED_EXACT_ENUMERATION_V1":
            if set(algorithm) != {"kind", "algorithm_id", "configurations", "observed_configuration_id"}:
                raise GovernanceError("STATISTICAL_ADAPTER_DEFINITION_INVALID")
            configurations = algorithm["configurations"]
            if not isinstance(configurations, list) or not configurations or len(configurations) > 10_000:
                raise GovernanceError("STATISTICAL_ADAPTER_DEFINITION_INVALID")
            ids = [item.get("configuration_id") for item in configurations if isinstance(item, dict)]
            if len(ids) != len(configurations) or len(set(ids)) != len(ids) or algorithm["observed_configuration_id"] not in ids:
                raise GovernanceError("STATISTICAL_ADAPTER_DEFINITION_INVALID")
        else:
            raise GovernanceError("STATISTICAL_ADAPTER_DEFINITION_INVALID")
        require_identifier(algorithm["algorithm_id"], "null_algorithm_id")
        if not callable(self.function):
            raise GovernanceError("STATISTICAL_ADAPTER_INVALID")
        object.__setattr__(self, "definition", MappingProxyType(definition))

    @property
    def adapter_hash(self) -> str:
        return canonical_hash({"adapter_id": self.adapter_id, "definition": dict(self.definition)})


@dataclass(frozen=True)
class ProtectedEvaluator:
    evaluator_id: str
    definition: Mapping[str, Any]
    function: ServiceFunction
    arbitrary_python_eligible: bool = False

    def __post_init__(self) -> None:
        require_identifier(self.evaluator_id, "evaluator_id")
        definition = freeze_json(dict(self.definition))
        if set(definition) != {"version", "input_schema", "output_schema", "measurement_algorithm", "deterministic"}:
            raise GovernanceError("PROTECTED_EVALUATOR_DEFINITION_INVALID")
        for field in ("version", "input_schema", "output_schema", "measurement_algorithm"):
            require_identifier(definition[field], "evaluator_definition")
        if definition["deterministic"] is not True or not callable(self.function) or self.arbitrary_python_eligible is not False:
            raise GovernanceError("ARBITRARY_PYTHON_NOT_PROTECTED_STAGE_ELIGIBLE")
        object.__setattr__(self, "definition", MappingProxyType(definition))

    @property
    def evaluator_hash(self) -> str:
        return canonical_hash({"evaluator_id": self.evaluator_id, "definition": dict(self.definition)})


class _SealedRegistry:
    kind = "REGISTRY"
    id_attr = ""
    hash_attr = ""

    def __init__(self, entries: tuple[Any, ...] = (), *, _seal: object | None = None) -> None:
        if entries and _seal is not _STATIC_REGISTRY_SEAL:
            raise TypeError("production services are statically sealed")
        values = tuple(entries)
        identifiers = [getattr(item, self.id_attr) for item in values]
        if len(identifiers) != len(set(identifiers)):
            raise GovernanceError(f"{self.kind}_REGISTRY_INVALID")
        self._entries = MappingProxyType({getattr(item, self.id_attr): item for item in values})

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    def snapshot_core(self) -> dict[str, Any]:
        return {"registry": self.kind, "sealed": True, "dynamic_loading": False,
                "entries": [{"id": key, "hash": getattr(item, self.hash_attr)}
                            for key, item in sorted(self._entries.items())]}

    @property
    def snapshot_hash(self) -> str:
        return canonical_hash(self.snapshot_core())

    def resolve(self, identifier: str, digest: str) -> Any:
        require_identifier(identifier, "service_id")
        value = self._entries.get(identifier)
        if value is None or getattr(value, self.hash_attr) != digest:
            raise GovernanceError(f"{self.kind}_NOT_REGISTERED")
        return value


class StatisticalAdapterRegistry(_SealedRegistry):
    kind = "STATISTICAL_ADAPTER"
    id_attr = "adapter_id"
    hash_attr = "adapter_hash"


class ProtectedEvaluatorRegistry(_SealedRegistry):
    kind = "PROTECTED_EVALUATOR"
    id_attr = "evaluator_id"
    hash_attr = "evaluator_hash"


from offchain.research.rab1.statistics import protected_evaluator, statistical_adapter


_PRODUCTION_STATISTICAL_REGISTRY = StatisticalAdapterRegistry(
    (statistical_adapter(),), _seal=_STATIC_REGISTRY_SEAL,
)
_PRODUCTION_EVALUATOR_REGISTRY = ProtectedEvaluatorRegistry(
    (protected_evaluator(),), _seal=_STATIC_REGISTRY_SEAL,
)


def production_statistical_adapter_registry() -> StatisticalAdapterRegistry:
    return _PRODUCTION_STATISTICAL_REGISTRY


def production_protected_evaluator_registry() -> ProtectedEvaluatorRegistry:
    return _PRODUCTION_EVALUATOR_REGISTRY


def _resolve_statistical_adapter(identifier: str, digest: str) -> StatisticalAdapter:
    return _PRODUCTION_STATISTICAL_REGISTRY.resolve(identifier, digest)


def _resolve_protected_evaluator(identifier: str, digest: str) -> ProtectedEvaluator:
    return _PRODUCTION_EVALUATOR_REGISTRY.resolve(identifier, digest)


__all__ = ["StatisticalAdapter", "ProtectedEvaluator", "StatisticalAdapterRegistry",
           "ProtectedEvaluatorRegistry", "production_statistical_adapter_registry",
           "production_protected_evaluator_registry"]
