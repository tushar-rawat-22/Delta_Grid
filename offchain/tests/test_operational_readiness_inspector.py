from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from offchain.safety.operational_readiness_inspector import (
    inspect_operational_readiness,
    main,
)
from offchain.safety.operational_release_gate import BLOCKED, READY


TABLES = {
    "paper": ("paper_sandbox_sessions", "session_label", ()),
    "risk": ("institutional_risk_control_reviews", "review_label", ("risk_decision",)),
    "capital": ("capital_readiness_reviews", "review_label", ("capital_decision",)),
    "kill_switch": (
        "paper_drawdown_kill_switch_reviews",
        "review_label",
        ("kill_switch_decision", "kill_switch_state"),
    ),
}


def _ready_summary(kind: str, *, created_at: str = "2026-08-24T12:00:00+00:00") -> dict:
    common = {
        "created_at": created_at,
        "live_trading": "DISABLED",
        "live_order_sent": 0,
        "capital_deployment": "BLOCKED",
        "safety_breach_count": 0,
    }
    if kind == "paper":
        return {**common, "global_verdict": "PAPER_SANDBOX_READY_SHADOW_ONLY"}
    if kind == "risk":
        return {
            **common,
            "risk_decision": "INSTITUTIONAL_RISK_APPROVED_FOR_CONTROLLED_PAPER_OBSERVATION",
            "global_verdict": "INSTITUTIONAL_RISK_CONTROL_READY_SHADOW_ONLY",
        }
    if kind == "capital":
        return {
            **common,
            "capital_decision": "CAPITAL_READINESS_APPROVED_FOR_EXTENDED_PAPER_OBSERVATION_ONLY",
            "global_verdict": "CAPITAL_READINESS_REVIEW_PAPER_ONLY_READY",
        }
    if kind == "kill_switch":
        return {
            **common,
            "kill_switch_decision": "PAPER_DRAWDOWN_KILL_SWITCH_ARMED_CONTINUE_OBSERVATION",
            "kill_switch_state": "KILL_SWITCH_STATE_ARMED_NOT_TRIGGERED",
            "global_verdict": "PAPER_DRAWDOWN_KILL_SWITCH_ARMED_SHADOW_ONLY",
        }
    raise AssertionError(kind)


def _create_table(connection: sqlite3.Connection, kind: str) -> None:
    table, label, extra = TABLES[kind]
    extra_sql = "".join(f", {name} TEXT NOT NULL" for name in extra)
    connection.execute(
        f"""
        CREATE TABLE {table} (
            {label} TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            global_verdict TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            safety_breach_count INTEGER NOT NULL,
            summary_json TEXT NOT NULL
            {extra_sql}
        )
        """
    )


def _insert(connection: sqlite3.Connection, kind: str, label_value: str, summary: dict, *, raw_json: str | None = None) -> None:
    table, label, extra = TABLES[kind]
    columns = [
        label,
        "created_at",
        "global_verdict",
        "live_trading",
        "live_order_sent",
        "capital_deployment",
        "safety_breach_count",
        "summary_json",
        *extra,
    ]
    values = [
        label_value,
        summary["created_at"],
        summary["global_verdict"],
        summary["live_trading"],
        summary["live_order_sent"],
        summary["capital_deployment"],
        summary["safety_breach_count"],
        raw_json if raw_json is not None else json.dumps(summary, sort_keys=True),
        *(summary[name] for name in extra),
    ]
    placeholders = ",".join("?" for _ in values)
    connection.execute(
        f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
        values,
    )


def _ready_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        for kind in TABLES:
            _create_table(connection, kind)
            _insert(connection, kind, f"{kind}-ready", _ready_summary(kind))
        connection.commit()


def test_valid_persisted_chain_is_ready_and_non_authorizing(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    _ready_db(database)

    result = inspect_operational_readiness(database)

    assert result["inspection_status"] == "VERIFIED"
    assert result["release"]["status"] == READY
    assert result["release"]["ready_for_extended_paper"] is True
    assert result["authority_effect"] == "NONE"
    assert result["live_trading_allowed"] is False
    assert result["exchange_access_allowed"] is False
    assert result["capital_deployment_allowed"] is False
    assert result["database_mode"] == "READ_ONLY_QUERY_ONLY"
    assert set(result["sources"]) == set(TABLES)


def test_newest_row_is_selected_deterministically(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    _ready_db(database)
    with sqlite3.connect(database) as connection:
        newest = _ready_summary("paper", created_at="2026-08-24T13:00:00+00:00")
        _insert(connection, "paper", "paper-newest", newest)
        connection.commit()

    result = inspect_operational_readiness(database)

    assert result["sources"]["paper"]["row_label"] == "paper-newest"
    assert result["sources"]["paper"]["created_at"] == "2026-08-24T13:00:00+00:00"


def test_missing_database_is_not_created_and_blocks(tmp_path: Path) -> None:
    database = tmp_path / "missing.db"

    result = inspect_operational_readiness(database)

    assert database.exists() is False
    assert result["inspection_status"] == "BLOCKED"
    assert result["release"]["status"] == BLOCKED
    assert result["release"]["ready_for_extended_paper"] is False
    assert "DATABASE_MISSING_OR_INVALID" in result["inspector_blockers"]


def test_missing_table_fails_closed(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    _ready_db(database)
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE paper_drawdown_kill_switch_reviews")
        connection.commit()

    result = inspect_operational_readiness(database)

    assert result["release"]["status"] == BLOCKED
    assert result["release"]["ready_for_extended_paper"] is False
    assert result["sources"]["kill_switch"]["status"] == "INVALID_OR_MISSING"
    assert any("TABLE_MISSING" in blocker for blocker in result["inspector_blockers"])


def test_missing_row_fails_closed(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    _ready_db(database)
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM capital_readiness_reviews")
        connection.commit()

    result = inspect_operational_readiness(database)

    assert result["release"]["status"] == BLOCKED
    assert any("ROW_MISSING" in blocker for blocker in result["inspector_blockers"])


def test_malformed_or_non_object_summary_fails_closed(tmp_path: Path) -> None:
    for raw in ("{not-json", "[]", '{"x":1,"x":2}'):
        database = tmp_path / f"state-{len(raw)}.db"
        _ready_db(database)
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE institutional_risk_control_reviews SET summary_json=?",
                (raw,),
            )
            connection.commit()

        result = inspect_operational_readiness(database)
        assert result["release"]["status"] == BLOCKED
        assert result["release"]["ready_for_extended_paper"] is False
        assert result["sources"]["risk"]["status"] == "INVALID_OR_MISSING"


def test_persisted_summary_contradiction_fails_closed(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    _ready_db(database)
    with sqlite3.connect(database) as connection:
        summary = _ready_summary("capital")
        summary["live_order_sent"] = 1
        connection.execute(
            "UPDATE capital_readiness_reviews SET summary_json=?",
            (json.dumps(summary, sort_keys=True),),
        )
        connection.commit()

    result = inspect_operational_readiness(database)

    assert result["release"]["status"] == BLOCKED
    assert any("SUMMARY_CONTRADICTION:live_order_sent" in blocker for blocker in result["inspector_blockers"])


def test_readonly_inspection_does_not_mutate_database_or_directory(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    _ready_db(database)
    before_bytes = database.read_bytes()
    before_names = sorted(item.name for item in tmp_path.iterdir())

    result = inspect_operational_readiness(database)

    assert result["inspection_status"] == "VERIFIED"
    assert database.read_bytes() == before_bytes
    assert sorted(item.name for item in tmp_path.iterdir()) == before_names


def test_cli_is_status_only_by_default_and_can_optionally_require_ready(tmp_path: Path, capsys) -> None:
    database = tmp_path / "state.db"
    _ready_db(database)

    assert main(["--db", str(database)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["release"]["status"] == READY

    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM paper_sandbox_sessions")
        connection.commit()

    assert main(["--db", str(database)]) == 0
    capsys.readouterr()
    assert main(["--db", str(database), "--require-ready"]) == 2


def test_inspector_source_does_not_import_or_call_historical_runners() -> None:
    source = Path(__file__).parents[1] / "safety" / "operational_readiness_inspector.py"
    text = source.read_text(encoding="utf-8")
    for forbidden in (
        "run_paper_trading_sandbox",
        "run_institutional_risk_control",
        "run_capital_readiness_review",
        "run_paper_drawdown_kill_switch",
    ):
        assert forbidden not in text
    assert "mode=ro" in text
    assert "PRAGMA query_only=ON" in text
