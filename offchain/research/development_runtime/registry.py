"""Sealed, hash-bound Mission 102 experiment-family registry."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol, Sequence
from decimal import Decimal

from .core import (
    FAMILY_DEFINITION_ID,
    FILL_MODEL_ID,
    INSTRUMENT_IDENTITY_ID,
    REGISTRY_SNAPSHOT_ID,
    VARIANT_DEFINITION_ID,
    DevelopmentRuntimeError,
    canonical_hash,
    decimal_text,
    require_identifier,
)


TRADABLE_STREAMS = frozenset({"spot_ohlcv", "perpetual_ohlcv"})
INFORMATIONAL_STREAMS = frozenset({"mark_price_ohlcv", "index_price_ohlcv", "funding_rates"})
ALL_STREAMS = TRADABLE_STREAMS | INFORMATIONAL_STREAMS
MAX_FAMILIES = 100
MAX_VARIANTS = 10_000
MAX_ABS_PARAMETER = Decimal("1e30")
MAX_PARAMETER_DEPTH = 16
MAX_PARAMETER_NODES = 10_000
MAX_PARAMETER_CONTAINER = 1_000
MAX_PARAMETER_STRING = 4_096
MAX_PARAMETER_INTEGER = 10**30
MAPPING_PROXY_TYPE = type(MappingProxyType({}))


class Adapter(Protocol):
    def on_event(self, event: Any, state: Mapping[str, Any]) -> Sequence[Any]: ...


AdapterFactory = Callable[[Mapping[str, Any]], Adapter]


def _freeze_parameters(value: Any) -> Any:
    seen: set[int] = set()
    nodes = 0

    def freeze(item: Any, depth: int) -> Any:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_PARAMETER_NODES or depth > MAX_PARAMETER_DEPTH:
            raise DevelopmentRuntimeError("STRATEGY_PARAMETERS_LIMIT")
        if item is None or type(item) is bool:
            return item
        if type(item) is int:
            if abs(item) > MAX_PARAMETER_INTEGER:
                raise DevelopmentRuntimeError("STRATEGY_PARAMETER_INTEGER_INVALID")
            return item
        if type(item) is str:
            if len(item) > MAX_PARAMETER_STRING:
                raise DevelopmentRuntimeError("STRATEGY_PARAMETER_STRING_INVALID")
            return item
        if type(item) in {dict, MAPPING_PROXY_TYPE}:
            identity = id(item)
            if identity in seen or len(item) > MAX_PARAMETER_CONTAINER:
                raise DevelopmentRuntimeError("STRATEGY_PARAMETERS_INVALID")
            seen.add(identity)
            copied: dict[str, Any] = {}
            for key, nested in item.items():
                if type(key) is not str or not key or len(key) > 128:
                    raise DevelopmentRuntimeError("STRATEGY_PARAMETER_KEY_INVALID")
                copied[key] = freeze(nested, depth + 1)
            seen.remove(identity)
            return MappingProxyType(copied)
        if type(item) in {list, tuple}:
            identity = id(item)
            if identity in seen or len(item) > MAX_PARAMETER_CONTAINER:
                raise DevelopmentRuntimeError("STRATEGY_PARAMETERS_INVALID")
            seen.add(identity)
            copied = tuple(freeze(nested, depth + 1) for nested in item)
            seen.remove(identity)
            return copied
        # Floats, Decimal instances, and custom objects are deliberately not
        # canonical economic parameter values. Decimal values use strings.
        raise DevelopmentRuntimeError("STRATEGY_PARAMETER_TYPE_INVALID")

    return freeze(value, 0)


def _thaw_parameters(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_parameters(nested) for key, nested in value.items()}
    if type(value) is tuple:
        return [_thaw_parameters(nested) for nested in value]
    return value


def canonical_instrument_id(stream: str, symbol: str) -> str:
    """Return the frozen exact Mission 102 ``stream:symbol`` identity."""

    if stream not in ALL_STREAMS:
        raise DevelopmentRuntimeError("INSTRUMENT_STREAM_INVALID", stream)
    require_identifier(symbol, "symbol")
    if ":" in symbol:
        raise DevelopmentRuntimeError("INSTRUMENT_SYMBOL_INVALID")
    return f"{stream}:{symbol}"


def parse_instrument_id(value: Any, *, tradable: bool = False) -> tuple[str, str]:
    if type(value) is not str or len(value) > 320 or value.count(":") != 1:
        raise DevelopmentRuntimeError("INSTRUMENT_ID_INVALID")
    stream, symbol = value.split(":", 1)
    expected = canonical_instrument_id(stream, symbol)
    if expected != value or (tradable and stream not in TRADABLE_STREAMS):
        raise DevelopmentRuntimeError("INSTRUMENT_NOT_TRADABLE" if tradable else "INSTRUMENT_ID_INVALID")
    return stream, symbol


@dataclass(frozen=True)
class VariantDefinition:
    variant_id: str
    required_streams: tuple[str, ...]
    required_symbols: tuple[str, ...]
    observable_inputs: tuple[str, ...]
    tradable_instruments: tuple[str, ...]
    informational_streams: tuple[str, ...]
    initial_research_nav: str
    max_gross_research_exposure: str
    max_net_research_exposure: str
    per_instrument_bounds: Mapping[str, str]
    fee_bps: str
    slippage_bps: str
    funding_accounting_applicable: bool
    strategy_parameters: Mapping[str, Any]

    def __post_init__(self) -> None:
        require_identifier(self.variant_id, "variant_id")
        required = tuple(self.required_streams)
        if not required or len(required) != len(set(required)) or not set(required) <= ALL_STREAMS:
            raise DevelopmentRuntimeError("VARIANT_STREAMS_INVALID")
        symbols = tuple(self.required_symbols)
        if not symbols or len(symbols) != len(set(symbols)) or len(symbols) > 64:
            raise DevelopmentRuntimeError("VARIANT_SYMBOLS_INVALID")
        for symbol in symbols:
            require_identifier(symbol, "required_symbol")
            if ":" in symbol:
                raise DevelopmentRuntimeError("VARIANT_SYMBOLS_INVALID")
        observable = tuple(self.observable_inputs)
        if not observable or len(observable) != len(set(observable)) or len(observable) > 320:
            raise DevelopmentRuntimeError("VARIANT_OBSERVABLE_SCOPE_INVALID")
        observable_pairs = [parse_instrument_id(item) for item in observable]
        if {stream for stream, _symbol in observable_pairs} != set(required) or {symbol for _stream, symbol in observable_pairs} != set(symbols):
            raise DevelopmentRuntimeError("VARIANT_OBSERVABLE_SCOPE_INVALID")
        tradable = tuple(self.tradable_instruments)
        if not tradable or len(tradable) > 64:
            raise DevelopmentRuntimeError("VARIANT_INSTRUMENTS_INVALID")
        if len(tradable) != len(set(tradable)):
            raise DevelopmentRuntimeError("VARIANT_INSTRUMENTS_INVALID")
        for instrument_id in tradable:
            parse_instrument_id(instrument_id, tradable=True)
            if instrument_id not in observable:
                raise DevelopmentRuntimeError("VARIANT_OBSERVABLE_SCOPE_INVALID")
        informational = tuple(self.informational_streams)
        if len(informational) != len(set(informational)) or not set(informational) <= INFORMATIONAL_STREAMS:
            raise DevelopmentRuntimeError("VARIANT_STREAMS_INVALID")
        observable_informational = {stream for stream, _symbol in observable_pairs if stream in INFORMATIONAL_STREAMS}
        if set(informational) != observable_informational:
            raise DevelopmentRuntimeError("VARIANT_OBSERVABLE_SCOPE_INVALID")
        for field in (
            "initial_research_nav", "max_gross_research_exposure",
            "max_net_research_exposure", "fee_bps", "slippage_bps",
        ):
            value = decimal_text(getattr(self, field), field, nonnegative=True)
            if Decimal(value) > MAX_ABS_PARAMETER:
                raise DevelopmentRuntimeError("VARIANT_NUMERIC_BOUND_INVALID")
        if Decimal(self.initial_research_nav) <= 0:
            raise DevelopmentRuntimeError("INITIAL_RESEARCH_NAV_INVALID")
        if Decimal(self.fee_bps) > Decimal("10000"):
            raise DevelopmentRuntimeError("FEE_BPS_INVALID")
        if Decimal(self.slippage_bps) >= Decimal("10000"):
            raise DevelopmentRuntimeError("SLIPPAGE_BPS_INVALID")
        bounds = dict(self.per_instrument_bounds)
        if set(bounds) != set(tradable):
            raise DevelopmentRuntimeError("VARIANT_BOUNDS_INVALID")
        for value in bounds.values():
            decimal_text(value, "per_instrument_bound", nonnegative=True)
            if Decimal(value) > MAX_ABS_PARAMETER:
                raise DevelopmentRuntimeError("VARIANT_NUMERIC_BOUND_INVALID")
        if type(self.funding_accounting_applicable) is not bool or not isinstance(self.strategy_parameters, Mapping):
            raise DevelopmentRuntimeError("VARIANT_DEFINITION_INVALID")
        parameters = _freeze_parameters(self.strategy_parameters)
        object.__setattr__(self, "required_streams", required)
        object.__setattr__(self, "required_symbols", symbols)
        object.__setattr__(self, "observable_inputs", observable)
        object.__setattr__(self, "tradable_instruments", tradable)
        object.__setattr__(self, "informational_streams", informational)
        object.__setattr__(self, "per_instrument_bounds", MappingProxyType(bounds))
        object.__setattr__(self, "strategy_parameters", parameters)

    def core(self) -> dict[str, Any]:
        return {
            "definition_schema": VARIANT_DEFINITION_ID,
            "instrument_identity": INSTRUMENT_IDENTITY_ID,
            "variant_id": self.variant_id,
            "required_streams": list(self.required_streams),
            "required_symbols": list(self.required_symbols),
            "observable_inputs": list(self.observable_inputs),
            "tradable_instruments": list(self.tradable_instruments),
            "informational_streams": list(self.informational_streams),
            "initial_research_nav": self.initial_research_nav,
            "max_gross_research_exposure": self.max_gross_research_exposure,
            "max_net_research_exposure": self.max_net_research_exposure,
            "per_instrument_bounds": dict(sorted(self.per_instrument_bounds.items())),
            "fee_model": {"kind": "BPS_ON_ABSOLUTE_FILL_NOTIONAL", "bps": self.fee_bps},
            "slippage_model": {"kind": "DIRECTIONAL_BPS_FROM_BAR_CLOSE", "bps": self.slippage_bps},
            "causal_fill_model": FILL_MODEL_ID,
            "funding_accounting_applicable": self.funding_accounting_applicable,
            "strategy_parameters": _thaw_parameters(self.strategy_parameters),
        }

    @property
    def definition_hash(self) -> str:
        return canonical_hash(self.core())

    def validate_dataset_scope(self, descriptor: Mapping[str, Any]) -> None:
        allowed_streams = descriptor.get("allowed_streams")
        allowed_symbols = descriptor.get("allowed_symbols")
        if not isinstance(allowed_streams, list) or not set(self.required_streams) <= set(allowed_streams):
            raise DevelopmentRuntimeError("VARIANT_REQUIRED_STREAM_MISSING")
        if not isinstance(allowed_symbols, list) or not set(self.required_symbols) <= set(allowed_symbols):
            raise DevelopmentRuntimeError("VARIANT_REQUIRED_SYMBOL_MISSING")
        for instrument_id in self.tradable_instruments:
            stream, symbol = parse_instrument_id(instrument_id, tradable=True)
            if stream not in allowed_streams or symbol not in allowed_symbols:
                raise DevelopmentRuntimeError("VARIANT_TRADABLE_INSTRUMENT_NOT_PERMITTED")


@dataclass(frozen=True)
class FamilyDefinition:
    family_id: str
    variants: tuple[VariantDefinition, ...]
    adapter_factory: AdapterFactory

    def __post_init__(self) -> None:
        require_identifier(self.family_id, "family_id")
        variants = tuple(self.variants)
        if not variants or len(variants) > MAX_VARIANTS or len({v.variant_id for v in variants}) != len(variants):
            raise DevelopmentRuntimeError("FAMILY_VARIANT_PLAN_INVALID")
        if not callable(self.adapter_factory):
            raise DevelopmentRuntimeError("ADAPTER_FACTORY_INVALID")
        object.__setattr__(self, "variants", variants)

    def core(self) -> dict[str, Any]:
        return {
            "definition_schema": FAMILY_DEFINITION_ID,
            "family_id": self.family_id,
            "variant_plan": [
                {"declared_trial_number": index, "variant_id": variant.variant_id, "variant_definition_hash": variant.definition_hash}
                for index, variant in enumerate(self.variants, start=1)
            ],
        }

    @property
    def definition_hash(self) -> str:
        return canonical_hash(self.core())

    def variant_for_trial(self, declared_trial_number: int, permit_budget: int) -> VariantDefinition:
        if type(declared_trial_number) is not int or declared_trial_number < 1:
            raise DevelopmentRuntimeError("DECLARED_TRIAL_NUMBER_INVALID")
        if declared_trial_number > permit_budget or declared_trial_number > len(self.variants):
            raise DevelopmentRuntimeError("TRIAL_VARIANT_OUT_OF_RANGE")
        return self.variants[declared_trial_number - 1]


class ExperimentRegistry:
    """Immutable family collection. Production construction is deliberately empty."""

    def __init__(self, families: Sequence[FamilyDefinition] = ()) -> None:
        values = tuple(families)
        if len(values) > MAX_FAMILIES or len({item.family_id for item in values}) != len(values):
            raise DevelopmentRuntimeError("EXPERIMENT_REGISTRY_INVALID")
        self._families = MappingProxyType({item.family_id: item for item in values})

    @property
    def family_count(self) -> int:
        return len(self._families)

    def snapshot_core(self) -> dict[str, Any]:
        return {
            "registry_schema": REGISTRY_SNAPSHOT_ID,
            "families": [
                {"family_id": item.family_id, "family_definition_hash": item.definition_hash}
                for item in sorted(self._families.values(), key=lambda value: value.family_id)
            ],
        }

    @property
    def snapshot_hash(self) -> str:
        return canonical_hash(self.snapshot_core())

    def resolve(self, family_id: str, declared_trial_number: int, permit_budget: int) -> tuple[FamilyDefinition, VariantDefinition]:
        family = self._families.get(family_id)
        if family is None:
            raise DevelopmentRuntimeError("EXPERIMENT_FAMILY_NOT_REGISTERED")
        return family, family.variant_for_trial(declared_trial_number, permit_budget)


def production_registry() -> ExperimentRegistry:
    return ExperimentRegistry(())
