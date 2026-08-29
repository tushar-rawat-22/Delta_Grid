from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "web" / "scripts" / "verify-public-deploy-env.sh"
REQUIRED = ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID")


def run_preflight(**values: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for name in REQUIRED:
        env.pop(name, None)
    env.update(values)
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_preflight_fails_closed_and_names_missing_configuration() -> None:
    result = run_preflight()

    assert result.returncode == 1
    assert "CLOUDFLARE_API_TOKEN" in result.stderr
    assert "CLOUDFLARE_ACCOUNT_ID" in result.stderr
    assert "public-production" in result.stderr


def test_preflight_reports_only_the_configuration_still_missing() -> None:
    result = run_preflight(CLOUDFLARE_API_TOKEN="token-value-must-not-leak")

    assert result.returncode == 1
    assert "CLOUDFLARE_ACCOUNT_ID" in result.stderr
    assert "CLOUDFLARE_API_TOKEN" not in result.stderr
    assert "token-value-must-not-leak" not in result.stdout + result.stderr


def test_preflight_passes_without_logging_secret_values() -> None:
    token = "token-value-must-not-leak"
    account = "account-value-must-not-leak"
    result = run_preflight(
        CLOUDFLARE_API_TOKEN=token,
        CLOUDFLARE_ACCOUNT_ID=account,
    )

    assert result.returncode == 0
    assert "preflight passed" in result.stdout
    assert token not in result.stdout + result.stderr
    assert account not in result.stdout + result.stderr
