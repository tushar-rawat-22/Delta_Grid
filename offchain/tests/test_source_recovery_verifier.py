from __future__ import annotations

from pathlib import Path

import pytest

from offchain.governance.source_recovery import (
    RecoveryVerificationError,
    verify_source_recovery,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_source_recovery_verifier_reconstructs_exact_committed_head() -> None:
    payload = verify_source_recovery(REPOSITORY_ROOT)

    assert payload["status"] == "VERIFIED"
    assert payload["authority_effect"] == "NONE"
    assert payload["source_scope"] == "TRACKED_GIT_HISTORY_AT_HEAD"
    assert payload["source_sha"] == payload["recovered_sha"]
    assert payload["source_tree_sha"] == payload["recovered_tree_sha"]
    assert len(payload["source_sha"]) == 40
    assert len(payload["source_tree_sha"]) == 40


def test_source_recovery_verifier_fails_closed_for_non_repository(tmp_path: Path) -> None:
    with pytest.raises(RecoveryVerificationError, match="^REPOSITORY_INVALID$"):
        verify_source_recovery(tmp_path)
