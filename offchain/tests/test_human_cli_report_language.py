from __future__ import annotations

import ast
import importlib
import json
import os
import re
import subprocess
import sys
import types
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
BASE_COMMIT = "172691b773949cd6516da65a498989ce81e767a0"
PYTHON = sys.executable

ELIGIBLE_CLI_PATHS = {
    "scripts/mission_control.py",
    "scripts/mission_pack_runner.py",
}
ELIGIBLE_REPORT_RENDERERS = {
    ("scripts/mission_control.py", "run_command"),
}
RECORDED_SURFACE_TESTS = {
    ("scripts/mission_control.py", "main"): {
        "test_human_help_explains_purpose_inputs_outputs_and_dry_run",
        "test_help_preserves_current_authorization_boundaries_and_negative_controls",
    },
    ("scripts/mission_pack_runner.py", "main"): {
        "test_human_help_explains_purpose_inputs_outputs_and_dry_run",
        "test_help_preserves_current_authorization_boundaries_and_negative_controls",
    },
    ("scripts/mission_control.py", "run_command"): {
        "test_success_log_leads_with_outcome_without_strategy_approval",
        "test_failure_log_is_fail_not_reject_or_crash_and_has_next_action",
    },
}
EXPECTED_CHANGED_PATHS = {
    "docs/README.md",
    "offchain/tests/test_human_cli_report_language.py",
    "offchain/tests/test_research_evidence_summaries.py",
    "scripts/mission_control.py",
    "scripts/mission_pack_runner.py",
}


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )


def base_text(path: str) -> str:
    return git("show", f"{BASE_COMMIT}:{path}").stdout


def current_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def normalized(text: str) -> str:
    return " ".join(text.split())


def run_module(module: str, *args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [PYTHON, "-m", module, *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def load_base_module(path: str, module_name: str) -> types.ModuleType:
    module = types.ModuleType(module_name)
    module.__file__ = str(ROOT / path)
    sys.modules[module_name] = module
    exec(compile(base_text(path), module.__file__, "exec"), module.__dict__)
    return module


def parser_contract_calls(text: str) -> list[str]:
    tree = ast.parse(text)
    contracts: list[str] = []
    relevant = {"ArgumentParser", "add_subparsers", "add_parser", "add_argument"}
    human_only_keywords = {"description", "epilog", "help"}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = (
            node.func.attr
            if isinstance(node.func, ast.Attribute)
            else node.func.id
            if isinstance(node.func, ast.Name)
            else ""
        )
        if name not in relevant:
            continue
        copy = ast.Call(
            func=node.func,
            args=node.args,
            keywords=[
                keyword
                for keyword in node.keywords
                if keyword.arg not in human_only_keywords
            ],
        )
        contracts.append(ast.dump(copy, include_attributes=False))

    return contracts


def top_level_function_dumps(text: str) -> dict[str, str]:
    return {
        node.name: ast.dump(node, include_attributes=False)
        for node in ast.parse(text).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def changed_paths() -> set[str]:
    modified = set(git("diff", "--name-only", BASE_COMMIT, "--").stdout.splitlines())
    untracked = set(git("ls-files", "--others", "--exclude-standard").stdout.splitlines())
    return modified | untracked


def assert_no_unsafe_authorization_claim(text: str) -> None:
    lowered = normalized(text).casefold()
    prohibited = {
        "approved for paper trading",
        "live trading is authorized",
        "capital deployment is authorized",
        "ml operation is authorized",
        "autonomous execution is authorized",
        "validated profitability",
        "proven edge",
        "deployment-ready",
        "production trading",
        "institutional-grade",
    }
    found = sorted(phrase for phrase in prohibited if phrase in lowered)
    assert not found, f"unsafe human-facing claim(s): {found}"


def test_locked_manifest_eligible_inventory_is_fully_covered():
    script_sources = {
        path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in (ROOT / "scripts").glob("*.py")
    }
    detected_clis = {
        path for path, text in script_sources.items() if "argparse.ArgumentParser" in text
    }
    detected_logs = {
        (path, node.name)
        for path, text in script_sources.items()
        for node in ast.parse(text).body
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(child, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "log_body" for target in child.targets)
            for child in ast.walk(node)
        )
    }

    assert detected_clis == ELIGIBLE_CLI_PATHS
    assert detected_logs == ELIGIBLE_REPORT_RENDERERS
    assert set(RECORDED_SURFACE_TESTS) == {
        ("scripts/mission_control.py", "main"),
        ("scripts/mission_pack_runner.py", "main"),
        *ELIGIBLE_REPORT_RENDERERS,
    }
    source = current_text("offchain/tests/test_human_cli_report_language.py")
    for tests in RECORDED_SURFACE_TESTS.values():
        assert tests
        assert all(f"def {name}(" in source for name in tests)


def test_cli_parser_contracts_match_base():
    for path in sorted(ELIGIBLE_CLI_PATHS):
        assert parser_contract_calls(current_text(path)) == parser_contract_calls(base_text(path))

    base_cli_paths = {
        path
        for path in git("ls-tree", "-r", "--name-only", BASE_COMMIT).stdout.splitlines()
        if path.endswith(".py")
        and not path.startswith("offchain/tests/")
        and "ArgumentParser" in base_text(path)
    }
    current_cli_paths = {
        path
        for path in git("ls-files", "*.py").stdout.splitlines()
        if not path.startswith("offchain/tests/") and "ArgumentParser" in current_text(path)
    }
    assert current_cli_paths == base_cli_paths


def test_human_help_explains_purpose_inputs_outputs_and_dry_run():
    control = run_module("scripts.mission_control", "verify", "--help")
    pack = run_module("scripts.mission_pack_runner", "run", "--help")

    assert control.returncode == pack.returncode == 0
    assert control.stderr == pack.stderr == ""
    control_help = normalized(control.stdout)
    pack_help = normalized(pack.stdout)

    for phrase in (
        "Compile selected files",
        "Label used to identify this verification run",
        "Parent directory where the JSON summary and command logs are written",
        "without executing them",
        "not run through a shell",
    ):
        assert phrase in control_help

    for phrase in (
        "Path to the mission-pack JSON file to read and validate",
        "Repository whose files and local logs the pack may update",
        "without applying its file actions or running its commands",
        "summary.json is still written",
        "clean working tree requirement",
    ):
        assert phrase in pack_help


def test_help_preserves_current_authorization_boundaries_and_negative_controls():
    text = normalized(
        run_module("scripts.mission_control", "--help").stdout
        + " "
        + run_module("scripts.mission_pack_runner", "--help").stdout
        + " "
        + run_module("scripts.mission_control", "verify", "--help").stdout
        + " "
        + run_module("scripts.mission_pack_runner", "run", "--help").stdout
    )

    assert "does not establish profitable alpha" in text
    assert "Paper trading is not currently authorized" in text
    assert "live trading, ML operation, and autonomous execution are not authorized" in text
    assert "capital deployment is blocked" in text
    assert_no_unsafe_authorization_claim(text)


def test_representative_cli_exit_codes_and_streams_are_preserved(tmp_path):
    control_help = run_module("scripts.mission_control", "--help")
    control_missing = run_module("scripts.mission_control")
    control_required = run_module("scripts.mission_control", "verify")
    control_dry = run_module(
        "scripts.mission_control",
        "verify",
        "--mission",
        "batch5-safe-fixture",
        "--skip-full-suite",
        "--dry-run",
        "--log-dir",
        str(tmp_path / "control-logs"),
    )

    repo = tmp_path / "pack-repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    pack_path = repo / "pack.json"
    pack_path.write_text(
        json.dumps({"mission": "batch5-safe-pack", "verification": {"skip_full_suite": True}}),
        encoding="utf-8",
    )
    pack_help = run_module("scripts.mission_pack_runner", "--help")
    pack_missing = run_module("scripts.mission_pack_runner")
    pack_required = run_module("scripts.mission_pack_runner", "run")
    pack_dry = run_module(
        "scripts.mission_pack_runner",
        "run",
        "--pack",
        str(pack_path),
        "--repo-root",
        str(repo),
        "--dry-run",
    )

    assert [control_help.returncode, control_missing.returncode, control_required.returncode, control_dry.returncode] == [0, 2, 2, 0]
    assert [pack_help.returncode, pack_missing.returncode, pack_required.returncode, pack_dry.returncode] == [0, 2, 2, 0]
    assert control_help.stderr == pack_help.stderr == ""
    assert control_missing.stdout == control_required.stdout == ""
    assert pack_missing.stdout == pack_required.stdout == ""
    assert "required: command" in control_missing.stderr
    assert "required: --mission" in control_required.stderr
    assert "required: command" in pack_missing.stderr
    assert "required: --pack" in pack_required.stderr
    assert json.loads(control_dry.stdout)["global_verdict"] == "MISSION_CONTROL_DRY_RUN"
    assert json.loads(pack_dry.stdout)["global_verdict"] == "MISSION_PACK_RUNNER_DRY_RUN"


def test_mission_control_machine_summary_matches_base(monkeypatch, tmp_path):
    current = importlib.import_module("scripts.mission_control")
    base = load_base_module("scripts/mission_control.py", "_batch5_base_mission_control")
    fixed_time = "2026-07-19T00:00:00+00:00"
    monkeypatch.setattr(current, "utc_now", lambda: fixed_time)
    monkeypatch.setattr(base, "utc_now", lambda: fixed_time)
    monkeypatch.setattr(current.uuid, "uuid4", lambda: SimpleNamespace(hex="12345678abcdef"))

    kwargs = {
        "mission": "batch5-machine-fixture",
        "module_file": "scripts/mission_control.py",
        "test_file": "offchain/tests/test_mission_control.py",
        "mission_test": "offchain/tests/test_mission_control.py",
        "mission_command": "python -c pass",
        "log_dir": tmp_path,
        "skip_full_suite": False,
        "require_clean_start": False,
        "dry_run": True,
    }
    before = base.run_verification(**kwargs)
    after = current.run_verification(**kwargs)

    assert after == before
    assert json.dumps(after, indent=2, sort_keys=True) == json.dumps(before, indent=2, sort_keys=True)
    assert after["command_count"] == 7
    assert after["failed_count"] == 0
    assert after["live_trading_required_status"] == "DISABLED"
    assert after["capital_deployment_required_status"] == "BLOCKED"


def test_mission_pack_machine_summary_matches_base(monkeypatch, tmp_path):
    current = importlib.import_module("scripts.mission_pack_runner")
    base = load_base_module("scripts/mission_pack_runner.py", "_batch5_base_mission_pack_runner")
    fixed_time = "2026-07-19T00:00:00+00:00"
    monkeypatch.setattr(current, "utc_now", lambda: fixed_time)
    monkeypatch.setattr(base, "utc_now", lambda: fixed_time)
    monkeypatch.setattr(current.uuid, "uuid4", lambda: SimpleNamespace(hex="12345678abcdef"))

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    pack_path = repo / "pack.json"
    pack_path.write_text(
        json.dumps(
            {
                "mission": "batch5-machine-pack",
                "code_files": [{"path": "scripts/generated.py", "content": "value = 1\n"}],
                "verification": {"skip_full_suite": True},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    kwargs = {
        "pack_path": pack_path,
        "repo_root": repo,
        "dry_run": True,
        "commit": False,
        "push": False,
        "require_clean_start": False,
    }
    before = base.run_mission_pack(**kwargs)
    after = current.run_mission_pack(**kwargs)

    assert after == before
    assert json.dumps(after, indent=2, sort_keys=True) == json.dumps(before, indent=2, sort_keys=True)
    assert after["global_verdict"] == "MISSION_PACK_RUNNER_DRY_RUN"
    assert after["code_file_results"][0]["bytes_written"] == 10
    assert after["code_file_results"][0]["path"] == "scripts/generated.py"


def test_command_result_and_structured_log_contract_remain_stable(tmp_path):
    control = importlib.import_module("scripts.mission_control")
    result = control.run_command(
        name="structured-success",
        command=[PYTHON, "-c", "print('ok')"],
        log_dir=tmp_path,
        log_prefix="batch5",
    )
    log_path = Path(result.log_path)
    log_text = log_path.read_text(encoding="utf-8")
    field_names = re.findall(
        r"^(name|command|returncode|started_at|ended_at|duration_seconds):",
        log_text,
        flags=re.MULTILINE,
    )

    assert list(asdict(result)) == [
        "name",
        "command",
        "returncode",
        "stdout",
        "stderr",
        "duration_seconds",
        "log_path",
    ]
    assert field_names == ["name", "command", "returncode", "started_at", "ended_at", "duration_seconds"]
    assert "\nSTDOUT:\n" in log_text and "\nSTDERR:\n" in log_text
    assert log_path.name == "batch5-structured-success.log"
    assert log_path.parent == tmp_path
    assert result.returncode == 0
    assert isinstance(result.duration_seconds, float)
    assert result.duration_seconds == round(result.duration_seconds, 6)


def test_success_log_leads_with_outcome_without_strategy_approval(tmp_path):
    control = importlib.import_module("scripts.mission_control")
    result = control.run_command(
        name="passing-check",
        command=[PYTHON, "-c", "print('verified')"],
        log_dir=tmp_path,
    )
    text = Path(result.log_path).read_text(encoding="utf-8")
    compact = normalized(text)

    assert text.startswith("DeltaGrid local verification command log\nOutcome: PASS")
    assert "software verification result, not a research hypothesis decision" in compact
    assert "not" in compact and "evidence of profitable alpha" in compact
    assert "Next safe action:" in text
    assert_no_unsafe_authorization_claim(text)


def test_failure_log_is_fail_not_reject_or_crash_and_has_next_action(tmp_path):
    control = importlib.import_module("scripts.mission_control")
    result = control.run_command(
        name="failing-check",
        command=[PYTHON, "-c", "import sys; print('bad input'); sys.exit(7)"],
        log_dir=tmp_path,
    )
    text = Path(result.log_path).read_text(encoding="utf-8")

    assert "Outcome: FAIL — the command completed with exit code 7." in text
    assert "correct the reported software or input problem, and rerun this check" in normalized(text)
    assert "Outcome: REJECT" not in text
    assert "crash" not in text.casefold()
    assert "returncode: 7" in text
    assert "bad input" in text


def test_documentation_records_review_and_controlling_state():
    text = normalized(current_text("docs/README.md"))

    assert "current local verification CLIs" in text
    assert "plain-text command logs" in text
    assert "machine-readable JSON, contracts, and evidence remain unchanged" in text
    assert "does not establish profitable alpha or authorize paper trading" in text
    assert "research infrastructure is complete" in text
    assert "did not find a validated profitable strategy" in text
    assert "No candidate is selected" in text
    assert "Alpha discovery has stopped" in text
    root_readme = normalized(current_text("README.md"))
    assert "zero scoped validation access and zero scoped holdout access" in root_readme
    assert "Historical next steps" in text and "final freeze" in text
    assert_no_unsafe_authorization_claim(text)


def test_protected_files_and_output_formats_are_unchanged():
    assert changed_paths() == EXPECTED_CHANGED_PATHS

    protected = git("ls-tree", "-r", "--name-only", BASE_COMMIT, "--", "contracts", "docs", "README.md").stdout.splitlines()
    for path in protected:
        if path == "docs/README.md":
            continue
        assert (ROOT / path).read_bytes() == subprocess.run(
            ["git", "show", f"{BASE_COMMIT}:{path}"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout

    assert current_text("docs/documentation-status.json") == base_text("docs/documentation-status.json")
    assert current_text("offchain/requirements.txt") == base_text("offchain/requirements.txt")
    assert not any(path.endswith((".json", ".csv", ".tsv", ".log")) for path in changed_paths())


def test_only_presentation_functions_changed_from_base():
    control_before = top_level_function_dumps(base_text("scripts/mission_control.py"))
    control_after = top_level_function_dumps(current_text("scripts/mission_control.py"))
    pack_before = top_level_function_dumps(base_text("scripts/mission_pack_runner.py"))
    pack_after = top_level_function_dumps(current_text("scripts/mission_pack_runner.py"))

    assert set(control_before) == set(control_after)
    assert set(pack_before) == set(pack_after)
    assert {
        name for name in control_before if control_before[name] != control_after[name]
    } == {"run_command", "main"}
    assert {
        name for name in pack_before if pack_before[name] != pack_after[name]
    } == {"main"}

    for path in ELIGIBLE_CLI_PATHS:
        before = ast.parse(base_text(path))
        after = ast.parse(current_text(path))
        before_runs = [
            ast.dump(node, include_attributes=False)
            for node in ast.walk(before)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
        ]
        after_runs = [
            ast.dump(node, include_attributes=False)
            for node in ast.walk(after)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
        ]
        assert after_runs == before_runs


def test_language_guard_negative_controls_reject_unsafe_claims():
    assert_no_unsafe_authorization_claim(
        "Paper trading is not currently authorized; capital deployment is blocked."
    )

    unsafe_samples = (
        "The strategy is approved for paper trading.",
        "Live trading is authorized after this passing check.",
        "This report proves validated profitability and a proven edge.",
    )
    for sample in unsafe_samples:
        with pytest.raises(AssertionError):
            assert_no_unsafe_authorization_claim(sample)
