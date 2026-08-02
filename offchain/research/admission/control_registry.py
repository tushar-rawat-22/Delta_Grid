"""Immutable validation registry for the four non-alpha controls."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

from .models import AdmissionError, ValidatedControl, canonical_hash


_CONTROLS = MappingProxyType(
    {
        "NO_TRADE_CONTROL": MappingProxyType({}),
        "BUY_AND_HOLD_CONTROL": MappingProxyType({}),
        "SEEDED_RANDOM_CONTROL": MappingProxyType({"seed": "INTEGER"}),
        "SIMULATOR_STATE_MACHINE_CONTROL": MappingProxyType(
            {
                "scenario_id": (
                    "ROUND_TRIP",
                    "STOP_AND_COOLDOWN",
                    "PARTIAL_FILL_SEQUENCE",
                )
            }
        ),
    }
)


class ControlRegistry:
    """Validate exact control parameters without importing executable code."""

    @property
    def controls(self) -> Mapping[str, Mapping[str, Any]]:
        return _CONTROLS

    def validate(
        self, control_identifier: str, parameters: Mapping[str, Any]
    ) -> ValidatedControl:
        """Return a deterministic non-executable specification."""

        contract = _CONTROLS.get(control_identifier)
        if contract is None:
            raise AdmissionError("CONTROL_UNKNOWN")
        if not isinstance(parameters, Mapping):
            raise AdmissionError("CONTROL_PARAMETER_TYPE_INVALID")
        expected = set(contract)
        provided = set(parameters)
        if expected - provided:
            raise AdmissionError("CONTROL_PARAMETER_MISSING")
        if provided - expected:
            raise AdmissionError("CONTROL_PARAMETER_EXTRA")
        copied = dict(parameters)
        if control_identifier == "SEEDED_RANDOM_CONTROL":
            seed = copied["seed"]
            if type(seed) is not int:
                raise AdmissionError("CONTROL_PARAMETER_TYPE_INVALID")
            if not 0 <= seed <= 9223372036854775807:
                raise AdmissionError("CONTROL_PARAMETER_VALUE_INVALID")
        elif control_identifier == "SIMULATOR_STATE_MACHINE_CONTROL":
            scenario_id = copied["scenario_id"]
            if not isinstance(scenario_id, str):
                raise AdmissionError("CONTROL_PARAMETER_TYPE_INVALID")
            if scenario_id not in contract["scenario_id"]:
                raise AdmissionError("CONTROL_PARAMETER_VALUE_INVALID")
        core = {
            "schema_version": "1.0",
            "control_identifier": control_identifier,
            "control_parameters": copied,
            "non_alpha": True,
            "execution_authorized": False,
        }
        return ValidatedControl(
            **{
                **core,
                "control_parameters": MappingProxyType(dict(copied)),
            },
            canonical_control_hash=canonical_hash(core),
        )
