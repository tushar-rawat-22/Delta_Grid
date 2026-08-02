"""Append-only SQLite trial budget, reservation, and event ledger."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator

from .models import (
    AdmissionError,
    BudgetDefinition,
    TrialReservation,
    canonical_hash,
)


STATUSES = frozenset(
    {
        "RESERVED",
        "ADMITTED",
        "STOPPED",
        "FAILED",
        "REJECTED",
        "COMPLETED",
        "SUPERSEDED",
    }
)
TERMINAL_STATUSES = frozenset(
    {"STOPPED", "FAILED", "REJECTED", "COMPLETED", "SUPERSEDED"}
)
ORIGINS = frozenset({"OPERATOR", "MANUAL_RECONSTRUCTION", "FUTURE_AUTOMATION"})
TRANSITIONS = {
    "RESERVED": frozenset(
        {"ADMITTED", "STOPPED", "FAILED", "REJECTED", "SUPERSEDED"}
    ),
    "ADMITTED": frozenset({"FAILED", "COMPLETED", "SUPERSEDED"}),
    "STOPPED": frozenset(),
    "FAILED": frozenset(),
    "REJECTED": frozenset(),
    "COMPLETED": frozenset(),
    "SUPERSEDED": frozenset(),
}


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS trial_budgets (
    budget_id TEXT PRIMARY KEY,
    controlling_contract_id TEXT NOT NULL,
    controlling_contract_hash TEXT NOT NULL,
    experiment_family TEXT NOT NULL,
    total_trial_budget INTEGER NOT NULL CHECK (
        total_trial_budget > 0 AND typeof(total_trial_budget) = 'integer'
    ),
    created_at TEXT NOT NULL,
    canonical_budget_hash TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS trial_reservations (
    trial_id TEXT PRIMARY KEY,
    budget_id TEXT NOT NULL REFERENCES trial_budgets(budget_id),
    declared_trial_number INTEGER NOT NULL CHECK (
        declared_trial_number > 0 AND typeof(declared_trial_number) = 'integer'
    ),
    request_hash TEXT NOT NULL UNIQUE,
    initiated_by TEXT NOT NULL CHECK (
        initiated_by IN ('OPERATOR', 'MANUAL_RECONSTRUCTION', 'FUTURE_AUTOMATION')
    ),
    reserved_at TEXT NOT NULL,
    UNIQUE (budget_id, declared_trial_number)
);
CREATE TABLE IF NOT EXISTS trial_events (
    event_id TEXT PRIMARY KEY,
    trial_id TEXT NOT NULL REFERENCES trial_reservations(trial_id),
    sequence_number INTEGER NOT NULL CHECK (
        sequence_number > 0 AND typeof(sequence_number) = 'integer'
    ),
    status_token TEXT NOT NULL CHECK (
        status_token IN (
            'RESERVED', 'ADMITTED', 'STOPPED', 'FAILED', 'REJECTED',
            'COMPLETED', 'SUPERSEDED'
        )
    ),
    reason_token TEXT NOT NULL,
    event_timestamp TEXT NOT NULL,
    canonical_event_hash TEXT NOT NULL UNIQUE,
    UNIQUE (trial_id, sequence_number)
);
CREATE TRIGGER IF NOT EXISTS trial_budgets_no_update
BEFORE UPDATE ON trial_budgets BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_TRIAL_BUDGET');
END;
CREATE TRIGGER IF NOT EXISTS trial_budgets_no_delete
BEFORE DELETE ON trial_budgets BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_TRIAL_BUDGET');
END;
CREATE TRIGGER IF NOT EXISTS trial_reservations_no_update
BEFORE UPDATE ON trial_reservations BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_TRIAL_RESERVATION');
END;
CREATE TRIGGER IF NOT EXISTS trial_reservations_no_delete
BEFORE DELETE ON trial_reservations BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_TRIAL_RESERVATION');
END;
CREATE TRIGGER IF NOT EXISTS trial_reservations_budget_guard
BEFORE INSERT ON trial_reservations BEGIN
    SELECT CASE WHEN NEW.declared_trial_number > (
        SELECT total_trial_budget FROM trial_budgets
        WHERE budget_id = NEW.budget_id
    ) THEN RAISE(ABORT, 'TRIAL_BUDGET_EXHAUSTED') END;
    SELECT CASE WHEN (
        SELECT COUNT(*) FROM trial_reservations
        WHERE budget_id = NEW.budget_id
    ) >= (
        SELECT total_trial_budget FROM trial_budgets
        WHERE budget_id = NEW.budget_id
    ) THEN RAISE(ABORT, 'TRIAL_BUDGET_EXHAUSTED') END;
END;
CREATE TRIGGER IF NOT EXISTS trial_events_no_update
BEFORE UPDATE ON trial_events BEGIN
    SELECT RAISE(ABORT, 'APPEND_ONLY_TRIAL_EVENT');
END;
CREATE TRIGGER IF NOT EXISTS trial_events_no_delete
BEFORE DELETE ON trial_events BEGIN
    SELECT RAISE(ABORT, 'APPEND_ONLY_TRIAL_EVENT');
END;
"""


class TrialLedger:
    """Caller-local SQLite ledger with atomic reservation semantics."""

    def __init__(self, database_path: Path | str, timeout: float = 10.0) -> None:
        self.database_path = Path(database_path)
        self.timeout = timeout
        with self._connection() as connection:
            connection.executescript(SCHEMA_SQL)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self.database_path,
            timeout=self.timeout,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def register_budget(
        self,
        *,
        budget_id: str,
        controlling_contract_id: str,
        controlling_contract_hash: str,
        experiment_family: str,
        total_trial_budget: int,
        created_at: str,
    ) -> BudgetDefinition:
        """Create an immutable budget, or return its identical existing record."""

        values = {
            "budget_id": budget_id,
            "controlling_contract_id": controlling_contract_id,
            "controlling_contract_hash": controlling_contract_hash,
            "experiment_family": experiment_family,
            "total_trial_budget": total_trial_budget,
            "created_at": created_at,
        }
        if (
            any(not isinstance(values[key], str) or not values[key] for key in values if key != "total_trial_budget")
            or type(total_trial_budget) is not int
            or total_trial_budget < 1
        ):
            raise AdmissionError("BUDGET_DEFINITION_MISMATCH")
        budget_hash = canonical_hash(values)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM trial_budgets WHERE budget_id = ?", (budget_id,)
            ).fetchone()
            if row is not None:
                connection.commit()
                existing = self._budget_from_row(row)
                if existing.canonical_budget_hash != budget_hash:
                    raise AdmissionError("BUDGET_DEFINITION_MISMATCH")
                return existing
            try:
                connection.execute(
                    """
                    INSERT INTO trial_budgets (
                        budget_id, controlling_contract_id,
                        controlling_contract_hash, experiment_family,
                        total_trial_budget, created_at, canonical_budget_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        budget_id,
                        controlling_contract_id,
                        controlling_contract_hash,
                        experiment_family,
                        total_trial_budget,
                        created_at,
                        budget_hash,
                    ),
                )
                connection.commit()
            except sqlite3.DatabaseError as error:
                connection.rollback()
                raise AdmissionError("BUDGET_DEFINITION_MISMATCH") from error
        return BudgetDefinition(**values, canonical_budget_hash=budget_hash)

    @staticmethod
    def _budget_from_row(row: sqlite3.Row) -> BudgetDefinition:
        return BudgetDefinition(**dict(row))

    def get_budget(self, budget_id: str) -> BudgetDefinition:
        """Return an immutable budget definition."""

        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM trial_budgets WHERE budget_id = ?", (budget_id,)
            ).fetchone()
        if row is None:
            raise AdmissionError("BUDGET_UNKNOWN")
        budget = self._budget_from_row(row)
        core = budget.as_dict()
        supplied_hash = core.pop("canonical_budget_hash")
        if canonical_hash(core) != supplied_hash:
            raise AdmissionError("INTERNAL_INTEGRITY_FAILURE")
        return budget

    def check_reservable(
        self,
        *,
        budget_id: str,
        declared_trial_number: int,
        request_hash: str,
        controlling_contract_id: str,
        controlling_contract_hash: str,
    ) -> None:
        """Perform a read-only advisory reservation check for preflight."""

        budget = self.get_budget(budget_id)
        self._verify_budget_identity(
            budget, controlling_contract_id, controlling_contract_hash
        )
        with self._connection() as connection:
            if connection.execute(
                "SELECT 1 FROM trial_reservations WHERE request_hash = ?",
                (request_hash,),
            ).fetchone():
                raise AdmissionError("REQUEST_ALREADY_RESERVED")
            if connection.execute(
                """
                SELECT 1 FROM trial_reservations
                WHERE budget_id = ? AND declared_trial_number = ?
                """,
                (budget_id, declared_trial_number),
            ).fetchone():
                raise AdmissionError("DECLARED_TRIAL_ALREADY_USED")
            used = connection.execute(
                "SELECT COUNT(*) FROM trial_reservations WHERE budget_id = ?",
                (budget_id,),
            ).fetchone()[0]
        if declared_trial_number > budget.total_trial_budget or used >= budget.total_trial_budget:
            raise AdmissionError("TRIAL_BUDGET_EXHAUSTED")

    @staticmethod
    def _verify_budget_identity(
        budget: BudgetDefinition,
        controlling_contract_id: str,
        controlling_contract_hash: str,
    ) -> None:
        if (
            budget.controlling_contract_id != controlling_contract_id
            or budget.controlling_contract_hash != controlling_contract_hash
        ):
            raise AdmissionError("BUDGET_DEFINITION_MISMATCH")

    def reserve(
        self,
        *,
        budget_id: str,
        declared_trial_number: int,
        request_hash: str,
        initiated_by: str,
        reserved_at: str,
        controlling_contract_id: str,
        controlling_contract_hash: str,
    ) -> TrialReservation:
        """Atomically reserve one immutable trial using ``BEGIN IMMEDIATE``."""

        if initiated_by not in ORIGINS:
            raise AdmissionError("INITIATED_BY_INVALID")
        if type(declared_trial_number) is not int or declared_trial_number < 1:
            raise AdmissionError("DECLARED_TRIAL_NUMBER_INVALID")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT * FROM trial_budgets WHERE budget_id = ?", (budget_id,)
                ).fetchone()
                if row is None:
                    raise AdmissionError("BUDGET_UNKNOWN")
                budget = self._budget_from_row(row)
                self._verify_budget_identity(
                    budget, controlling_contract_id, controlling_contract_hash
                )
                if connection.execute(
                    "SELECT 1 FROM trial_reservations WHERE request_hash = ?",
                    (request_hash,),
                ).fetchone():
                    raise AdmissionError("REQUEST_ALREADY_RESERVED")
                if connection.execute(
                    """
                    SELECT 1 FROM trial_reservations
                    WHERE budget_id = ? AND declared_trial_number = ?
                    """,
                    (budget_id, declared_trial_number),
                ).fetchone():
                    raise AdmissionError("DECLARED_TRIAL_ALREADY_USED")
                used = connection.execute(
                    "SELECT COUNT(*) FROM trial_reservations WHERE budget_id = ?",
                    (budget_id,),
                ).fetchone()[0]
                if (
                    declared_trial_number > budget.total_trial_budget
                    or used >= budget.total_trial_budget
                ):
                    raise AdmissionError("TRIAL_BUDGET_EXHAUSTED")
                trial_core = {
                    "budget_id": budget_id,
                    "declared_trial_number": declared_trial_number,
                    "request_hash": request_hash,
                    "initiated_by": initiated_by,
                    "reserved_at": reserved_at,
                }
                trial_id = f"trial-{canonical_hash(trial_core)[:32]}"
                reservation = TrialReservation(trial_id=trial_id, **trial_core)
                connection.execute(
                    """
                    INSERT INTO trial_reservations (
                        trial_id, budget_id, declared_trial_number, request_hash,
                        initiated_by, reserved_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trial_id,
                        budget_id,
                        declared_trial_number,
                        request_hash,
                        initiated_by,
                        reserved_at,
                    ),
                )
                self._insert_event(
                    connection,
                    trial_id=trial_id,
                    sequence_number=1,
                    status_token="RESERVED",
                    reason_token="TRIAL_RESERVED",
                    event_timestamp=reserved_at,
                )
                connection.commit()
                return reservation
            except AdmissionError:
                connection.rollback()
                raise
            except sqlite3.IntegrityError as error:
                connection.rollback()
                message = str(error)
                reason = (
                    "TRIAL_BUDGET_EXHAUSTED"
                    if "TRIAL_BUDGET_EXHAUSTED" in message
                    else "INTERNAL_INTEGRITY_FAILURE"
                )
                raise AdmissionError(reason) from error
            except sqlite3.DatabaseError as error:
                connection.rollback()
                raise AdmissionError("INTERNAL_INTEGRITY_FAILURE") from error

    @staticmethod
    def _insert_event(
        connection: sqlite3.Connection,
        *,
        trial_id: str,
        sequence_number: int,
        status_token: str,
        reason_token: str,
        event_timestamp: str,
    ) -> None:
        core = {
            "trial_id": trial_id,
            "sequence_number": sequence_number,
            "status_token": status_token,
            "reason_token": reason_token,
            "event_timestamp": event_timestamp,
        }
        event_hash = canonical_hash(core)
        event_id = f"event-{event_hash[:32]}"
        connection.execute(
            """
            INSERT INTO trial_events (
                event_id, trial_id, sequence_number, status_token,
                reason_token, event_timestamp, canonical_event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                trial_id,
                sequence_number,
                status_token,
                reason_token,
                event_timestamp,
                event_hash,
            ),
        )

    def append_event(
        self,
        *,
        trial_id: str,
        status_token: str,
        reason_token: str,
        event_timestamp: str,
    ) -> None:
        """Append one explicit allowed transition to a trial."""

        if status_token not in STATUSES or status_token == "RESERVED":
            raise AdmissionError("INTERNAL_INTEGRITY_FAILURE")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                latest = connection.execute(
                    """
                    SELECT sequence_number, status_token FROM trial_events
                    WHERE trial_id = ? ORDER BY sequence_number DESC LIMIT 1
                    """,
                    (trial_id,),
                ).fetchone()
                if latest is None:
                    raise AdmissionError("INTERNAL_INTEGRITY_FAILURE")
                if status_token not in TRANSITIONS[latest["status_token"]]:
                    raise AdmissionError("INTERNAL_INTEGRITY_FAILURE")
                self._insert_event(
                    connection,
                    trial_id=trial_id,
                    sequence_number=latest["sequence_number"] + 1,
                    status_token=status_token,
                    reason_token=reason_token,
                    event_timestamp=event_timestamp,
                )
                connection.commit()
            except AdmissionError:
                connection.rollback()
                raise
            except sqlite3.DatabaseError as error:
                connection.rollback()
                raise AdmissionError("INTERNAL_INTEGRITY_FAILURE") from error

    def reservation_count(self, budget_id: str | None = None) -> int:
        """Return a read-only reservation count for verification and reporting."""

        with self._connection() as connection:
            if budget_id is None:
                row = connection.execute(
                    "SELECT COUNT(*) FROM trial_reservations"
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT COUNT(*) FROM trial_reservations WHERE budget_id = ?",
                    (budget_id,),
                ).fetchone()
        return int(row[0])

    def event_statuses(self, trial_id: str) -> tuple[str, ...]:
        """Return the append-order status tokens for one trial."""

        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT status_token FROM trial_events
                WHERE trial_id = ? ORDER BY sequence_number
                """,
                (trial_id,),
            ).fetchall()
        return tuple(row[0] for row in rows)
