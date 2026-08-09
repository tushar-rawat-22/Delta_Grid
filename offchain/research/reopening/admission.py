"""Mission 101 metadata-only REAL_MARKET_DEVELOPMENT Admission V2."""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import stat
from typing import Any, Callable, Mapping
from urllib.parse import quote

from offchain.research.admission.models import AdmissionError
from offchain.research.admission.trial_ledger import ORIGINS, SCHEMA_SQL, TrialLedger

from .authority import _reserve_permit_capacity, verify_development_permit
from .core import (
    DATA_CLASS,
    DEVELOPMENT_STAGE,
    MISSION101_HASH,
    MISSION101_ID,
    REPOSITORY_ROOT,
    SPLIT_IDENTITY,
    ReopeningError,
    canonical_hash,
    get_repository_observation,
    parse_utc,
    require_commit,
    require_hash,
    require_identifier,
    load_contracts,
    trusted_utc_now,
)
from .dataset import verify_development_dataset_descriptor


REQUEST_FIELDS = {
    "schema_version", "request_id", "controlling_contract_id",
    "controlling_contract_hash", "repository_commit", "repository_clean",
    "budget_id", "declared_trial_number", "dataset_id", "dataset_descriptor_hash",
    "data_class", "split_identity", "permit_id", "permit_hash",
    "experiment_family", "authorization_stage", "initiated_by", "created_at",
    "canonical_request_hash",
}
ACK_REGISTER_BUDGET = "REGISTER_M101_DEVELOPMENT_TRIAL_BUDGET"
ACK_ADMIT_DEVELOPMENT = "RESERVE_M101_DEVELOPMENT_ADMISSION_TRIAL"
MAX_TRIAL_LEDGER_BYTES = 64 * 1024 * 1024


def _schema_rows(conn: sqlite3.Connection) -> list[tuple[Any, ...]]:
    return [
        tuple(row)
        for row in conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        ).fetchall()
    ]


def _expected_trial_ledger_schema_rows() -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(SCHEMA_SQL)
        return _schema_rows(conn)
    finally:
        conn.close()


EXPECTED_TRIAL_LEDGER_SCHEMA_ROWS = _expected_trial_ledger_schema_rows()


def _verify_trial_ledger_file(path: Path) -> None:
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise ReopeningError("TRIAL_LEDGER_PARENT_INVALID")
    if stat.S_IMODE(path.parent.stat().st_mode) != 0o700:
        raise ReopeningError("TRIAL_LEDGER_PARENT_MODE_INVALID")
    if path.is_symlink() or not path.is_file():
        raise ReopeningError("TRIAL_LEDGER_MISSING")
    details = path.stat()
    if stat.S_IMODE(details.st_mode) != 0o600:
        raise ReopeningError("TRIAL_LEDGER_FILE_MODE_INVALID")
    if details.st_size > MAX_TRIAL_LEDGER_BYTES:
        raise ReopeningError("TRIAL_LEDGER_SIZE_LIMIT")
    try:
        conn = sqlite3.connect(
            "file:" + quote(str(path), safe="/") + "?mode=ro", uri=True
        )
        conn.execute("PRAGMA query_only=ON")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ReopeningError("TRIAL_LEDGER_INTEGRITY_INVALID")
        if _schema_rows(conn) != EXPECTED_TRIAL_LEDGER_SCHEMA_ROWS:
            raise ReopeningError("TRIAL_LEDGER_SCHEMA_INVALID")
    except ReopeningError:
        raise
    except sqlite3.DatabaseError as error:
        raise ReopeningError("TRIAL_LEDGER_DATABASE_INVALID") from error
    finally:
        if "conn" in locals():
            conn.close()


def _trial_ledger_path(value: str | Path, *, must_exist: bool) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ReopeningError("TRIAL_LEDGER_PATH_NOT_ABSOLUTE")
    current = path
    while True:
        if current.is_symlink():
            raise ReopeningError("TRIAL_LEDGER_PATH_SYMLINK")
        if current == current.parent:
            break
        current = current.parent
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(REPOSITORY_ROOT.resolve(strict=True))
    except ValueError:
        pass
    else:
        raise ReopeningError("TRIAL_LEDGER_PATH_INSIDE_REPOSITORY")
    if must_exist:
        _verify_trial_ledger_file(resolved)
    elif resolved.exists():
        if resolved.is_symlink() or not resolved.is_file():
            raise ReopeningError("TRIAL_LEDGER_PATH_INVALID")
        _verify_trial_ledger_file(resolved)
    return resolved


def register_development_budget(
    database_path: str | Path,
    *,
    budget_id: str,
    experiment_family: str,
    total_trial_budget: int,
    created_at: str,
    acknowledgement: str,
) -> dict[str, Any]:
    """Register one Mission 101 budget through the unchanged Mission 94 ledger."""

    if acknowledgement != ACK_REGISTER_BUDGET:
        raise ReopeningError("BUDGET_REGISTRATION_ACKNOWLEDGEMENT_REQUIRED")
    path = _trial_ledger_path(database_path, must_exist=False)
    if not path.exists():
        parent_existed = path.parent.exists()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not parent_existed:
            os.chmod(path.parent, 0o700)
        if path.parent.is_symlink() or not path.parent.is_dir():
            raise ReopeningError("TRIAL_LEDGER_PARENT_INVALID")
        if stat.S_IMODE(path.parent.stat().st_mode) != 0o700:
            raise ReopeningError("TRIAL_LEDGER_PARENT_MODE_INVALID")
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags, 0o600)
        os.close(fd)
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise ReopeningError("TRIAL_LEDGER_FILE_MODE_INVALID")
        TrialLedger(path)
        _verify_trial_ledger_file(path)
    ledger = TrialLedger(path)
    budget = ledger.register_budget(
        budget_id=budget_id,
        controlling_contract_id=MISSION101_ID,
        controlling_contract_hash=MISSION101_HASH,
        experiment_family=experiment_family,
        total_trial_budget=total_trial_budget,
        created_at=created_at,
    )
    _verify_trial_ledger_file(path)
    return budget.as_dict()


def open_development_trial_ledger(database_path: str | Path) -> TrialLedger:
    """Open an existing safe trial ledger for Mission 101 admission."""

    path = _trial_ledger_path(database_path, must_exist=True)
    ledger = TrialLedger(path)
    _verify_trial_ledger_file(path)
    return ledger


def build_admission_request(**values: Any) -> dict[str, Any]:
    core = {
        "schema_version": "2.0",
        "controlling_contract_id": MISSION101_ID,
        "controlling_contract_hash": MISSION101_HASH,
        **values,
    }
    core["canonical_request_hash"] = canonical_hash(core)
    return core


def _parse_request(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != REQUEST_FIELDS:
        raise ReopeningError("REQUEST_SCHEMA_INVALID")
    request = dict(value)
    if request["schema_version"] != "2.0":
        raise ReopeningError("REQUEST_SCHEMA_INVALID")
    for field in ("request_id", "budget_id", "dataset_id", "permit_id", "experiment_family", "initiated_by"):
        require_identifier(request[field], field)
    require_commit(request["repository_commit"], "repository_commit")
    for field in ("controlling_contract_hash", "dataset_descriptor_hash", "permit_hash", "canonical_request_hash"):
        require_hash(request[field], field)
    if type(request["repository_clean"]) is not bool:
        raise ReopeningError("REQUEST_SCHEMA_INVALID")
    if type(request["declared_trial_number"]) is not int or request["declared_trial_number"] < 1:
        raise ReopeningError("DECLARED_TRIAL_NUMBER_INVALID")
    core = dict(request)
    supplied = core.pop("canonical_request_hash")
    if canonical_hash(core) != supplied:
        raise ReopeningError("REQUEST_HASH_MISMATCH")
    return request


class DevelopmentAdmissionService:
    """Reserve development eligibility and stop before any execution boundary."""

    def __init__(
        self,
        *,
        descriptor: Mapping[str, Any] | str,
        release_directory: str,
        custody_runtime_root: str,
        authority_root: str,
        trial_ledger: TrialLedger,
        time_provider: Callable[[], str] | None = None,
        repository_observer: Callable[[], Mapping[str, Any]] | None = None,
    ) -> None:
        load_contracts()
        if type(trial_ledger) is not TrialLedger:
            raise ReopeningError("TRIAL_LEDGER_TYPE_INVALID")
        _verify_trial_ledger_file(_trial_ledger_path(trial_ledger.database_path, must_exist=True))
        self._descriptor = descriptor
        self._release_directory = release_directory
        self._custody_runtime_root = custody_runtime_root
        self._authority_root = authority_root
        self._ledger = trial_ledger
        self._time_provider = time_provider or trusted_utc_now
        self._repository_observer = repository_observer

    def _decision_time(self) -> str:
        try:
            value = self._time_provider()
            parse_utc(value, "trusted_decision_time")
        except ReopeningError:
            raise
        except Exception as error:
            raise ReopeningError("TRUSTED_DECISION_TIME_INVALID") from error
        return value

    def _base(self, request: Mapping[str, Any]) -> dict[str, Any]:
        parsed = _parse_request(request)
        if parsed["controlling_contract_id"] != MISSION101_ID:
            raise ReopeningError("CONTRACT_ID_MISMATCH")
        if parsed["controlling_contract_hash"] != MISSION101_HASH:
            raise ReopeningError("CONTRACT_HASH_MISMATCH")
        if parsed["initiated_by"] not in ORIGINS:
            raise ReopeningError("INITIATED_BY_INVALID")
        return parsed

    def _substantive(
        self,
        request: Mapping[str, Any],
        *,
        decision_time: str,
        trial_id: str | None,
        repository_observation: Mapping[str, Any],
    ) -> tuple[str, str]:
        if parse_utc(request["created_at"], "created_at") > parse_utc(
            decision_time, "trusted_decision_time"
        ):
            raise ReopeningError("REQUEST_CREATED_AT_IN_FUTURE")
        if not repository_observation["clean"]:
            raise ReopeningError("DIRTY_REPOSITORY")
        if request["repository_commit"] != repository_observation["head"]:
            raise ReopeningError("REPOSITORY_COMMIT_MISMATCH")
        if request["repository_clean"] is not repository_observation["clean"]:
            raise ReopeningError("REPOSITORY_CLEAN_MISMATCH")
        if request["data_class"] != DATA_CLASS:
            if "VALIDATION" in request["data_class"]:
                raise ReopeningError("VALIDATION_FORBIDDEN")
            if "HOLDOUT" in request["data_class"]:
                raise ReopeningError("HOLDOUT_FORBIDDEN")
            raise ReopeningError("DATASET_CLASS_UNAUTHORIZED")
        if request["split_identity"] != SPLIT_IDENTITY:
            if "VALIDATION" in request["split_identity"]:
                raise ReopeningError("VALIDATION_FORBIDDEN")
            if "HOLDOUT" in request["split_identity"]:
                raise ReopeningError("HOLDOUT_FORBIDDEN")
            raise ReopeningError("DATASET_CLASS_UNAUTHORIZED")
        if request["authorization_stage"] != DEVELOPMENT_STAGE:
            raise ReopeningError("AUTHORIZATION_STAGE_MISMATCH")
        require_identifier(request["experiment_family"], "experiment_family")
        dataset = verify_development_dataset_descriptor(
            self._descriptor,
            release_directory=self._release_directory,
            runtime_root=self._custody_runtime_root,
        )
        if request["dataset_id"] != dataset["dataset_id"] or request["dataset_descriptor_hash"] != dataset["canonical_descriptor_hash"]:
            raise ReopeningError("DATASET_DESCRIPTOR_BINDING_MISMATCH")
        permit = verify_development_permit(
            self._authority_root,
            request["permit_id"],
            descriptor=dataset,
            release_directory=self._release_directory,
            custody_runtime_root=self._custody_runtime_root,
            repository_commit=request["repository_commit"],
            experiment_family=request["experiment_family"],
            authorization_stage=request["authorization_stage"],
            as_of=decision_time,
        )
        if request["permit_hash"] != permit["permit_hash"]:
            raise ReopeningError("PERMIT_HASH_MISMATCH")
        budget = self._ledger.get_budget(request["budget_id"])
        if budget.experiment_family != request["experiment_family"] or budget.total_trial_budget != permit["fixed_trial_budget"]:
            raise ReopeningError("BUDGET_DEFINITION_MISMATCH")
        if trial_id is not None:
            _reserve_permit_capacity(
                self._authority_root,
                permit_id=request["permit_id"],
                trial_id=trial_id,
                request_hash=request["canonical_request_hash"],
                budget_id=request["budget_id"],
                reserved_at=decision_time,
            )
        return dataset["canonical_descriptor_hash"], permit["permit_hash"]

    def preflight(self, request: Mapping[str, Any]) -> dict[str, Any]:
        parsed: Mapping[str, Any] = request
        dataset_hash = None
        permit_hash = None
        try:
            parsed = self._base(request)
            decision_time = self._decision_time()
            observation = get_repository_observation(self._repository_observer)
            self._ledger.check_reservable(
                budget_id=parsed["budget_id"],
                declared_trial_number=parsed["declared_trial_number"],
                request_hash=parsed["canonical_request_hash"],
                controlling_contract_id=parsed["controlling_contract_id"],
                controlling_contract_hash=parsed["controlling_contract_hash"],
            )
            dataset_hash, permit_hash = self._substantive(
                parsed,
                decision_time=decision_time,
                trial_id=None,
                repository_observation=observation,
            )
            return self._decision(parsed, None, "PRECHECK_PASS", "PRECHECK_GATES_PASSED", dataset_hash, permit_hash)
        except (ReopeningError, AdmissionError) as error:
            return self._decision(parsed, None, "PRECHECK_STOP", self._reason(error), dataset_hash, permit_hash)
        except Exception:
            return self._decision(parsed, None, "PRECHECK_STOP", "INTERNAL_INTEGRITY_FAILURE", dataset_hash, permit_hash)

    def admit(self, request: Mapping[str, Any]) -> dict[str, Any]:
        parsed: Mapping[str, Any] = request
        reservation = None
        dataset_hash = None
        permit_hash = None
        decision_time = None
        try:
            parsed = self._base(request)
            decision_time = self._decision_time()
            observation = get_repository_observation(self._repository_observer)
            reservation = self._ledger.reserve(
                budget_id=parsed["budget_id"],
                declared_trial_number=parsed["declared_trial_number"],
                request_hash=parsed["canonical_request_hash"],
                initiated_by=parsed["initiated_by"],
                reserved_at=decision_time,
                controlling_contract_id=parsed["controlling_contract_id"],
                controlling_contract_hash=parsed["controlling_contract_hash"],
            )
            dataset_hash, permit_hash = self._substantive(
                parsed,
                decision_time=decision_time,
                trial_id=reservation.trial_id,
                repository_observation=observation,
            )
            self._ledger.append_event(trial_id=reservation.trial_id, status_token="ADMITTED", reason_token="M101_DEVELOPMENT_ADMISSION_GATES_PASSED", event_timestamp=decision_time)
            return self._decision(parsed, reservation.trial_id, "ADMITTED", "M101_DEVELOPMENT_ADMISSION_GATES_PASSED", dataset_hash, permit_hash)
        except (ReopeningError, AdmissionError) as error:
            reason = self._reason(error)
            if reservation is not None:
                try:
                    self._ledger.append_event(trial_id=reservation.trial_id, status_token="STOPPED", reason_token=reason, event_timestamp=decision_time or parsed["created_at"])
                except AdmissionError:
                    reason = "INTERNAL_INTEGRITY_FAILURE"
            return self._decision(parsed, reservation.trial_id if reservation else None, "STOPPED", reason, dataset_hash, permit_hash)
        except Exception:
            if reservation is not None:
                try:
                    self._ledger.append_event(trial_id=reservation.trial_id, status_token="STOPPED", reason_token="INTERNAL_INTEGRITY_FAILURE", event_timestamp=decision_time or parsed.get("created_at", "UNSPECIFIED"))
                except Exception:
                    pass
            return self._decision(parsed, reservation.trial_id if reservation else None, "STOPPED", "INTERNAL_INTEGRITY_FAILURE", dataset_hash, permit_hash)

    @staticmethod
    def _reason(error: Exception) -> str:
        return str(getattr(error, "reason", getattr(error, "reason_token", "INTERNAL_INTEGRITY_FAILURE")))

    @staticmethod
    def _decision(request: Mapping[str, Any], trial_id: str | None, token: str, reason: str, dataset_hash: str | None, permit_hash: str | None) -> dict[str, Any]:
        core = {
            "schema_version": "2.0",
            "request_id": request.get("request_id", "INVALID_REQUEST") if isinstance(request, Mapping) else "INVALID_REQUEST",
            "trial_id": trial_id,
            "decision_token": token,
            "reason_token": reason,
            "dataset_descriptor_hash": dataset_hash,
            "permit_hash": permit_hash,
            "execution_authorized": False,
        }
        return {**core, "canonical_decision_hash": canonical_hash(core)}
