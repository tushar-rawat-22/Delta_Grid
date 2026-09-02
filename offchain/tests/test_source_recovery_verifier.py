from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MODULE = "offchain.governance.source_recovery"


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", MODULE, *arguments],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_source_recovery_verifier_reconstructs_exact_committed_head() -> None:
    result = _run("--repository", str(REPOSITORY_ROOT))

    assert result.returncode == 0
    assert result.stderr == ""

    payload = json.loads(result.stdout)
    assert payload["status"] == "VERIFIED"
    assert payload["authority_effect"] == "NONE"
    assert payload["source_scope"] == "TRACKED_GIT_HISTORY_AT_HEAD"
    assert payload["source_sha"] == payload["recovered_sha"]
    assert payload["source_tree_sha"] == payload["recovered_tree_sha"]
    assert len(payload["source_sha"]) == 40
    assert len(payload["source_tree_sha"]) == 40


def test_source_recovery_verifier_fails_closed_for_non_repository(tmp_path: Path) -> None:
    result = _run("--repository", str(tmp_path))

    assert result.returncode == 1
    assert result.stderr == ""

    payload = json.loads(result.stdout)
    assert payload == {
        "authority_effect": "NONE",
        "reason_token": "REPOSITORY_INVALID",
        "source_scope": "TRACKED_GIT_HISTORY_AT_HEAD",
        "status": "BLOCKED",
    }
