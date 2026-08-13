"""Metadata-only T0 selection and immutable RAB-1 readiness initialization."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from urllib.parse import quote

from offchain.market_data_acquisition.schema import APPLICATION_ID
from offchain.research.statistical_governance.core import GovernanceError, canonical_hash

from .protocol import CONTRACT_HASH, evidence_calendar, load_contract


SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
HOUR_MS = 3_600_000
MAX_SETTLED_FUNDING_AGE_MS = 8 * HOUR_MS


def _iso_hour(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, timezone.utc).strftime("%Y-%m-%dT%H:00:00.000Z")


def select_t0_metadata(database_path: str | Path) -> str:
    """Select T0 without opening any observation payload JSON."""

    path = Path(database_path).resolve(strict=True)
    connection = sqlite3.connect(f"file:{quote(str(path), safe='/')}?mode=ro", uri=True)
    try:
        application_id = connection.execute("PRAGMA application_id").fetchone()[0]
        if application_id != APPLICATION_ID:
            raise GovernanceError("RAB1_T0_JOURNAL_IDENTITY_INVALID")
        created = connection.execute("SELECT value FROM metadata WHERE key='created_at'").fetchone()
        if created is None:
            raise GovernanceError("RAB1_T0_ACTIVATION_MISSING")
        activation_ms = int(datetime.fromisoformat(created[0].replace("Z", "+00:00")).timestamp() * 1000)
        rows = connection.execute(
            """SELECT o.event_time_ms, o.symbol
               FROM observations o
               JOIN capture_batches b ON b.batch_id=o.batch_id
               JOIN receipts r ON r.receipt_hash=o.receipt_hash
               WHERE o.stream='perpetual_ohlcv' AND b.status='COMPLETE'
                 AND r.clock_status='HEALTHY' AND o.event_time_ms>=?
               GROUP BY o.event_time_ms,o.symbol
               ORDER BY o.event_time_ms,o.symbol""",
            (activation_ms,),
        ).fetchall()
        by_hour: dict[int, set[str]] = {}
        for event_time, symbol in rows:
            if symbol in SYMBOLS and event_time % HOUR_MS == 0:
                by_hour.setdefault(int(event_time), set()).add(str(symbol))
        for hour in sorted(by_hour):
            if by_hour[hour] != set(SYMBOLS):
                continue
            complete = True
            for symbol in SYMBOLS:
                latest = connection.execute(
                    """SELECT MAX(o.event_time_ms)
                       FROM observations o
                       JOIN capture_batches b ON b.batch_id=o.batch_id
                       JOIN receipts r ON r.receipt_hash=o.receipt_hash
                       WHERE o.stream='funding_rates' AND o.symbol=?
                         AND o.event_time_ms<=? AND b.status='COMPLETE' AND r.clock_status='HEALTHY'""",
                    (symbol, hour),
                ).fetchone()[0]
                if latest is None or hour - int(latest) > MAX_SETTLED_FUNDING_AGE_MS:
                    complete = False
                    break
            if complete:
                return _iso_hour(hour)
    finally:
        connection.close()
    raise GovernanceError("RAB1_T0_HEALTHY_COMPLETE_COVERAGE_NOT_FOUND")


def initialize_state(destination: str | Path, *, journal_path: str | Path) -> dict[str, object]:
    load_contract()
    t0 = select_t0_metadata(journal_path)
    calendar = evidence_calendar(t0)
    core: dict[str, object] = {
        "state_schema": "DELTAGRID_RAB1_READINESS_STATE_V1",
        "contract_hash": CONTRACT_HASH,
        "t0": t0,
        "calendar": calendar,
        "current_state": "WARMUP",
        "required_founder_approval": None,
        "terminal_verdict": "MISSION_104_NOT_AUTHORIZED",
        "authority_effect": "NONE",
        "mission104_started": False,
        "mission104_authorized": False,
    }
    state = {**core, "state_hash": canonical_hash(core)}
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != state:
            raise GovernanceError("RAB1_STATE_ALREADY_INITIALIZED_DIFFERENTLY")
        return state
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(state, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return state
