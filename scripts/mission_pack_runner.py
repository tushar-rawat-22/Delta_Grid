"""Validate and apply reviewed local mission-pack JSON files.

The supported ``run`` command may write declared repository files, execute the
declared local verification plan, and commit or push only when explicitly
requested. Dry-run validates and summarizes the pack without applying declared
file actions or executing verification commands, while still writing a local
summary. This is development automation, not research or trading automation;
success does not establish profitable alpha or create research, paper-trading,
live-trading, capital, ML, or autonomous authority.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.mission_control import (
    CAPITAL_DEPLOYMENT_REQUIRED_STATUS,
    LIVE_TRADING_REQUIRED_STATUS,
    MISSION_CONTROL_FAIL,
    MISSION_CONTROL_PASS,
    build_verification_plan,
    command_to_text,
    ensure_log_dir,
    run_command,
    safe_label,
    write_text,
)


PACK_RUNNER_PASS = "MISSION_PACK_RUNNER_PASS"
PACK_RUNNER_FAIL = "MISSION_PACK_RUNNER_FAIL"
PACK_RUNNER_DRY_RUN = "MISSION_PACK_RUNNER_DRY_RUN"

DEFAULT_LOG_DIR = Path("reports/mission_logs")

FORBIDDEN_PATH_PARTS = {
    ".git",
    ".env",
    ".ssh",
    ".aws",
    ".gcp",
    "id_rsa",
    "id_ed25519",
}

FORBIDDEN_CONTENT_PATTERNS = {
    "BEGIN PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
    "PRIVATE_KEY=",
    "PRIVATE_KEY =",
    "LIVE_TRADING_ENABLED = True",
    "LIVE_TRADING_ENABLED=True",
    "ENABLE_LIVE_TRADING = True",
    "ENABLE_LIVE_TRADING=True",
    "send_order(",
    "create_order(",
    "sign_transaction(",
    "broadcast_transaction(",
}


@dataclass(frozen=True)
class FileActionResult:
    """Record the outcome of one declared repository file action."""

    path: str
    action: str
    changed: bool
    bytes_written: int
    reason: str


@dataclass(frozen=True)
class GitActionResult:
    """Record the captured outcome of one local Git command."""

    name: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        """Return whether the Git command completed with exit code zero."""

        return self.returncode == 0


def utc_now() -> str:
    """Return the current UTC time as a seconds-precision ISO 8601 string."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def pushd(path: str | Path):
    """Temporarily change the process working directory.

    Args:
        path: Directory used for the duration of the context.

    Yields:
        Control while the process is in the requested directory.

    Raises:
        OSError: If either directory change fails.
    """

    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def read_json(path: str | Path) -> dict[str, Any]:
    """Read and parse a UTF-8 JSON object from a local file.

    Args:
        path: JSON file to read.

    Returns:
        The parsed object expected by mission-pack validation.

    Raises:
        OSError: If the file cannot be read.
        json.JSONDecodeError: If the file is not valid JSON.
    """

    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    """Write a mapping as stable, indented UTF-8 JSON.

    Args:
        path: Local file to create or replace.
        payload: JSON-serializable mapping to write.

    Raises:
        OSError: If the destination cannot be written.
        TypeError: If the payload contains a non-serializable value.
    """

    write_text(path, json.dumps(payload, indent=2, sort_keys=True))


def is_safe_relative_path(path_text: str) -> bool:
    """Check whether a path is an allowed repository-relative path.

    Args:
        path_text: Path text to check without touching the filesystem.

    Returns:
        ``True`` only for a non-empty relative path with no traversal or
        forbidden path component.
    """

    path = Path(path_text)

    if path.is_absolute():
        return False

    parts = set(path.parts)

    if ".." in parts:
        return False

    if parts.intersection(FORBIDDEN_PATH_PARTS):
        return False

    if path_text.strip() == "":
        return False

    return True


def resolve_pack_path(repo_root: str | Path, relative_path: str) -> Path:
    """Resolve an approved relative path beneath a repository root.

    Args:
        repo_root: Repository directory that must contain the result.
        relative_path: Declared path from a validated mission pack.

    Returns:
        The resolved local target path.

    Raises:
        ValueError: If the path is unsafe or resolves outside the repository.
    """

    if not is_safe_relative_path(relative_path):
        raise ValueError(f"unsafe path rejected: {relative_path}")

    root = Path(repo_root).resolve()
    resolved = (root / relative_path).resolve()

    if root != resolved and root not in resolved.parents:
        raise ValueError(f"path escapes repo root: {relative_path}")

    return resolved


def scan_content_forbidden_patterns(content: str) -> list[str]:
    """Find forbidden credential, live-operation, or signing patterns in text.

    Args:
        content: Proposed file content to scan.

    Returns:
        Matching forbidden patterns in deterministic sorted order.
    """

    return [
        pattern
        for pattern in sorted(FORBIDDEN_CONTENT_PATTERNS)
        if pattern in content
    ]


def validate_file_action(action: dict[str, Any]) -> None:
    """Validate one declared overwrite or append-once file action.

    Args:
        action: Mission-pack file action to validate.

    Raises:
        ValueError: If its mode, path, marker, or content is unsafe or invalid.
    """

    path = str(action.get("path", ""))
    content = str(action.get("content", ""))
    mode = str(action.get("mode", "overwrite"))

    if mode not in {"overwrite", "append_once"}:
        raise ValueError(f"unsupported file action mode: {mode}")

    if not is_safe_relative_path(path):
        raise ValueError(f"unsafe file action path: {path}")

    forbidden = scan_content_forbidden_patterns(content)

    if forbidden:
        raise ValueError(f"forbidden content pattern found in {path}: {forbidden}")

    if mode == "append_once" and not str(action.get("marker", "")).strip():
        raise ValueError(f"append_once action requires marker: {path}")


def validate_pack(pack: dict[str, Any]) -> None:
    """Validate mission identity, file actions, and declared repository paths.

    Args:
        pack: Parsed mission-pack object.

    Raises:
        ValueError: If the pack shape, required mission, file actions, commit
            paths, or verification paths are invalid.
    """

    if not isinstance(pack, dict):
        raise ValueError("mission pack must be a JSON object")

    if not str(pack.get("mission", "")).strip():
        raise ValueError("mission pack requires mission")

    for key in ["code_files", "docs_files"]:
        for action in pack.get(key, []):
            validate_file_action(action)

    for key in ["code_commit_paths", "docs_commit_paths"]:
        for path in pack.get(key, []):
            if not is_safe_relative_path(str(path)):
                raise ValueError(f"unsafe commit path in {key}: {path}")

    verification = pack.get("verification", {})

    for key in ["module_file", "test_file", "mission_test"]:
        value = verification.get(key)
        if value is not None and not is_safe_relative_path(str(value)):
            raise ValueError(f"unsafe verification path {key}: {value}")


def render_template(text: str, context: dict[str, Any]) -> str:
    """Replace brace-delimited context keys in text.

    Args:
        text: Template text to render.
        context: Keys and values substituted by literal string replacement.

    Returns:
        Rendered text; unknown placeholders remain unchanged.
    """

    rendered = text

    for key, value in context.items():
        rendered = rendered.replace("{" + key + "}", str(value))

    return rendered


def apply_file_action(
    repo_root: str | Path,
    action: dict[str, Any],
    context: dict[str, Any],
    dry_run: bool = False,
) -> FileActionResult:
    """Preview or apply one validated repository file action.

    Args:
        repo_root: Repository directory that must contain the target.
        action: Declared overwrite or append-once action.
        context: Values available to the action's text template.
        dry_run: Whether to summarize the action without writing its target.

    Returns:
        The declared path, mode, change state, byte count, and reason.

    Raises:
        ValueError: If the action or resolved path is unsafe or invalid.
        OSError: If a required local file or directory operation fails.
    """

    validate_file_action(action)

    relative_path = str(action["path"])
    mode = str(action.get("mode", "overwrite"))
    content = render_template(str(action.get("content", "")), context)
    target = resolve_pack_path(repo_root, relative_path)

    if dry_run:
        return FileActionResult(
            path=relative_path,
            action=mode,
            changed=False,
            bytes_written=len(content.encode("utf-8")),
            reason="dry-run",
        )

    target.parent.mkdir(parents=True, exist_ok=True)

    if mode == "overwrite":
        old = target.read_text(encoding="utf-8") if target.exists() else None
        changed = old != content
        target.write_text(content, encoding="utf-8")

        return FileActionResult(
            path=relative_path,
            action=mode,
            changed=changed,
            bytes_written=len(content.encode("utf-8")),
            reason="written" if changed else "unchanged-content-rewritten",
        )

    marker = str(action["marker"])
    existing = target.read_text(encoding="utf-8") if target.exists() else ""

    if marker in existing:
        return FileActionResult(
            path=relative_path,
            action=mode,
            changed=False,
            bytes_written=0,
            reason="marker-already-present",
        )

    next_text = existing.rstrip() + "\n\n" + content.strip() + "\n"
    target.write_text(next_text, encoding="utf-8")

    return FileActionResult(
        path=relative_path,
        action=mode,
        changed=True,
        bytes_written=len(content.encode("utf-8")),
        reason="appended",
    )


def git_status_short(repo_root: str | Path) -> str:
    """Return stripped ``git status --short`` output for a repository.

    Args:
        repo_root: Repository in which to inspect status.

    Returns:
        Short status text, or an empty string for a clean tree.

    Raises:
        RuntimeError: If the Git status command fails.
    """

    completed = subprocess.run(
        ["git", "status", "--short"],
        cwd=str(repo_root),
        text=True,
        capture_output=True,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git status failed")

    return completed.stdout.strip()


def relative_to_repo(repo_root: str | Path, target: str | Path) -> str | None:
    """Express a target as a repository-relative POSIX path when possible.

    Args:
        repo_root: Repository directory used as the boundary.
        target: Local path to classify.

    Returns:
        A relative POSIX path, or ``None`` when the target is outside the root.
    """

    root = Path(repo_root).resolve()
    resolved = Path(target).resolve()

    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return None


def untracked_directory_contains_only_allowed_files(
    repo_root: str | Path,
    status_path: str,
    allowed_paths: set[str],
) -> bool:
    """Check whether an untracked directory contains only allowed files.

    Args:
        repo_root: Repository containing the untracked status path.
        status_path: Directory path reported by short Git status.
        allowed_paths: Exact repository-relative files allowed for this check.

    Returns:
        ``True`` when the directory exists, contains files, and every file is
        explicitly allowed.
    """

    root = Path(repo_root).resolve()
    directory = (root / status_path).resolve()

    if not directory.exists() or not directory.is_dir():
        return False

    files = {
        item.relative_to(root).as_posix()
        for item in directory.rglob("*")
        if item.is_file()
    }

    return bool(files) and files.issubset(allowed_paths)


def git_status_short_ignoring_allowed_untracked_paths(
    repo_root: str | Path,
    allowed_paths: set[str],
) -> str:
    """Filter explicitly allowed untracked files from short Git status.

    Args:
        repo_root: Repository whose status is inspected.
        allowed_paths: Exact untracked files that may be ignored.

    Returns:
        Remaining blocking status lines, or an empty string.

    Raises:
        RuntimeError: If the underlying Git status command fails.
    """

    status = git_status_short(repo_root)

    if not status:
        return ""

    blocked_lines: list[str] = []

    for line in status.splitlines():
        code = line[:2]
        path_text = line[3:].strip()

        if code == "??":
            normalized = path_text.rstrip("/")

            if normalized in allowed_paths:
                continue

            if untracked_directory_contains_only_allowed_files(
                repo_root=repo_root,
                status_path=path_text,
                allowed_paths=allowed_paths,
            ):
                continue

        blocked_lines.append(line)

    return "\n".join(blocked_lines)


def git_action(repo_root: str | Path, command: list[str]) -> GitActionResult:
    """Run a supplied local Git command and capture its result.

    Args:
        repo_root: Repository used as the subprocess working directory.
        command: Complete Git argument vector selected by the caller.

    Returns:
        Captured command, exit status, standard output, and standard error.
    """

    completed = subprocess.run(
        command,
        cwd=str(repo_root),
        text=True,
        capture_output=True,
        check=False,
    )

    return GitActionResult(
        name=command_to_text(command),
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def git_commit(
    repo_root: str | Path,
    paths: list[str],
    message: str,
) -> GitActionResult:
    """Stage declared paths and create one local commit when changes exist.

    This operation may run ``git add`` and ``git commit`` in the repository.

    Args:
        repo_root: Repository in which to stage and commit.
        paths: Exact paths declared by the reviewed mission pack.
        message: Commit message passed to Git.

    Returns:
        The failed stage result, commit result, or a successful skipped/no-change
        result.
    """

    if not paths:
        return GitActionResult(
            name="git-commit-skipped",
            command=[],
            returncode=0,
            stdout="No paths supplied; commit skipped.",
            stderr="",
        )

    add_result = git_action(repo_root, ["git", "add", *paths])

    if not add_result.passed:
        return add_result

    commit_result = git_action(repo_root, ["git", "commit", "-m", message])

    if commit_result.returncode != 0 and "nothing to commit" in (
        commit_result.stdout + commit_result.stderr
    ):
        return GitActionResult(
            name="git-commit-no-changes",
            command=["git", "commit", "-m", message],
            returncode=0,
            stdout=commit_result.stdout,
            stderr=commit_result.stderr,
        )

    return commit_result


def git_latest_short_commit(repo_root: str | Path) -> str:
    """Return the latest short commit description for a repository.

    Args:
        repo_root: Repository in which to run the read-only Git log command.

    Returns:
        The latest ``<short-hash> <subject>`` text, or ``UNKNOWN_COMMIT`` when
        Git cannot provide it.
    """

    completed = subprocess.run(
        ["git", "log", "--format=%h %s", "-1"],
        cwd=str(repo_root),
        text=True,
        capture_output=True,
        check=False,
    )

    if completed.returncode != 0:
        return "UNKNOWN_COMMIT"

    return completed.stdout.strip()


def run_pack_verification(
    repo_root: str | Path,
    mission: str,
    verification: dict[str, Any],
    log_dir: str | Path,
) -> dict[str, Any]:
    """Run a mission pack's local verification plan until completion or failure.

    Args:
        repo_root: Repository used by commands and Git status checks.
        mission: Label used for per-command log filenames.
        verification: Pack fields used to build the verification plan.
        log_dir: Directory that receives per-command logs.

    Returns:
        A JSON-serializable result count, verdict, and structured command list.

    Raises:
        OSError: If a subprocess cannot start or a command log cannot be written.
        ValueError: If an optional mission command cannot be parsed.
    """

    plan = build_verification_plan(
        module_file=verification.get("module_file"),
        test_file=verification.get("test_file"),
        mission_test=verification.get("mission_test"),
        mission_command=verification.get("mission_command"),
        skip_full_suite=bool(verification.get("skip_full_suite", False)),
    )

    results = []

    for name, command in plan:
        result = run_command(
            name=name,
            command=command,
            cwd=repo_root,
            log_dir=log_dir,
            log_prefix=safe_label(mission),
        )
        results.append(result)

        if not result.passed:
            break

    failed = [item for item in results if not item.passed]

    return {
        "command_count": len(results),
        "passed_count": sum(1 for item in results if item.passed),
        "failed_count": len(failed),
        "failed_commands": [item.name for item in failed],
        "global_verdict": MISSION_CONTROL_FAIL if failed else MISSION_CONTROL_PASS,
        "results": [asdict(item) for item in results],
    }


def run_mission_pack(
    pack_path: str | Path,
    repo_root: str | Path = ".",
    dry_run: bool = False,
    commit: bool = False,
    push: bool = False,
    require_clean_start: bool = True,
) -> dict[str, Any]:
    """Validate, preview, or apply a reviewed local mission pack.

    Args:
        pack_path: JSON mission pack to read and validate.
        repo_root: Repository whose declared files and logs may be updated.
        dry_run: Whether to avoid declared file actions and verification commands
            while still writing a local summary.
        commit: Whether to commit only paths declared by the pack after successful
            verification.
        push: Whether to run ``git push origin main`` after preceding stages.
        require_clean_start: Whether unrelated working-tree changes stop the pack
            before declared actions.

    Returns:
        The JSON-serializable pack summary also written to ``summary.json``.

    Raises:
        ValueError: If the pack or a declared path or action is invalid.
        OSError: If local files, logs, or subprocesses cannot be accessed.
        json.JSONDecodeError: If the pack is not valid JSON.
    """

    repo = Path(repo_root).resolve()
    pack = read_json(pack_path)
    validate_pack(pack)

    mission = str(pack["mission"])
    mission_label = safe_label(mission)
    created_at = utc_now()
    run_id = uuid.uuid4().hex[:8]
    log_dir = ensure_log_dir(repo / DEFAULT_LOG_DIR / f"{mission_label}-{run_id}")

    context: dict[str, Any] = {
        "mission": mission,
        "created_at": created_at,
        "code_commit": "UNCOMMITTED_CODE",
        "docs_commit": "UNCOMMITTED_DOCS",
    }

    summary: dict[str, Any] = {
        "mission": mission,
        "created_at": created_at,
        "pack_path": str(pack_path),
        "repo_root": str(repo),
        "log_dir": str(log_dir),
        "dry_run": dry_run,
        "commit_requested": commit,
        "push_requested": push,
        "require_clean_start": require_clean_start,
        "live_trading_required_status": LIVE_TRADING_REQUIRED_STATUS,
        "capital_deployment_required_status": CAPITAL_DEPLOYMENT_REQUIRED_STATUS,
        "code_file_results": [],
        "docs_file_results": [],
        "git_actions": [],
        "verification": {},
    }

    if require_clean_start:
        allowed_paths: set[str] = set()
        pack_relative_path = relative_to_repo(repo, pack_path)

        if pack_relative_path is not None:
            allowed_paths.add(pack_relative_path)

        status = git_status_short_ignoring_allowed_untracked_paths(
            repo_root=repo,
            allowed_paths=allowed_paths,
        )

        if status:
            summary.update(
                {
                    "global_verdict": PACK_RUNNER_FAIL,
                    "recommended_action": "CLEAN_OR_COMMIT_WORKING_TREE_BEFORE_RUNNING_PACK",
                    "failed_stage": "clean-start",
                    "git_status_short": status,
                    "allowed_untracked_paths": sorted(allowed_paths),
                }
            )
            write_json(log_dir / "summary.json", summary)
            return summary

    if dry_run:
        summary["code_file_results"] = [
            asdict(apply_file_action(repo, action, context, dry_run=True))
            for action in pack.get("code_files", [])
        ]
        summary["docs_file_results"] = [
            asdict(apply_file_action(repo, action, context, dry_run=True))
            for action in pack.get("docs_files", [])
        ]
        summary["verification_plan"] = [
            {"name": name, "command": command}
            for name, command in build_verification_plan(
                module_file=pack.get("verification", {}).get("module_file"),
                test_file=pack.get("verification", {}).get("test_file"),
                mission_test=pack.get("verification", {}).get("mission_test"),
                mission_command=pack.get("verification", {}).get("mission_command"),
                skip_full_suite=bool(pack.get("verification", {}).get("skip_full_suite", False)),
            )
        ]
        summary["global_verdict"] = PACK_RUNNER_DRY_RUN
        summary["recommended_action"] = "REVIEW_MISSION_PACK_DRY_RUN"
        write_json(log_dir / "summary.json", summary)
        return summary

    code_results = [
        apply_file_action(repo, action, context, dry_run=False)
        for action in pack.get("code_files", [])
    ]
    summary["code_file_results"] = [asdict(item) for item in code_results]

    verification_summary = run_pack_verification(
        repo_root=repo,
        mission=mission,
        verification=pack.get("verification", {}),
        log_dir=log_dir,
    )
    summary["verification"] = verification_summary

    if verification_summary["failed_count"] > 0:
        summary.update(
            {
                "global_verdict": PACK_RUNNER_FAIL,
                "recommended_action": "STOP_AND_FIX_VERIFICATION_FAILURE",
                "failed_stage": "verification",
            }
        )
        write_json(log_dir / "summary.json", summary)
        return summary

    if commit:
        code_commit_result = git_commit(
            repo_root=repo,
            paths=[str(path) for path in pack.get("code_commit_paths", [])],
            message=str(pack.get("code_commit_message", f"Add {mission}")),
        )
        summary["git_actions"].append(asdict(code_commit_result))

        if not code_commit_result.passed:
            summary.update(
                {
                    "global_verdict": PACK_RUNNER_FAIL,
                    "recommended_action": "STOP_AND_FIX_CODE_COMMIT_FAILURE",
                    "failed_stage": "code-commit",
                }
            )
            write_json(log_dir / "summary.json", summary)
            return summary

        context["code_commit"] = git_latest_short_commit(repo)

    docs_results = [
        apply_file_action(repo, action, context, dry_run=False)
        for action in pack.get("docs_files", [])
    ]
    summary["docs_file_results"] = [asdict(item) for item in docs_results]

    if commit and pack.get("docs_files"):
        docs_commit_result = git_commit(
            repo_root=repo,
            paths=[str(path) for path in pack.get("docs_commit_paths", [])],
            message=str(pack.get("docs_commit_message", f"Document {mission}")),
        )
        summary["git_actions"].append(asdict(docs_commit_result))

        if not docs_commit_result.passed:
            summary.update(
                {
                    "global_verdict": PACK_RUNNER_FAIL,
                    "recommended_action": "STOP_AND_FIX_DOCS_COMMIT_FAILURE",
                    "failed_stage": "docs-commit",
                }
            )
            write_json(log_dir / "summary.json", summary)
            return summary

        context["docs_commit"] = git_latest_short_commit(repo)

    if push:
        push_result = git_action(repo, ["git", "push", "origin", "main"])
        summary["git_actions"].append(asdict(push_result))

        if not push_result.passed:
            summary.update(
                {
                    "global_verdict": PACK_RUNNER_FAIL,
                    "recommended_action": "STOP_AND_FIX_PUSH_FAILURE",
                    "failed_stage": "push",
                }
            )
            write_json(log_dir / "summary.json", summary)
            return summary

    final_status = git_status_short(repo)
    summary["final_git_status_short"] = final_status
    summary["global_verdict"] = PACK_RUNNER_PASS
    summary["recommended_action"] = "MISSION_PACK_APPLIED_REVIEW_FINAL_OUTPUTS"

    write_json(log_dir / "summary.json", summary)

    return summary


def main() -> None:
    """Run the ``run`` CLI and print its machine-readable JSON summary.

    A normal invocation may apply declared repository file actions and execute
    local verification. Commit and push occur only when their explicit flags
    are present. Argparse exits with its standard status for help or invalid
    input; pack outcomes remain encoded in the printed summary.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Apply a local DeltaGrid mission-pack JSON file and run its software-verification "
            "plan. The command can write repository files and local logs; it does not create "
            "research or trading authorization."
        ),
        epilog=(
            "A successful pack run verifies only the requested software steps. It does not "
            "establish profitable alpha. Paper trading is not currently authorized; live "
            "trading, ML operation, and autonomous execution are not authorized; capital "
            "deployment is blocked."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser(
        "run",
        help="Apply a local mission pack and run its verification plan.",
        description=(
            "Validate the pack, apply its code and documentation file actions, run local "
            "verification, and perform only the explicitly requested Git actions."
        ),
        epilog=(
            "A successful run does not establish profitable alpha or change the current "
            "boundary: paper trading is not currently authorized; live trading, ML operation, "
            "and autonomous execution are not authorized; capital deployment is blocked."
        ),
    )
    run.add_argument(
        "--pack",
        required=True,
        help="Path to the mission-pack JSON file to read and validate.",
    )
    run.add_argument(
        "--repo-root",
        default=".",
        help="Repository whose files and local logs the pack may update (default: current directory).",
    )
    run.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate and summarize the pack without applying its file actions or running its "
            "commands; summary.json is still written under reports/mission_logs."
        ),
    )
    run.add_argument(
        "--commit",
        action="store_true",
        help="Commit only the code and documentation paths declared by the pack after verification.",
    )
    run.add_argument(
        "--push",
        action="store_true",
        help="Run 'git push origin main' after the pack and requested commits succeed.",
    )
    run.add_argument(
        "--no-clean-start",
        action="store_true",
        help="Allow the pack to start without the default clean working tree requirement.",
    )

    args = parser.parse_args()

    if args.command == "run":
        summary = run_mission_pack(
            pack_path=args.pack,
            repo_root=args.repo_root,
            dry_run=args.dry_run,
            commit=args.commit,
            push=args.push,
            require_clean_start=not args.no_clean_start,
        )
        print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
