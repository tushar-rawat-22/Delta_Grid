import sys

from scripts.mission_control import (
    CAPITAL_DEPLOYMENT_REQUIRED_STATUS,
    LIVE_TRADING_REQUIRED_STATUS,
    MISSION_CONTROL_DRY_RUN,
    MISSION_CONTROL_FAIL,
    MISSION_CONTROL_PASS,
    build_verification_plan,
    command_to_text,
    run_command,
    run_verification,
    safe_label,
)


def test_safe_label_removes_unsafe_characters():
    assert safe_label("Mission 41: Local Harness") == "Mission-41--Local-Harness"
    assert safe_label("mission_41.ok") == "mission_41.ok"


def test_command_to_text_quotes_arguments():
    text = command_to_text(["python", "-c", "print('hello world')"])

    assert text.startswith("python -c")
    assert "hello" in text


def test_run_command_success_writes_log(tmp_path):
    result = run_command(
        name="success",
        command=[sys.executable, "-c", "print('ok')"],
        log_dir=tmp_path,
        log_prefix="mission41",
    )

    assert result.passed is True
    assert result.returncode == 0
    assert "ok" in result.stdout
    assert result.log_path is not None
    assert "returncode: 0" in open(result.log_path, encoding="utf-8").read()


def test_run_command_failure_is_captured(tmp_path):
    result = run_command(
        name="failure",
        command=[sys.executable, "-c", "import sys; print('bad'); sys.exit(7)"],
        log_dir=tmp_path,
        log_prefix="mission41",
    )

    assert result.passed is False
    assert result.returncode == 7
    assert "bad" in result.stdout
    assert result.log_path is not None


def test_build_verification_plan_contains_expected_steps():
    plan = build_verification_plan(
        module_file="scripts/mission_control.py",
        test_file="offchain/tests/test_mission_control.py",
        mission_test="offchain/tests/test_mission_control.py",
        mission_command="python -m scripts.mission_control verify --mission dry --dry-run",
        skip_full_suite=False,
    )

    names = [name for name, _ in plan]

    assert names == [
        "compile-module",
        "compile-test",
        "mission-tests",
        "full-offchain-suite",
        "mission-command",
        "git-status-short",
        "git-status",
    ]


def test_run_verification_dry_run_does_not_execute_real_commands(tmp_path):
    summary = run_verification(
        mission="mission41-dry-run",
        module_file="missing_module_should_not_run.py",
        test_file="missing_test_should_not_run.py",
        mission_test="missing_pytest_should_not_run.py",
        mission_command="python missing_command_should_not_run.py",
        log_dir=tmp_path,
        dry_run=True,
    )

    assert summary["dry_run"] is True
    assert summary["global_verdict"] == MISSION_CONTROL_DRY_RUN
    assert summary["failed_count"] == 0
    assert summary["command_count"] == 7
    assert summary["live_trading_required_status"] == LIVE_TRADING_REQUIRED_STATUS
    assert summary["capital_deployment_required_status"] == CAPITAL_DEPLOYMENT_REQUIRED_STATUS


def test_run_verification_passes_small_real_plan(tmp_path):
    summary = run_verification(
        mission="mission41-small-pass",
        module_file="scripts/mission_control.py",
        test_file="offchain/tests/test_mission_control.py",
        mission_test=None,
        mission_command=f"{sys.executable} -c \"print('mission-control-ok')\"",
        log_dir=tmp_path,
        skip_full_suite=True,
    )

    assert summary["global_verdict"] == MISSION_CONTROL_PASS
    assert summary["failed_count"] == 0
    assert summary["passed_count"] == 5


def test_run_verification_stops_on_failure(tmp_path):
    summary = run_verification(
        mission="mission41-small-fail",
        module_file="scripts/mission_control.py",
        test_file="offchain/tests/test_mission_control.py",
        mission_test=None,
        mission_command=f"{sys.executable} -c \"import sys; sys.exit(9)\"",
        log_dir=tmp_path,
        skip_full_suite=True,
    )

    assert summary["global_verdict"] == MISSION_CONTROL_FAIL
    assert summary["failed_count"] == 1
    assert summary["failed_commands"] == ["mission-command"]
