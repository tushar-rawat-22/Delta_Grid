"""Verify recoverability of the committed DeltaGrid source tree.

The proof is deliberately limited to tracked Git history at the current checkout
HEAD. It does not inspect, copy, or make claims about founder records, protected
evidence, private runtime data, credentials, trading state, or capital authority.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence


VERIFIED = "VERIFIED"
BLOCKED = "BLOCKED"
AUTHORITY_EFFECT = "NONE"
SOURCE_SCOPE = "TRACKED_GIT_HISTORY_AT_HEAD"


class RecoveryVerificationError(RuntimeError):
    """Raised when the source recovery proof cannot be completed."""


def _git(repository: Path, arguments: Sequence[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RecoveryVerificationError("GIT_COMMAND_FAILED")
    return result.stdout.strip()


def verify_source_recovery(repository: Path) -> dict[str, str]:
    """Reconstruct exact HEAD from a temporary Git bundle and compare its tree."""
    repository = repository.resolve()
    if not repository.is_dir():
        raise RecoveryVerificationError("REPOSITORY_NOT_FOUND")

    try:
        worktree = _git(repository, ["rev-parse", "--show-toplevel"])
    except RecoveryVerificationError as error:
        raise RecoveryVerificationError("REPOSITORY_INVALID") from error

    if Path(worktree).resolve() != repository:
        raise RecoveryVerificationError("REPOSITORY_ROOT_REQUIRED")

    source_sha = _git(repository, ["rev-parse", "HEAD"])
    source_tree_sha = _git(repository, ["rev-parse", "HEAD^{tree}"])

    with tempfile.TemporaryDirectory(prefix="deltagrid-source-recovery-") as temporary:
        temporary_path = Path(temporary)
        bundle = temporary_path / "source.bundle"
        recovered = temporary_path / "recovered"

        _git(repository, ["bundle", "create", str(bundle), "HEAD"])
        _git(repository, ["bundle", "verify", str(bundle)])

        clone = subprocess.run(
            ["git", "clone", "--quiet", "--no-checkout", str(bundle), str(recovered)],
            check=False,
            capture_output=True,
            text=True,
        )
        if clone.returncode != 0:
            raise RecoveryVerificationError("BUNDLE_CLONE_FAILED")

        _git(recovered, ["cat-file", "-e", f"{source_sha}^{{commit}}"])
        _git(recovered, ["checkout", "--quiet", "--detach", source_sha])
        recovered_sha = _git(recovered, ["rev-parse", "HEAD"])
        recovered_tree_sha = _git(recovered, ["rev-parse", "HEAD^{tree}"])

    if recovered_sha != source_sha:
        raise RecoveryVerificationError("RECOVERED_HEAD_MISMATCH")
    if recovered_tree_sha != source_tree_sha:
        raise RecoveryVerificationError("RECOVERED_TREE_MISMATCH")

    return {
        "authority_effect": AUTHORITY_EFFECT,
        "recovered_sha": recovered_sha,
        "recovered_tree_sha": recovered_tree_sha,
        "source_scope": SOURCE_SCOPE,
        "source_sha": source_sha,
        "source_tree_sha": source_tree_sha,
        "status": VERIFIED,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify recoverability of the committed DeltaGrid source HEAD."
    )
    parser.add_argument(
        "--repository",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root to verify (defaults to this checkout).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        payload = verify_source_recovery(arguments.repository)
        returncode = 0
    except RecoveryVerificationError as error:
        payload = {
            "authority_effect": AUTHORITY_EFFECT,
            "reason_token": str(error),
            "source_scope": SOURCE_SCOPE,
            "status": BLOCKED,
        }
        returncode = 1

    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
