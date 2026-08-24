from __future__ import annotations

import json
from pathlib import Path

from offchain.orchestration.__main__ import _parser, main
from offchain.safety.operational_release_gate import BLOCKED, READY
from offchain.tests.test_operational_readiness_inspector import _ready_db


def _status_parser():
    parser = _parser()
    subparsers = next(
        action for action in parser._actions if hasattr(action, "choices") and action.choices
    )
    return subparsers.choices["status"]


def test_status_cli_exposes_one_explicit_readonly_readiness_mode() -> None:
    status = _status_parser()
    options = {
        option
        for action in status._actions
        for option in action.option_strings
    }

    assert "--database" in options
    assert "--run-id" in options
    assert "--operational-readiness" in options


def test_readiness_status_returns_verified_non_authorizing_json_without_mutation(
    tmp_path: Path,
    capsys,
) -> None:
    database = tmp_path / "state.db"
    _ready_db(database)
    before_bytes = database.read_bytes()
    before_names = sorted(item.name for item in tmp_path.iterdir())

    returncode = main(
        [
            "status",
            "--database",
            str(database),
            "--operational-readiness",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert returncode == 0
    assert captured.err == ""
    assert payload["inspection_status"] == "VERIFIED"
    assert payload["release"]["status"] == READY
    assert payload["release"]["ready_for_extended_paper"] is True
    assert payload["authority_effect"] == "NONE"
    assert payload["live_trading_allowed"] is False
    assert payload["exchange_access_allowed"] is False
    assert payload["capital_deployment_allowed"] is False
    assert payload["database_mode"] == "READ_ONLY_QUERY_ONLY"
    assert database.read_bytes() == before_bytes
    assert sorted(item.name for item in tmp_path.iterdir()) == before_names


def test_readiness_status_treats_missing_evidence_as_blocked_state_not_cli_failure(
    tmp_path: Path,
    capsys,
) -> None:
    database = tmp_path / "missing.db"

    returncode = main(
        [
            "status",
            "--database",
            str(database),
            "--operational-readiness",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert returncode == 0
    assert captured.err == ""
    assert database.exists() is False
    assert payload["inspection_status"] == "BLOCKED"
    assert payload["release"]["status"] == BLOCKED
    assert payload["release"]["ready_for_extended_paper"] is False
    assert "DATABASE_MISSING_OR_INVALID" in payload["inspector_blockers"]
    assert payload["authority_effect"] == "NONE"


def test_readiness_status_rejects_orchestration_run_selector(capsys) -> None:
    returncode = main(
        [
            "status",
            "--database",
            "ignored.db",
            "--run-id",
            "run-1",
            "--operational-readiness",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert returncode == 2
    assert captured.out == ""
    assert payload["reason_token"] == "WORKFLOW_INPUT_INVALID"
    assert "--run-id cannot be combined" in payload["explanation"]
    assert set(payload) == {"explanation", "reason_token"}
