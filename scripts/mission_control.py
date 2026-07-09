"""
Mission 41: Local Mission Automation Harness.

This module automates local mission verification.

It is a development automation layer, not a trading automation layer.

It never:
- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_LOG_DIR = Path("reports/mission_logs")
LIVE_TRADING_REQUIRED_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_REQUIRED_STATUS = "BLOCKED"

MISSION_CONTROL_PASS = "MISSION_CONTROL_PASS"
MISSION_CONTROL_FAIL = "MISSION_CONTROL_FAIL"
MISSION_CONTROL_DRY_RUN = "MISSION_CONTROL_DRY_RUN"


@dataclass(frozen=True)
class CommandResult:
    name: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    log_path: str | None

    @property
    def passed(self) -> bool:
        return self.returncode == 0


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_label(value: str) -> str:
    allowed = []
    for char in value:
        if char.isalnum() or char in {"-", "_", "."}:
            allowed.append(char)
        else:
            allowed.append("-")
    return "".join(allowed).strip("-") or "mission"


def ensure_log_dir(log_dir: str | Path = DEFAULT_LOG_DIR) -> Path:
    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_text(path: str | Path, text: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def command_to_text(command: Iterable[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in command)


def run_command(
    name: str,
    command: list[str],
    cwd: str | Path = ".",
    log_dir: str | Path = DEFAULT_LOG_DIR,
    log_prefix: str = "mission",
) -> CommandResult:
    started = datetime.now(timezone.utc)

    completed = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )

    ended = datetime.now(timezone.utc)
    duration = round((ended - started).total_seconds(), 6)

    log_path = ensure_log_dir(log_dir) / f"{safe_label(log_prefix)}-{safe_label(name)}.log"

    log_body = "\n".join(
        [
            f"name: {name}",
            f"command: {command_to_text(command)}",
            f"returncode: {completed.returncode}",
            f"started_at: {started.replace(microsecond=0).isoformat()}",
            f"ended_at: {ended.replace(microsecond=0).isoformat()}",
            f"duration_seconds: {duration}",
            "",
            "STDOUT:",
            completed.stdout,
            "",
            "STDERR:",
            completed.stderr,
            "",
        ]
    )

    write_text(log_path, log_body)

    return CommandResult(
        name=name,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        duration_seconds=duration,
        log_path=str(log_path),
    )


def build_verification_plan(
    module_file: str | None,
    test_file: str | None,
    mission_test: str | None,
    mission_command: str | None,
    skip_full_suite: bool,
) -> list[tuple[str, list[str]]]:
    plan: list[tuple[str, list[str]]] = []

    if module_file:
        plan.append(("compile-module", [sys.executable, "-m", "py_compile", module_file]))

    if test_file:
        plan.append(("compile-test", [sys.executable, "-m", "py_compile", test_file]))

    if mission_test:
        plan.append(("mission-tests", [sys.executable, "-m", "pytest", mission_test, "-q"]))

    if not skip_full_suite:
        plan.append(("full-offchain-suite", [sys.executable, "-m", "pytest", "offchain/tests", "-q"]))

    if mission_command:
        plan.append(("mission-command", shlex.split(mission_command)))

    plan.append(("git-status-short", ["git", "status", "--short"]))
    plan.append(("git-status", ["git", "status"]))

    return plan


def assert_git_clean_before_start(cwd: str | Path = ".") -> tuple[bool, str]:
    completed = subprocess.run(
        ["git", "status", "--short"],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )

    if completed.returncode != 0:
        return False, completed.stderr.strip() or "git status failed"

    if completed.stdout.strip():
        return False, completed.stdout.strip()

    return True, "working tree clean"


def summarize_results(
    mission: str,
    created_at: str,
    log_dir: str | Path,
    results: list[CommandResult],
    dry_run: bool = False,
) -> dict:
    failed = [item for item in results if not item.passed]

    if dry_run:
        verdict = MISSION_CONTROL_DRY_RUN
        recommended_action = "REVIEW_DRY_RUN_PLAN"
    elif failed:
        verdict = MISSION_CONTROL_FAIL
        recommended_action = "STOP_AND_FIX_FAILED_COMMANDS"
    else:
        verdict = MISSION_CONTROL_PASS
        recommended_action = "MISSION_VERIFICATION_PASSED_REVIEW_OUTPUTS"

    return {
        "mission": mission,
        "created_at": created_at,
        "log_dir": str(log_dir),
        "dry_run": dry_run,
        "command_count": len(results),
        "passed_count": sum(1 for item in results if item.passed),
        "failed_count": len(failed),
        "failed_commands": [item.name for item in failed],
        "live_trading_required_status": LIVE_TRADING_REQUIRED_STATUS,
        "capital_deployment_required_status": CAPITAL_DEPLOYMENT_REQUIRED_STATUS,
        "global_verdict": verdict,
        "recommended_action": recommended_action,
        "results": [asdict(item) for item in results],
    }


def run_verification(
    mission: str,
    module_file: str | None = None,
    test_file: str | None = None,
    mission_test: str | None = None,
    mission_command: str | None = None,
    log_dir: str | Path = DEFAULT_LOG_DIR,
    skip_full_suite: bool = False,
    require_clean_start: bool = False,
    dry_run: bool = False,
) -> dict:
    created_at = utc_now()
    mission_label = safe_label(mission)
    run_id = uuid.uuid4().hex[:8]
    log_path = ensure_log_dir(log_dir) / f"{mission_label}-{run_id}"
    log_path.mkdir(parents=True, exist_ok=True)

    if require_clean_start:
        clean, detail = assert_git_clean_before_start()
        if not clean:
            summary = {
                "mission": mission,
                "created_at": created_at,
                "log_dir": str(log_path),
                "dry_run": dry_run,
                "command_count": 0,
                "passed_count": 0,
                "failed_count": 1,
                "failed_commands": ["git-clean-start"],
                "live_trading_required_status": LIVE_TRADING_REQUIRED_STATUS,
                "capital_deployment_required_status": CAPITAL_DEPLOYMENT_REQUIRED_STATUS,
                "global_verdict": MISSION_CONTROL_FAIL,
                "recommended_action": "CLEAN_OR_COMMIT_WORKING_TREE_BEFORE_RUNNING_AUTOMATION",
                "git_clean_start_detail": detail,
                "results": [],
            }
            write_text(log_path / "summary.json", json.dumps(summary, indent=2, sort_keys=True))
            return summary

    plan = build_verification_plan(
        module_file=module_file,
        test_file=test_file,
        mission_test=mission_test,
        mission_command=mission_command,
        skip_full_suite=skip_full_suite,
    )

    if dry_run:
        results = [
            CommandResult(
                name=name,
                command=command,
                returncode=0,
                stdout=f"DRY RUN: {command_to_text(command)}",
                stderr="",
                duration_seconds=0.0,
                log_path=None,
            )
            for name, command in plan
        ]

        summary = summarize_results(
            mission=mission,
            created_at=created_at,
            log_dir=log_path,
            results=results,
            dry_run=True,
        )
        write_text(log_path / "summary.json", json.dumps(summary, indent=2, sort_keys=True))
        return summary

    results: list[CommandResult] = []

    for name, command in plan:
        result = run_command(
            name=name,
            command=command,
            cwd=".",
            log_dir=log_path,
            log_prefix=mission_label,
        )
        results.append(result)

        if not result.passed:
            break

    summary = summarize_results(
        mission=mission,
        created_at=created_at,
        log_dir=log_path,
        results=results,
        dry_run=False,
    )

    write_text(log_path / "summary.json", json.dumps(summary, indent=2, sort_keys=True))

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="DeltaGrid local mission automation harness.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify = subparsers.add_parser("verify", help="Run local mission verification.")
    verify.add_argument("--mission", required=True)
    verify.add_argument("--module-file", default=None)
    verify.add_argument("--test-file", default=None)
    verify.add_argument("--mission-test", default=None)
    verify.add_argument("--mission-command", default=None)
    verify.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    verify.add_argument("--skip-full-suite", action="store_true")
    verify.add_argument("--require-clean-start", action="store_true")
    verify.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if args.command == "verify":
        summary = run_verification(
            mission=args.mission,
            module_file=args.module_file,
            test_file=args.test_file,
            mission_test=args.mission_test,
            mission_command=args.mission_command,
            log_dir=args.log_dir,
            skip_full_suite=args.skip_full_suite,
            require_clean_start=args.require_clean_start,
            dry_run=args.dry_run,
        )
        print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
