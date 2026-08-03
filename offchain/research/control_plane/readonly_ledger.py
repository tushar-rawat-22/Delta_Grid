"""Independent, fail-closed, read-only access to the Mission 94/95 ledger."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
from typing import Any, Iterator
from urllib.parse import quote

from offchain.research.admission import (
    AdmissionError,
    BudgetDefinition,
    TrialEvent,
    TrialReservation,
    TrialResultLink,
    canonical_hash,
)
from offchain.research.admission.trial_ledger import ORIGINS, STATUSES, TRANSITIONS

from .models import ControlPlaneError


_REQUIRED_SCHEMA = {
    "trial_budgets": {
        "budget_id": "TEXT",
        "controlling_contract_id": "TEXT",
        "controlling_contract_hash": "TEXT",
        "experiment_family": "TEXT",
        "total_trial_budget": "INTEGER",
        "created_at": "TEXT",
        "canonical_budget_hash": "TEXT",
    },
    "trial_reservations": {
        "trial_id": "TEXT",
        "budget_id": "TEXT",
        "declared_trial_number": "INTEGER",
        "request_hash": "TEXT",
        "initiated_by": "TEXT",
        "reserved_at": "TEXT",
    },
    "trial_events": {
        "event_id": "TEXT",
        "trial_id": "TEXT",
        "sequence_number": "INTEGER",
        "status_token": "TEXT",
        "reason_token": "TEXT",
        "event_timestamp": "TEXT",
        "canonical_event_hash": "TEXT",
    },
    "trial_result_links": {
        "trial_id": "TEXT",
        "result_bundle_id": "TEXT",
        "result_bundle_hash": "TEXT",
        "result_bundle_path": "TEXT",
        "linked_at": "TEXT",
        "canonical_result_link_hash": "TEXT",
    },
}
_REQUIRED_PRIMARY_KEYS = {
    "trial_budgets": ("budget_id",),
    "trial_reservations": ("trial_id",),
    "trial_events": ("event_id",),
    "trial_result_links": ("trial_id",),
}
_REQUIRED_NOT_NULL = {
    table: frozenset(columns) - frozenset(_REQUIRED_PRIMARY_KEYS[table])
    for table, columns in _REQUIRED_SCHEMA.items()
}
_REQUIRED_UNIQUES = {
    "trial_budgets": frozenset({("canonical_budget_hash",)}),
    "trial_reservations": frozenset(
        {("request_hash",), ("budget_id", "declared_trial_number")}
    ),
    "trial_events": frozenset(
        {("canonical_event_hash",), ("trial_id", "sequence_number")}
    ),
    "trial_result_links": frozenset(
        {
            ("result_bundle_id",),
            ("result_bundle_hash",),
            ("result_bundle_path",),
            ("canonical_result_link_hash",),
        }
    ),
}
_REQUIRED_FOREIGN_KEYS = {
    "trial_reservations": frozenset(
        {("budget_id", "trial_budgets", "budget_id")}
    ),
    "trial_events": frozenset(
        {("trial_id", "trial_reservations", "trial_id")}
    ),
    "trial_result_links": frozenset(
        {("trial_id", "trial_reservations", "trial_id")}
    ),
}
_REQUIRED_TRIGGERS = {
    "trial_budgets_no_update": "trial_budgets",
    "trial_budgets_no_delete": "trial_budgets",
    "trial_reservations_no_update": "trial_reservations",
    "trial_reservations_no_delete": "trial_reservations",
    "trial_reservations_budget_guard": "trial_reservations",
    "trial_events_no_update": "trial_events",
    "trial_events_no_delete": "trial_events",
    "trial_result_links_no_update": "trial_result_links",
    "trial_result_links_no_delete": "trial_result_links",
}
_UTC_TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z"
)


@dataclass(frozen=True)
class _RowFailure:
    table: str
    reason_token: str
    trial_id: str | None
    identity: str


@dataclass(frozen=True)
class _LedgerSnapshot:
    budgets: tuple[BudgetDefinition, ...]
    reservations: tuple[TrialReservation, ...]
    events: tuple[TrialEvent, ...]
    result_links: tuple[TrialResultLink, ...]
    failures: tuple[_RowFailure, ...]
    raw_counts: tuple[int, int, int, int]


def _is_nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _is_hash(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _row_identity(value: dict[str, Any]) -> str:
    safe = {
        key: (
            item
            if item is None or type(item) in (str, int, float, bool)
            else {"python_type": type(item).__name__, "representation": repr(item)}
        )
        for key, item in value.items()
    }
    return canonical_hash(safe)


def _parse_normalized_utc(value: Any) -> datetime:
    """Parse exact UTC text without consulting a clock or local timezone."""

    if not isinstance(value, str) or _UTC_TIMESTAMP_RE.fullmatch(value) is None:
        raise AdmissionError("TIMESTAMP_INVALID")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise AdmissionError("TIMESTAMP_INVALID") from error
    if parsed.tzinfo != timezone.utc:
        raise AdmissionError("TIMESTAMP_INVALID")
    return parsed


def _resolve_existing_no_symlink(
    value: Path | str,
    *,
    require_directory: bool,
    unavailable_reason: str,
    unsafe_reason: str,
) -> Path:
    supplied = Path(value)
    candidate = supplied if supplied.is_absolute() else Path.cwd() / supplied
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current = current / part
        try:
            metadata = os.lstat(current)
        except OSError as error:
            raise ControlPlaneError(
                unavailable_reason, "path does not exist"
            ) from error
        if stat.S_ISLNK(metadata.st_mode):
            raise ControlPlaneError(
                unsafe_reason, "path contains a symbolic link"
            )
    try:
        resolved = candidate.resolve(strict=True)
        metadata = resolved.stat()
    except OSError as error:
        raise ControlPlaneError(unavailable_reason, "path does not exist") from error
    expected = (
        stat.S_ISDIR(metadata.st_mode)
        if require_directory
        else stat.S_ISREG(metadata.st_mode)
    )
    if not expected:
        kind = "directory" if require_directory else "regular file"
        raise ControlPlaneError(unavailable_reason, f"path must be a {kind}")
    return resolved


class ReadOnlyTrialLedger:
    """True SQLite read-only adapter with no write-capable ledger construction."""

    _IDENTITY_FIELDS = frozenset(
        {"_database_path", "_timeout", "_sqlite_uri"}
    )

    def __setattr__(self, name: str, value: Any) -> None:
        if name in self._IDENTITY_FIELDS and hasattr(self, name):
            raise AttributeError(f"{name} is read-only")
        object.__setattr__(self, name, value)

    def __init__(self, database_path: Path | str, timeout: float = 5.0) -> None:
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(float(timeout))
            or not 0.0 < float(timeout) <= 60.0
        ):
            raise ControlPlaneError(
                "LEDGER_TIMEOUT_INVALID", "timeout must be in (0, 60] seconds"
            )
        resolved = _resolve_existing_no_symlink(
            database_path,
            require_directory=False,
            unavailable_reason="LEDGER_UNAVAILABLE",
            unsafe_reason="LEDGER_PATH_UNSAFE",
        )
        self._database_path = resolved
        self._timeout = float(timeout)
        encoded_path = quote(str(resolved), safe="/")
        self._sqlite_uri = f"file:{encoded_path}?mode=ro"
        try:
            with self._connection() as connection:
                self._verify_schema(connection)
        except ControlPlaneError:
            raise
        except sqlite3.DatabaseError as error:
            raise ControlPlaneError("LEDGER_UNAVAILABLE", str(error)) from error

    @property
    def database_path(self) -> Path:
        return self._database_path

    @property
    def timeout(self) -> float:
        return self._timeout

    @property
    def sqlite_uri(self) -> str:
        return self._sqlite_uri

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        try:
            connection = sqlite3.connect(
                self.sqlite_uri,
                timeout=self.timeout,
                isolation_level=None,
                uri=True,
            )
        except sqlite3.DatabaseError as error:
            raise ControlPlaneError("LEDGER_UNAVAILABLE", str(error)) from error
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA query_only = ON")
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _verify_schema(connection: sqlite3.Connection) -> None:
        try:
            available = {
                str(row["name"])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            for table, required in _REQUIRED_SCHEMA.items():
                if table not in available:
                    raise ControlPlaneError(
                        "LEDGER_SCHEMA_INCOMPATIBLE", f"missing table: {table}"
                    )
                escaped_table = table.replace('"', '""')
                rows = connection.execute(
                    f'PRAGMA table_info("{escaped_table}")'
                ).fetchall()
                by_column = {str(row["name"]): row for row in rows}
                for column, expected_type in required.items():
                    if column not in by_column:
                        raise ControlPlaneError(
                            "LEDGER_SCHEMA_INCOMPATIBLE",
                            f"missing column: {table}.{column}",
                        )
                    declared_type = str(by_column[column]["type"]).upper().strip()
                    if declared_type != expected_type:
                        raise ControlPlaneError(
                            "LEDGER_SCHEMA_INCOMPATIBLE",
                            f"incompatible declaration: {table}.{column}",
                        )
                primary_key = tuple(
                    str(row["name"])
                    for row in sorted(rows, key=lambda item: int(item["pk"]))
                    if int(row["pk"]) > 0
                )
                if primary_key != _REQUIRED_PRIMARY_KEYS[table]:
                    raise ControlPlaneError(
                        "LEDGER_SCHEMA_INCOMPATIBLE",
                        f"incompatible primary key: {table}",
                    )
                if any(
                    int(by_column[column]["notnull"]) != 1
                    for column in _REQUIRED_NOT_NULL[table]
                ):
                    raise ControlPlaneError(
                        "LEDGER_SCHEMA_INCOMPATIBLE",
                        f"missing not-null declaration: {table}",
                    )
                unique_identities: set[tuple[str, ...]] = set()
                for index_row in connection.execute(
                    f'PRAGMA index_list("{escaped_table}")'
                ).fetchall():
                    if (
                        int(index_row["unique"]) != 1
                        or int(index_row["partial"]) != 0
                    ):
                        continue
                    index_name = str(index_row["name"]).replace('"', '""')
                    index_columns = tuple(
                        str(item["name"])
                        for item in sorted(
                            connection.execute(
                                f'PRAGMA index_info("{index_name}")'
                            ).fetchall(),
                            key=lambda item: int(item["seqno"]),
                        )
                    )
                    unique_identities.add(index_columns)
                if not _REQUIRED_UNIQUES[table] <= unique_identities:
                    raise ControlPlaneError(
                        "LEDGER_SCHEMA_INCOMPATIBLE",
                        f"missing unique identity: {table}",
                    )
                foreign_keys = frozenset(
                    (
                        str(row["from"]),
                        str(row["table"]),
                        str(row["to"]),
                    )
                    for row in connection.execute(
                        f'PRAGMA foreign_key_list("{escaped_table}")'
                    ).fetchall()
                )
                if not _REQUIRED_FOREIGN_KEYS.get(table, frozenset()) <= foreign_keys:
                    raise ControlPlaneError(
                        "LEDGER_SCHEMA_INCOMPATIBLE",
                        f"missing foreign key: {table}",
                    )
            triggers = {
                str(row["name"]): str(row["tbl_name"])
                for row in connection.execute(
                    "SELECT name, tbl_name FROM sqlite_master WHERE type = 'trigger'"
                ).fetchall()
            }
            if any(
                triggers.get(name) != table
                for name, table in _REQUIRED_TRIGGERS.items()
            ):
                raise ControlPlaneError(
                    "LEDGER_SCHEMA_INCOMPATIBLE", "required trigger is missing"
                )
        except ControlPlaneError:
            raise
        except sqlite3.DatabaseError as error:
            raise ControlPlaneError("LEDGER_SCHEMA_INCOMPATIBLE", str(error)) from error

    @staticmethod
    def _budget(row: sqlite3.Row) -> BudgetDefinition:
        value = dict(row)
        text_fields = (
            "budget_id",
            "controlling_contract_id",
            "controlling_contract_hash",
            "experiment_family",
            "created_at",
            "canonical_budget_hash",
        )
        if (
            any(not _is_nonempty_text(value[field]) for field in text_fields)
            or type(value["total_trial_budget"]) is not int
            or value["total_trial_budget"] < 1
            or not _is_hash(value["controlling_contract_hash"])
            or not _is_hash(value["canonical_budget_hash"])
        ):
            raise AdmissionError("INTERNAL_INTEGRITY_FAILURE")
        _parse_normalized_utc(value["created_at"])
        supplied = value.pop("canonical_budget_hash")
        if canonical_hash(value) != supplied:
            raise AdmissionError("INTERNAL_INTEGRITY_FAILURE")
        return BudgetDefinition(**value, canonical_budget_hash=supplied)

    @staticmethod
    def _reservation(row: sqlite3.Row) -> TrialReservation:
        value = dict(row)
        if (
            any(
                not _is_nonempty_text(value[field])
                for field in (
                    "trial_id",
                    "budget_id",
                    "request_hash",
                    "initiated_by",
                    "reserved_at",
                )
            )
            or type(value["declared_trial_number"]) is not int
            or value["declared_trial_number"] < 1
            or not _is_hash(value["request_hash"])
            or value["initiated_by"] not in ORIGINS
        ):
            raise AdmissionError("TRIAL_RESERVATION_MISMATCH")
        _parse_normalized_utc(value["reserved_at"])
        core = {key: value[key] for key in value if key != "trial_id"}
        if value["trial_id"] != f"trial-{canonical_hash(core)[:32]}":
            raise AdmissionError("TRIAL_RESERVATION_MISMATCH")
        return TrialReservation(**value)

    @staticmethod
    def _event(row: sqlite3.Row) -> TrialEvent:
        value = dict(row)
        if (
            any(
                not _is_nonempty_text(value[field])
                for field in (
                    "event_id",
                    "trial_id",
                    "status_token",
                    "reason_token",
                    "event_timestamp",
                    "canonical_event_hash",
                )
            )
            or type(value["sequence_number"]) is not int
            or value["sequence_number"] < 1
            or value["status_token"] not in STATUSES
            or not _is_hash(value["canonical_event_hash"])
        ):
            raise AdmissionError("INTERNAL_INTEGRITY_FAILURE")
        _parse_normalized_utc(value["event_timestamp"])
        core = {
            key: value[key]
            for key in (
                "trial_id",
                "sequence_number",
                "status_token",
                "reason_token",
                "event_timestamp",
            )
        }
        expected = canonical_hash(core)
        if (
            value["canonical_event_hash"] != expected
            or value["event_id"] != f"event-{expected[:32]}"
        ):
            raise AdmissionError("INTERNAL_INTEGRITY_FAILURE")
        return TrialEvent(**value)

    @staticmethod
    def _result_link(row: sqlite3.Row) -> TrialResultLink:
        value = dict(row)
        try:
            link = TrialResultLink.from_mapping(value)
        except AdmissionError:
            raise
        if (
            not link.trial_id.startswith("trial-")
            or len(link.trial_id) != 38
            or any(
                character not in "0123456789abcdef"
                for character in link.trial_id[6:]
            )
            or not link.result_bundle_id.startswith("result-bundle-")
            or len(link.result_bundle_id) != 46
            or any(
                character not in "0123456789abcdef"
                for character in link.result_bundle_id[14:]
            )
            or not _is_hash(link.result_bundle_hash)
            or link.result_bundle_path != f"{link.trial_id}/result.json"
        ):
            raise AdmissionError("RESULT_ARTIFACT_MISMATCH")
        _parse_normalized_utc(link.linked_at)
        return link

    def get_budget(self, budget_id: str) -> BudgetDefinition:
        with self._connection() as connection:
            self._verify_schema(connection)
            row = connection.execute(
                "SELECT * FROM trial_budgets WHERE budget_id = ?", (budget_id,)
            ).fetchone()
        if row is None:
            raise AdmissionError("BUDGET_UNKNOWN")
        return self._budget(row)

    def get_reservation(self, trial_id: str) -> TrialReservation:
        with self._connection() as connection:
            self._verify_schema(connection)
            row = connection.execute(
                "SELECT * FROM trial_reservations WHERE trial_id = ?", (trial_id,)
            ).fetchone()
        if row is None:
            raise AdmissionError("TRIAL_RESERVATION_MISMATCH")
        return self._reservation(row)

    def latest_event(self, trial_id: str) -> TrialEvent:
        events = self.list_events(trial_id)
        if not events:
            raise AdmissionError("TRIAL_STATE_NOT_ADMITTED")
        return events[-1]

    def get_result_link(self, trial_id: str) -> TrialResultLink | None:
        with self._connection() as connection:
            self._verify_schema(connection)
            row = connection.execute(
                "SELECT * FROM trial_result_links WHERE trial_id = ?", (trial_id,)
            ).fetchone()
        return None if row is None else self._result_link(row)

    def list_budgets(self) -> tuple[BudgetDefinition, ...]:
        with self._connection() as connection:
            self._verify_schema(connection)
            rows = connection.execute(
                "SELECT * FROM trial_budgets ORDER BY budget_id"
            ).fetchall()
        return tuple(self._budget(row) for row in rows)

    def list_reservations(self) -> tuple[TrialReservation, ...]:
        with self._connection() as connection:
            self._verify_schema(connection)
            rows = connection.execute(
                "SELECT * FROM trial_reservations"
            ).fetchall()
        reservations = [self._reservation(row) for row in rows]
        reservations.sort(
            key=lambda item: (_parse_normalized_utc(item.reserved_at), item.trial_id)
        )
        return tuple(reservations)

    def list_events(self, trial_id: str | None = None) -> tuple[TrialEvent, ...]:
        with self._connection() as connection:
            self._verify_schema(connection)
            if trial_id is None:
                rows = connection.execute(
                    "SELECT * FROM trial_events "
                    "ORDER BY trial_id, sequence_number, event_id"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM trial_events WHERE trial_id = ? "
                    "ORDER BY sequence_number, event_id",
                    (trial_id,),
                ).fetchall()
        return tuple(self._event(row) for row in rows)

    def list_result_links(self) -> tuple[TrialResultLink, ...]:
        with self._connection() as connection:
            self._verify_schema(connection)
            rows = connection.execute(
                "SELECT * FROM trial_result_links ORDER BY trial_id"
            ).fetchall()
        return tuple(self._result_link(row) for row in rows)

    def _snapshot(self) -> _LedgerSnapshot:
        """Read and parse one consistent snapshot while retaining row failures."""

        with self._connection() as connection:
            self._verify_schema(connection)
            try:
                connection.execute("BEGIN")
                violations = connection.execute("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise ControlPlaneError(
                        "LEDGER_ROW_INTEGRITY_FAILURE",
                        "the ledger contains a foreign-key violation",
                    )
                raw_groups = tuple(
                    connection.execute(f"SELECT * FROM {table}").fetchall()
                    for table in _REQUIRED_SCHEMA
                )
                connection.commit()
            except ControlPlaneError:
                connection.rollback()
                raise
            except sqlite3.DatabaseError as error:
                connection.rollback()
                raise ControlPlaneError("LEDGER_UNAVAILABLE", str(error)) from error
        parsers = (self._budget, self._reservation, self._event, self._result_link)
        tables = tuple(_REQUIRED_SCHEMA)
        parsed: list[list[Any]] = [[], [], [], []]
        failures: list[_RowFailure] = []
        for index, rows in enumerate(raw_groups):
            for row in rows:
                try:
                    parsed[index].append(parsers[index](row))
                except (AdmissionError, KeyError, TypeError, ValueError) as error:
                    value = dict(row)
                    trial_id = value.get("trial_id")
                    failures.append(
                        _RowFailure(
                            table=tables[index],
                            reason_token=getattr(
                                error, "reason_token", "INTERNAL_INTEGRITY_FAILURE"
                            ),
                            trial_id=trial_id if isinstance(trial_id, str) else None,
                            identity=_row_identity(value),
                        )
                    )
        parsed[0].sort(key=lambda item: item.budget_id)
        parsed[1].sort(
            key=lambda item: (_parse_normalized_utc(item.reserved_at), item.trial_id)
        )
        parsed[2].sort(
            key=lambda item: (item.trial_id, item.sequence_number, item.event_id)
        )
        parsed[3].sort(key=lambda item: item.trial_id)
        return _LedgerSnapshot(
            budgets=tuple(parsed[0]),
            reservations=tuple(parsed[1]),
            events=tuple(parsed[2]),
            result_links=tuple(parsed[3]),
            failures=tuple(failures),
            raw_counts=tuple(len(rows) for rows in raw_groups),
        )
