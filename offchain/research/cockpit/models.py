"""Immutable configuration and fixed Mission 96B authority identities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


MISSION_CONTRACT_ID = "deltagrid-research-cockpit-ui-v1"
MISSION_CONTRACT_HASH = (
    "13846c63a6fcd07b2a4603aadd388960e74282de486bddf39907a09aa053c8d3"
)
MISSION_BASE_COMMIT = "e26eea3348a7f7f502e85baf4ad7c2ad896399f6"
MISSION_AUTHORIZATION_STAGE = "MISSION_96B_LOCAL_RESEARCH_COCKPIT"

_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_MODES = frozenset({"DEMO", "CONNECTED"})
_DEMO_SCENARIOS = frozenset({"HEALTHY", "DEGRADED"})


class CockpitError(ValueError):
    """A fail-closed cockpit error carrying a stable public reason token."""

    def __init__(self, reason_token: str, human_explanation: str) -> None:
        super().__init__(reason_token)
        self.reason_token = reason_token
        self.human_explanation = human_explanation


def _configuration_error(explanation: str) -> CockpitError:
    return CockpitError("COCKPIT_CONFIGURATION_INVALID", explanation)


@dataclass(frozen=True)
class CockpitConfig:
    """Validated immutable configuration for one local cockpit process."""

    mode: str = "DEMO"
    demo_scenario: str | None = "HEALTHY"
    ledger_path: Path | str | None = None
    result_root_path: Path | str | None = None
    repository_root_path: Path | str | None = None
    expected_repository_commit: str | None = None
    port: int = 0
    refresh_seconds: int = 30
    open_browser: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.mode, str) or self.mode.upper() not in _MODES:
            raise _configuration_error("mode must be DEMO or CONNECTED")
        mode = self.mode.upper()
        object.__setattr__(self, "mode", mode)

        scenario = self.demo_scenario
        if isinstance(scenario, str):
            scenario = scenario.upper()
        if mode == "DEMO":
            if scenario not in _DEMO_SCENARIOS:
                raise _configuration_error(
                    "demo scenario must be HEALTHY or DEGRADED"
                )
            if any(
                value is not None
                for value in (
                    self.ledger_path,
                    self.result_root_path,
                    self.repository_root_path,
                    self.expected_repository_commit,
                )
            ):
                raise _configuration_error(
                    "connected paths and commit are invalid in demo mode"
                )
        else:
            if scenario is not None:
                raise _configuration_error(
                    "demo scenario is valid only in demo mode"
                )
            required = (
                self.ledger_path,
                self.result_root_path,
                self.repository_root_path,
                self.expected_repository_commit,
            )
            if any(value is None for value in required):
                raise _configuration_error(
                    "connected mode requires ledger, result root, repository root, "
                    "and expected repository commit"
                )
            if (
                not isinstance(self.expected_repository_commit, str)
                or _COMMIT_RE.fullmatch(self.expected_repository_commit) is None
            ):
                raise _configuration_error(
                    "expected repository commit must be 40 lowercase hexadecimal "
                    "characters"
                )
            for field in (
                "ledger_path",
                "result_root_path",
                "repository_root_path",
            ):
                value = getattr(self, field)
                if not isinstance(value, (Path, str)) or not str(value):
                    raise _configuration_error(
                        "connected paths must be non-empty filesystem paths"
                    )
                object.__setattr__(self, field, Path(value))

        object.__setattr__(self, "demo_scenario", scenario)
        if (
            isinstance(self.port, bool)
            or not isinstance(self.port, int)
            or not 0 <= self.port <= 65535
        ):
            raise _configuration_error("port must be an integer from 0 through 65535")
        if (
            isinstance(self.refresh_seconds, bool)
            or not isinstance(self.refresh_seconds, int)
            or not 5 <= self.refresh_seconds <= 3600
        ):
            raise _configuration_error(
                "refresh seconds must be an integer from 5 through 3600"
            )
        if not isinstance(self.open_browser, bool):
            raise _configuration_error("open browser must be a boolean")
