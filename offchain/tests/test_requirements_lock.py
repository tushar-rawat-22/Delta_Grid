from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
HISTORICAL_REQUIREMENTS = ROOT / "offchain" / "requirements.txt"
CI_REQUIREMENTS = ROOT / "offchain" / "ci-requirements.txt"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "deltagrid-ci.yml"
_NAME_NORMALIZER = re.compile(r"[-_.]+")


def _canonical_name(name: str) -> str:
    return _NAME_NORMALIZER.sub("-", name).lower()


def _parse_exact_pins(lines: list[str]) -> dict[str, str]:
    pins: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        assert ";" not in line, f"environment marker is not allowed in the CI lock: {line}"
        assert line.count("==") == 1, f"dependency must use one exact == pin: {line}"
        name, version = line.split("==", 1)
        assert name and version, f"invalid exact dependency pin: {line}"
        canonical = _canonical_name(name)
        assert canonical not in pins, f"duplicate dependency pin: {name}"
        pins[canonical] = version
    return pins


def _parse_historical_exact_pins(lines: list[str]) -> dict[str, str]:
    pins: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        assert line.count("==") == 1, f"invalid historical exact dependency pin: {line}"
        name, version = line.split("==", 1)
        assert name and version, f"invalid historical exact dependency pin: {line}"
        canonical = _canonical_name(name)
        assert canonical not in pins, f"duplicate historical dependency pin: {name}"
        pins[canonical] = version
    return pins


def test_offchain_ci_requirements_are_exact_pins() -> None:
    pins = _parse_exact_pins(CI_REQUIREMENTS.read_text(encoding="utf-8").splitlines())
    assert pins["pytest"] == "9.1.1"
    for transitive in ("greenlet", "iniconfig", "packaging", "pluggy", "pygments"):
        assert transitive in pins


def test_ci_lock_preserves_frozen_historical_runtime_pins() -> None:
    historical = _parse_historical_exact_pins(
        HISTORICAL_REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    )
    locked = _parse_exact_pins(CI_REQUIREMENTS.read_text(encoding="utf-8").splitlines())

    missing = sorted(set(historical) - set(locked))
    changed = sorted(
        name
        for name, version in historical.items()
        if locked.get(name) is not None and locked[name] != version
    )

    assert not missing, f"CI lock dropped frozen historical dependencies: {missing}"
    assert not changed, f"CI lock changed frozen historical dependency versions: {changed}"


def test_ci_workflow_installs_only_the_exact_ci_lock() -> None:
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    active = "run: python -m pip install --disable-pip-version-check -r offchain/ci-requirements.txt"
    historical = "pip install --disable-pip-version-check -r offchain/requirements.txt"
    assert active in text
    assert f"# {historical}" in text
    assert f"run: {historical}" not in text


def test_ci_environment_matches_offchain_lock() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return

    locked = _parse_exact_pins(CI_REQUIREMENTS.read_text(encoding="utf-8").splitlines())
    freeze = subprocess.run(
        [sys.executable, "-m", "pip", "freeze"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    installed = _parse_exact_pins(freeze)

    assert installed == locked, (
        "GitHub Actions installed a different Python dependency graph than "
        "offchain/ci-requirements.txt"
    )
