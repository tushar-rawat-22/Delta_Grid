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
FUNDING_BOUNDARY_TOLERANCE_MS = 10_000


def _iso_hour(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, timezone.utc).strftime("%Y-%m-%dT%H:00:00.000Z")


def _timestamp_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def _ceiling_hour(value: int) -> int:
    return ((value + HOUR_MS - 1) // HOUR_MS) * HOUR_MS


def _funding_hour(value: int) -> int | None:
    nearest = ((value + HOUR_MS // 2) // HOUR_MS) * HOUR_MS
    if abs(value - nearest) > FUNDING_BOUNDARY_TOLERANCE_MS:
        return None
    return nearest


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
            """SELECT o.event_time_ms, o.symbol, o.available_at
               FROM observations o
               JOIN capture_batches b ON b.batch_id=o.batch_id
               JOIN receipts r ON r.receipt_hash=o.receipt_hash
               WHERE o.stream='perpetual_ohlcv' AND b.status='COMPLETE'
                 AND r.clock_status='HEALTHY'
               ORDER BY o.event_time_ms,o.symbol,o.available_at""",
        ).fetchall()
        bar_hours: dict[int, dict[str, int]] = {}
        for event_time, symbol, available_at in rows:
            close_time = int(event_time)
            coverage_hour = close_time + 1
            if symbol in SYMBOLS and coverage_hour % HOUR_MS == 0 and coverage_hour >= activation_ms:
                observed = _timestamp_ms(str(available_at))
                prior = bar_hours.setdefault(coverage_hour, {}).get(str(symbol))
                bar_hours[coverage_hour][str(symbol)] = observed if prior is None else max(prior, observed)

        funding_rows = connection.execute(
            """SELECT o.event_time_ms, o.symbol, o.available_at
               FROM observations o
               JOIN capture_batches b ON b.batch_id=o.batch_id
               JOIN receipts r ON r.receipt_hash=o.receipt_hash
               WHERE o.stream='funding_rates' AND b.status='COMPLETE'
                 AND r.clock_status='HEALTHY'
               ORDER BY o.event_time_ms,o.symbol,o.available_at""",
        ).fetchall()
        funding_hours: dict[int, dict[str, int]] = {}
        for event_time, symbol, available_at in funding_rows:
            normalized = _funding_hour(int(event_time))
            if symbol not in SYMBOLS or normalized is None:
                continue
            observed = _timestamp_ms(str(available_at))
            prior = funding_hours.setdefault(normalized, {}).get(str(symbol))
            funding_hours[normalized][str(symbol)] = observed if prior is None else max(prior, observed)

        complete_funding = {
            hour: availability for hour, availability in funding_hours.items()
            if set(availability) == set(SYMBOLS)
        }
        candidates: list[int] = []
        for coverage_hour in sorted(bar_hours):
            bar_availability = bar_hours[coverage_hour]
            if set(bar_availability) != set(SYMBOLS):
                continue
            eligible_funding = [
                hour for hour in complete_funding
                if hour <= coverage_hour and coverage_hour - hour <= MAX_SETTLED_FUNDING_AGE_MS
            ]
            if not eligible_funding:
                continue
            funding_hour = max(eligible_funding)
            complete_at = max(
                activation_ms,
                *bar_availability.values(),
                *complete_funding[funding_hour].values(),
            )
            candidate = _ceiling_hour(complete_at)
            if candidate <= activation_ms:
                candidate += HOUR_MS
            candidates.append(candidate)
        if candidates:
            return _iso_hour(min(candidates))
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
