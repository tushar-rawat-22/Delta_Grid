from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys


CI_REQUIREMENTS = Path(__file__).resolve().parents[1] / "ci-requirements.txt"
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


def test_offchain_ci_requirements_are_exact_pins() -> None:
    pins = _parse_exact_pins(CI_REQUIREMENTS.read_text(encoding="utf-8").splitlines())
    assert pins["pytest"] == "9.1.1"
    for transitive in ("greenlet", "iniconfig", "packaging", "pluggy", "pygments"):
        assert transitive in pins


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
