"""Atomic Mission 102-specific completion of the existing Mission 94 ledger."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any, Mapping

from offchain.research.admission.models import TrialResultLink
from offchain.research.reopening.admission import _trial_ledger_path, _verify_trial_ledger_file

from .authority import ADMISSION_REASON
from .core import FINALIZER_ID, VERIFIER_ID, DevelopmentRuntimeError, canonical_hash, parse_utc


COMPLETION_REASON = "M102_DEVELOPMENT_RESULT_VERIFIED"


def _event(connection: sqlite3.Connection, *, trial_id: str, sequence: int, timestamp: str) -> None:
    core = {
        "trial_id": trial_id, "sequence_number": sequence,
        "status_token": "COMPLETED", "reason_token": COMPLETION_REASON,
        "event_timestamp": timestamp,
    }
    digest = canonical_hash(core)
    connection.execute(
        "INSERT INTO trial_events(event_id,trial_id,sequence_number,status_token,reason_token,event_timestamp,canonical_event_hash) VALUES (?,?,?,?,?,?,?)",
        (f"event-{digest[:32]}", trial_id, sequence, "COMPLETED", COMPLETION_REASON, timestamp, digest),
    )


def finalize_verified_result(
    ledger_path: str | Path, *, verified: Mapping[str, Any], result_relative_path: str,
    linked_at: str,
) -> dict[str, Any]:
    linked_time = parse_utc(linked_at, "linked_at")
    if (
        verified.get("verdict") != "VERIFIED"
        or verified.get("verifier") != VERIFIER_ID
        or verified.get("verification_mode") != "FULL_REPLAY_PREFINALIZATION"
    ):
        raise DevelopmentRuntimeError("VERIFIED_RESULT_REQUIRED")
    trial_id = verified.get("trial_id")
    result_id = verified.get("result_bundle_id")
    result_hash = verified.get("canonical_result_hash")
    if result_relative_path != f"{trial_id}/result.json":
        raise DevelopmentRuntimeError("RESULT_ARTIFACT_MISMATCH")
    link_core = {
        "trial_id": trial_id, "result_bundle_id": result_id,
        "result_bundle_hash": result_hash, "result_bundle_path": result_relative_path,
        "linked_at": linked_at,
    }
    link = TrialResultLink.from_mapping({**link_core, "canonical_result_link_hash": canonical_hash(link_core)})
    try:
        path = _trial_ledger_path(ledger_path, must_exist=True)
        _verify_trial_ledger_file(path)
    except Exception as error:
        raise DevelopmentRuntimeError(getattr(error, "reason", "TRIAL_LEDGER_INVALID")) from error
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing_row = conn.execute("SELECT * FROM trial_result_links WHERE trial_id=?", (trial_id,)).fetchone()
        latest = conn.execute("SELECT * FROM trial_events WHERE trial_id=? ORDER BY sequence_number DESC LIMIT 1", (trial_id,)).fetchone()
        if latest is not None:
            latest_core = {key: latest[key] for key in ("trial_id", "sequence_number", "status_token", "reason_token", "event_timestamp")}
            latest_hash = canonical_hash(latest_core)
            if latest["canonical_event_hash"] != latest_hash or latest["event_id"] != f"event-{latest_hash[:32]}":
                raise DevelopmentRuntimeError("TRIAL_EVENT_INTEGRITY_INVALID")
            if linked_time < parse_utc(latest["event_timestamp"], "latest_event_timestamp"):
                raise DevelopmentRuntimeError("TRIAL_EVENT_TIME_REGRESSION")
        if existing_row is not None:
            existing = TrialResultLink.from_mapping(dict(existing_row))
            if existing != link or latest is None or latest["status_token"] != "COMPLETED" or latest["reason_token"] != COMPLETION_REASON:
                raise DevelopmentRuntimeError("RESULT_FINALIZATION_CONFLICT")
            conn.commit()
            return {"finalizer": FINALIZER_ID, "trial_id": trial_id, "status": "COMPLETED", "replayed": True}
        if latest is None or latest["status_token"] != "ADMITTED" or latest["reason_token"] != ADMISSION_REASON:
            raise DevelopmentRuntimeError("TRIAL_STATE_NOT_ADMITTED")
        conn.execute(
            "INSERT INTO trial_result_links(trial_id,result_bundle_id,result_bundle_hash,result_bundle_path,linked_at,canonical_result_link_hash) VALUES (?,?,?,?,?,?)",
            (link.trial_id, link.result_bundle_id, link.result_bundle_hash, link.result_bundle_path, link.linked_at, link.canonical_result_link_hash),
        )
        _event(conn, trial_id=trial_id, sequence=int(latest["sequence_number"]) + 1, timestamp=linked_at)
        conn.commit()
        return {"finalizer": FINALIZER_ID, "trial_id": trial_id, "status": "COMPLETED", "replayed": False}
    except DevelopmentRuntimeError:
        conn.rollback()
        raise
    except sqlite3.DatabaseError as error:
        conn.rollback()
        raise DevelopmentRuntimeError("RESULT_FINALIZATION_FAILED") from error
    finally:
        conn.close()


def terminalize_failed_claim(ledger_path: str | Path, *, trial_id: str, reason: str, event_at: str) -> None:
    """Append one stable FAILED event only after an execution spec was claimed."""

    token = "M102_EXECUTION_OR_INTEGRITY_FAILURE"
    try:
        failure_time = parse_utc(event_at, "event_at")
        path = _trial_ledger_path(ledger_path, must_exist=True)
        _verify_trial_ledger_file(path)
        conn = sqlite3.connect(path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            conn.execute("BEGIN IMMEDIATE")
            latest = conn.execute(
                "SELECT * FROM trial_events WHERE trial_id=? ORDER BY sequence_number DESC LIMIT 1",
                (trial_id,),
            ).fetchone()
            if latest is None:
                raise DevelopmentRuntimeError("TRIAL_STATE_NOT_ADMITTED")
            latest_core = {
                key: latest[key] for key in
                ("trial_id", "sequence_number", "status_token", "reason_token", "event_timestamp")
            }
            latest_hash = canonical_hash(latest_core)
            if latest["canonical_event_hash"] != latest_hash or latest["event_id"] != f"event-{latest_hash[:32]}":
                raise DevelopmentRuntimeError("TRIAL_EVENT_INTEGRITY_INVALID")
            if latest["status_token"] == "FAILED" and latest["reason_token"] == token:
                conn.commit()
                return
            if latest["status_token"] != "ADMITTED" or latest["reason_token"] != ADMISSION_REASON:
                raise DevelopmentRuntimeError("TRIAL_STATE_NOT_ADMITTED")
            if failure_time < parse_utc(latest["event_timestamp"], "latest_event_timestamp"):
                raise DevelopmentRuntimeError("TRIAL_EVENT_TIME_REGRESSION")
            sequence = int(latest["sequence_number"]) + 1
            core = {
                "trial_id": trial_id, "sequence_number": sequence,
                "status_token": "FAILED", "reason_token": token,
                "event_timestamp": event_at,
            }
            digest = canonical_hash(core)
            conn.execute(
                "INSERT INTO trial_events(event_id,trial_id,sequence_number,status_token,reason_token,event_timestamp,canonical_event_hash) VALUES (?,?,?,?,?,?,?)",
                (f"event-{digest[:32]}", trial_id, sequence, "FAILED", token, event_at, digest),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except DevelopmentRuntimeError:
        raise
    except Exception as error:
        raise DevelopmentRuntimeError("TRIAL_FAILURE_TERMINALIZATION_FAILED", reason) from error
