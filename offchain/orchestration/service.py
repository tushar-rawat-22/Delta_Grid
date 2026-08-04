"""Foreground service for the fixed Mission 97 durable observation workflow."""

from __future__ import annotations

import hmac
from pathlib import Path
import re
import sqlite3
from typing import Any, Callable, Mapping

from offchain.research.admission import canonical_hash, canonical_json

from .actions import _execute
from .definitions import (
    ACTION_BY_STEP,
    RESEARCH_OBSERVATION_REFRESH_V1,
    STEP_INDEX,
)
from .ledger import WorkflowLedger
from .models import (
    MISSION_CONTRACT_HASH,
    OrchestrationError,
    TickOutcome,
    TickResult,
    WorkflowRunSnapshot,
    WorkflowStatus,
)
from .strict_json import (
    add_seconds,
    parse_utc,
    resolve_existing,
    validate_identifier,
)


_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_RETRYABLE = frozenset(
    {
        "SQLITE_BUSY",
        "ORCHESTRATION_DATABASE_BUSY",
        "SNAPSHOT_TEMPORARILY_UNAVAILABLE",
        "ARTIFACT_TEMPORARILY_UNAVAILABLE",
        "LEASE_EXPIRED_BEFORE_FINALIZATION",
    }
)


class WorkflowOrchestrator:
    """Progress the one compiled workflow with explicit time and no sleeping."""

    def __init__(self, ledger: WorkflowLedger, *, lease_duration: int = 60) -> None:
        if not isinstance(ledger, WorkflowLedger):
            raise OrchestrationError("WORKFLOW_INPUT_INVALID", "ledger is required")
        if (
            type(lease_duration) is not int
            or not 5 <= lease_duration <= 3600
        ):
            raise OrchestrationError("WORKFLOW_INPUT_INVALID", "lease duration is invalid")
        self._ledger = ledger
        self._lease_duration = lease_duration

    @property
    def ledger(self) -> WorkflowLedger:
        return self._ledger

    @property
    def lease_duration(self) -> int:
        return self._lease_duration

    @staticmethod
    def _run_input(
        *,
        run_key: str,
        research_ledger_path: Path | str,
        result_root: Path | str,
        expected_repository_commit: str,
        observation_as_of: str,
        requested_at: str,
        requested_by: str,
    ) -> dict[str, Any]:
        validate_identifier(run_key)
        validate_identifier(requested_by)
        if (
            type(expected_repository_commit) is not str
            or _COMMIT_RE.fullmatch(expected_repository_commit) is None
        ):
            raise OrchestrationError("WORKFLOW_INPUT_INVALID")
        observation_time = parse_utc(observation_as_of)
        requested_time = parse_utc(requested_at)
        if observation_time > requested_time:
            raise OrchestrationError("WORKFLOW_INPUT_INVALID")
        ledger_path = resolve_existing(
            research_ledger_path,
            directory=False,
            reason="WORKFLOW_INPUT_INVALID",
        )
        results = resolve_existing(
            result_root,
            directory=True,
            reason="WORKFLOW_INPUT_INVALID",
        )
        value = {
            "run_key": run_key,
            "research_ledger_path": str(ledger_path),
            "result_root": str(results),
            "expected_repository_commit": expected_repository_commit,
            "observation_as_of": observation_as_of,
            "requested_at": requested_at,
            "requested_by": requested_by,
        }
        raw = canonical_json(value).encode("utf-8")
        if len(raw) > 65536:
            raise OrchestrationError("RESOURCE_LIMIT_EXCEEDED")
        return value

    def create_run(
        self,
        *,
        run_key: str,
        research_ledger_path: Path | str,
        result_root: Path | str,
        expected_repository_commit: str,
        observation_as_of: str,
        requested_at: str,
        requested_by: str,
    ) -> WorkflowRunSnapshot:
        inputs = self._run_input(
            run_key=run_key,
            research_ledger_path=research_ledger_path,
            result_root=result_root,
            expected_repository_commit=expected_repository_commit,
            observation_as_of=observation_as_of,
            requested_at=requested_at,
            requested_by=requested_by,
        )
        input_json = canonical_json(inputs)
        input_hash = canonical_hash(inputs)
        identity_core = {
            "mission_97_contract_hash": MISSION_CONTRACT_HASH,
            "workflow_definition_hash": (
                RESEARCH_OBSERVATION_REFRESH_V1.canonical_workflow_definition_hash
            ),
            "run_key": run_key,
            "canonical_input_hash": input_hash,
        }
        run_id = f"run-{canonical_hash(identity_core)[:32]}"
        core = {
            "run_id": run_id,
            "workflow_definition_id": (
                RESEARCH_OBSERVATION_REFRESH_V1.workflow_definition_id
            ),
            "workflow_definition_version": 1,
            "workflow_definition_hash": (
                RESEARCH_OBSERVATION_REFRESH_V1.canonical_workflow_definition_hash
            ),
            "run_key": run_key,
            "canonical_input_json": input_json,
            "canonical_input_hash": input_hash,
            "requested_at": requested_at,
            "requested_by": requested_by,
        }
        value = {**core, "canonical_run_hash": canonical_hash(core)}
        with self._ledger._mutation() as connection:
            existing = connection.execute(
                "SELECT * FROM workflow_runs WHERE run_key=?", (run_key,)
            ).fetchone()
            if existing is not None:
                current = self._ledger._verify_run(existing)
                if (
                    current["run_id"] != run_id
                    or current["canonical_input_hash"] != input_hash
                    or current["canonical_run_hash"] != value["canonical_run_hash"]
                ):
                    raise OrchestrationError("RUN_KEY_CONFLICT")
                snapshot = self._ledger._snapshot(
                    *self._ledger._run_data(connection, run_id)
                )
            else:
                connection.execute(
                    f"INSERT INTO workflow_runs ({','.join(value)}) "
                    f"VALUES ({','.join('?' for _ in value)})",
                    tuple(value.values()),
                )
                self._ledger._append_event(
                    connection,
                    run_id=run_id,
                    event_type="RUN_CREATED",
                    reason_token="WORKFLOW_RUN_REGISTERED",
                    event_timestamp=requested_at,
                    evidence_hash=value["canonical_run_hash"],
                )
                snapshot = self._ledger._snapshot(
                    *self._ledger._run_data(connection, run_id)
                )
        return snapshot

    def get_run(self, run_id: str) -> WorkflowRunSnapshot:
        validate_identifier(run_id)
        return self._ledger.get_run(run_id)

    def list_runs(self) -> tuple[WorkflowRunSnapshot, ...]:
        return self._ledger.list_runs()

    def cancel_run(
        self,
        run_id: str,
        requested_at: str,
        reason: str,
    ) -> WorkflowRunSnapshot:
        validate_identifier(run_id)
        parse_utc(requested_at)
        if type(reason) is not str or not reason or len(reason) > 1024:
            raise OrchestrationError("WORKFLOW_INPUT_INVALID")
        reason_hash = canonical_hash({"operator_reason": reason})
        with self._ledger._mutation() as connection:
            run, events, receipts, claim = self._ledger._run_data(connection, run_id)
            snapshot = self._ledger._snapshot(run, events, receipts, claim)
            if snapshot.status in {
                WorkflowStatus.COMPLETED,
                WorkflowStatus.FAILED,
                WorkflowStatus.CANCELLED,
            }:
                if snapshot.status == WorkflowStatus.CANCELLED:
                    return snapshot
                raise OrchestrationError("INVALID_WORKFLOW_TRANSITION")
            if parse_utc(requested_at) < parse_utc(events[-1]["event_timestamp"]):
                raise OrchestrationError(
                    "CLOCK_REGRESSION",
                    "cancellation time precedes the latest run event",
                )
            if not any(item["event_type"] == "RUN_CANCEL_REQUESTED" for item in events):
                self._ledger._append_event(
                    connection,
                    run_id=run_id,
                    event_type="RUN_CANCEL_REQUESTED",
                    reason_token="OPERATOR_CANCELLATION_REQUESTED",
                    event_timestamp=requested_at,
                    evidence_hash=reason_hash,
                )
            if claim is None:
                self._ledger._append_event(
                    connection,
                    run_id=run_id,
                    event_type="RUN_CANCELLED",
                    reason_token="OPERATOR_CANCELLED",
                    event_timestamp=requested_at,
                    evidence_hash=reason_hash,
                )
            result = self._ledger._snapshot(
                *self._ledger._run_data(connection, run_id)
            )
        return result

    @staticmethod
    def _action_input(
        run: Mapping[str, Any],
        step_id: str,
        receipts: list[Mapping[str, Any]],
    ) -> dict[str, Any]:
        if STEP_INDEX[step_id] == 0:
            return {
                "canonical_run_input": run["input"],
                "workflow_definition_id": run["workflow_definition_id"],
                "workflow_definition_version": run["workflow_definition_version"],
                "workflow_definition_hash": run["workflow_definition_hash"],
                "step_id": step_id,
                "action_id": ACTION_BY_STEP[step_id],
            }
        if STEP_INDEX[step_id] == 1:
            first = receipts[0]
            return {
                "source_receipt_id": first["receipt_id"],
                "source_receipt_hash": first["canonical_receipt_hash"],
                "source_artifact_id": first["artifact_id"],
                "source_artifact_relative_path": first["artifact_relative_path"],
                "source_artifact_byte_hash": first["artifact_byte_hash"],
                "source_artifact_canonical_hash": first["artifact_canonical_hash"],
                "expected_repository_commit": run["input"]["expected_repository_commit"],
                "observation_as_of": run["input"]["observation_as_of"],
            }
        return {
            "source_receipt_id": receipts[0]["receipt_id"],
            "source_receipt_hash": receipts[0]["canonical_receipt_hash"],
            "verification_receipt_id": receipts[1]["receipt_id"],
            "verification_receipt_hash": receipts[1]["canonical_receipt_hash"],
            "workflow_definition_id": run["workflow_definition_id"],
            "workflow_definition_version": run["workflow_definition_version"],
            "workflow_definition_hash": run["workflow_definition_hash"],
            "run_id": run["run_id"],
            "canonical_run_hash": run["canonical_run_hash"],
        }

    @staticmethod
    def _idempotency_key(run: Mapping[str, Any], step_id: str, action_input_hash: str) -> str:
        core = {
            "mission_97_contract_hash": MISSION_CONTRACT_HASH,
            "workflow_definition_hash": run["workflow_definition_hash"],
            "run_id": run["run_id"],
            "step_id": step_id,
            "action_id": ACTION_BY_STEP[step_id],
            "canonical_action_input_hash": action_input_hash,
        }
        return f"idempotency-{canonical_hash(core)}"

    def _claim_one(self, worker_id: str, now: str) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]] | None:
        with self._ledger._mutation() as connection:
            rows = connection.execute(
                "SELECT run_id FROM workflow_runs ORDER BY requested_at,run_id"
            ).fetchall()
            for row in rows:
                run, events, receipts, claim = self._ledger._run_data(
                    connection, str(row["run_id"])
                )
                snapshot = self._ledger._snapshot(run, events, receipts, claim)
                if claim is not None or snapshot.status in {
                    WorkflowStatus.COMPLETED,
                    WorkflowStatus.FAILED,
                    WorkflowStatus.CANCELLED,
                }:
                    continue
                if any(item["event_type"] == "RUN_CANCEL_REQUESTED" for item in events):
                    continue
                if (
                    snapshot.next_runnable_at is not None
                    and parse_utc(now) < parse_utc(snapshot.next_runnable_at)
                ):
                    continue
                step_id = snapshot.current_step_id
                attempt = snapshot.next_attempt_number
                if step_id is None or attempt is None:
                    continue
                action_input_hash = canonical_hash(
                    self._action_input(run, step_id, receipts)
                )
                fencing_epoch = len(events) + 1
                token_core = {
                    "mission_97_contract_hash": MISSION_CONTRACT_HASH,
                    "run_id": run["run_id"],
                    "step_id": step_id,
                    "attempt_number": attempt,
                    "fencing_epoch": fencing_epoch,
                    "worker_id": worker_id,
                    "claimed_at": now,
                }
                fencing_token = f"fence-v1-{canonical_hash(token_core)}"
                claim_core = {
                    "run_id": run["run_id"],
                    "step_id": step_id,
                    "attempt_number": attempt,
                    "fencing_epoch": fencing_epoch,
                    "worker_id": worker_id,
                    "fencing_token": fencing_token,
                    "claimed_at": now,
                    "lease_expires_at": add_seconds(now, self._lease_duration),
                }
                claim_value = {
                    **claim_core, "canonical_claim_hash": canonical_hash(claim_core)
                }
                self._ledger._append_event(
                    connection,
                    run_id=run["run_id"],
                    event_type="STEP_CLAIMED",
                    reason_token="STEP_CLAIM_ACCEPTED",
                    event_timestamp=now,
                    step_id=step_id,
                    attempt_number=attempt,
                    evidence_hash=claim_value["canonical_claim_hash"],
                )
                try:
                    self._ledger._insert_claim(connection, claim_value)
                except sqlite3.IntegrityError:
                    continue
                return run, receipts, {**claim_value, "action_input_hash": action_input_hash}
        return None

    @staticmethod
    def _verify_fencing(
        claim: Mapping[str, Any] | None,
        expected: Mapping[str, Any],
        *,
        now: str,
    ) -> None:
        if (
            claim is None
            or claim["worker_id"] != expected["worker_id"]
            or claim["step_id"] != expected["step_id"]
            or claim["attempt_number"] != expected["attempt_number"]
            or claim["fencing_epoch"] != expected["fencing_epoch"]
            or not hmac.compare_digest(
                str(claim["fencing_token"]), str(expected["fencing_token"])
            )
            or parse_utc(now) >= parse_utc(claim["lease_expires_at"])
        ):
            raise OrchestrationError("STALE_FENCING_TOKEN")
        if parse_utc(now) < parse_utc(claim["claimed_at"]):
            raise OrchestrationError(
                "CLOCK_REGRESSION",
                "finalization time precedes the accepted claim time",
            )

    def _finalize_success(
        self,
        run_id: str,
        claim_expected: Mapping[str, Any],
        result: Any,
        now: str,
    ) -> WorkflowRunSnapshot:
        with self._ledger._mutation() as connection:
            run, events, receipts, claim = self._ledger._run_data(connection, run_id)
            self._verify_fencing(claim, claim_expected, now=now)
            action_input_hash = canonical_hash(
                self._action_input(run, claim["step_id"], receipts)
            )
            if action_input_hash != claim_expected["action_input_hash"]:
                raise OrchestrationError("STALE_FENCING_TOKEN")
            idempotency_key = self._idempotency_key(
                run, claim["step_id"], action_input_hash
            )
            receipt_core = {
                "idempotency_key": idempotency_key,
                "run_id": run_id,
                "step_id": claim["step_id"],
                "action_id": ACTION_BY_STEP[claim["step_id"]],
                "canonical_action_input_hash": action_input_hash,
                "artifact_id": result.artifact_id,
                "artifact_relative_path": result.artifact_relative_path,
                "artifact_byte_hash": result.artifact_byte_hash,
                "artifact_canonical_hash": result.artifact_canonical_hash,
                "completed_at": now,
            }
            receipt = self._ledger._insert_receipt(connection, receipt_core)
            self._ledger._append_event(
                connection,
                run_id=run_id,
                event_type="STEP_SUCCEEDED",
                reason_token="ACTION_RECEIPT_ACCEPTED",
                event_timestamp=now,
                step_id=claim["step_id"],
                attempt_number=claim["attempt_number"],
                evidence_hash=receipt["canonical_receipt_hash"],
            )
            self._ledger._delete_claim(connection, run_id)
            cancelled = any(x["event_type"] == "RUN_CANCEL_REQUESTED" for x in events)
            if cancelled:
                self._ledger._append_event(
                    connection,
                    run_id=run_id,
                    event_type="RUN_CANCELLED",
                    reason_token="OPERATOR_CANCELLED",
                    event_timestamp=now,
                    evidence_hash=receipt["canonical_receipt_hash"],
                )
            elif claim["step_id"] == RESEARCH_OBSERVATION_REFRESH_V1.steps[-1].step_id:
                self._ledger._append_event(
                    connection,
                    run_id=run_id,
                    event_type="RUN_COMPLETED",
                    reason_token="WORKFLOW_COMPLETED",
                    event_timestamp=now,
                    evidence_hash=receipt["canonical_receipt_hash"],
                )
            return self._ledger._snapshot(
                *self._ledger._run_data(connection, run_id)
            )

    def _finalize_failure(
        self,
        run_id: str,
        claim_expected: Mapping[str, Any],
        reason_token: str,
        now: str,
    ) -> tuple[TickOutcome, WorkflowRunSnapshot]:
        with self._ledger._mutation() as connection:
            run, events, receipts, claim = self._ledger._run_data(connection, run_id)
            self._verify_fencing(claim, claim_expected, now=now)
            evidence = canonical_hash(
                {
                    "run_id": run_id,
                    "step_id": claim["step_id"],
                    "attempt_number": claim["attempt_number"],
                    "reason_token": reason_token,
                }
            )
            self._ledger._append_event(
                connection,
                run_id=run_id,
                event_type="STEP_ATTEMPT_FAILED",
                reason_token=reason_token,
                event_timestamp=now,
                step_id=claim["step_id"],
                attempt_number=claim["attempt_number"],
                evidence_hash=evidence,
            )
            self._ledger._delete_claim(connection, run_id)
            cancelled = any(x["event_type"] == "RUN_CANCEL_REQUESTED" for x in events)
            if cancelled:
                self._ledger._append_event(
                    connection,
                    run_id=run_id,
                    event_type="RUN_CANCELLED",
                    reason_token="OPERATOR_CANCELLED",
                    event_timestamp=now,
                    evidence_hash=evidence,
                )
                outcome = TickOutcome.RUN_CANCELLED
            elif reason_token in _RETRYABLE and claim["attempt_number"] < 3:
                delay = RESEARCH_OBSERVATION_REFRESH_V1.retry_delays_seconds[
                    claim["attempt_number"] - 1
                ]
                self._ledger._append_event(
                    connection,
                    run_id=run_id,
                    event_type="STEP_RETRY_SCHEDULED",
                    reason_token=reason_token,
                    event_timestamp=now,
                    step_id=claim["step_id"],
                    attempt_number=claim["attempt_number"],
                    not_before_at=add_seconds(now, delay),
                    evidence_hash=evidence,
                )
                outcome = TickOutcome.STEP_RETRY_SCHEDULED
            else:
                self._ledger._append_event(
                    connection,
                    run_id=run_id,
                    event_type="RUN_FAILED",
                    reason_token=reason_token,
                    event_timestamp=now,
                    step_id=claim["step_id"],
                    attempt_number=claim["attempt_number"],
                    evidence_hash=evidence,
                )
                outcome = TickOutcome.STEP_TERMINALLY_FAILED
            snapshot = self._ledger._snapshot(
                *self._ledger._run_data(connection, run_id)
            )
        return outcome, snapshot

    def recover_expired_claims(self, now: str) -> tuple[WorkflowRunSnapshot, ...]:
        parse_utc(now)
        recovered: list[WorkflowRunSnapshot] = []
        with self._ledger._mutation() as connection:
            rows = connection.execute(
                "SELECT c.run_id FROM workflow_claims AS c "
                "JOIN workflow_runs AS r ON r.run_id=c.run_id "
                "ORDER BY c.lease_expires_at, r.requested_at, c.run_id, "
                "CASE c.step_id "
                "WHEN 'CAPTURE_CONTROL_PLANE_SNAPSHOT' THEN 1 "
                "WHEN 'VERIFY_CONTROL_PLANE_SNAPSHOT' THEN 2 "
                "WHEN 'PUBLISH_OBSERVATION_MANIFEST' THEN 3 ELSE 4 END"
            ).fetchall()
            for row in rows:
                run_id = str(row["run_id"])
                run, events, receipts, claim = self._ledger._run_data(connection, run_id)
                if claim is None:
                    continue
                if parse_utc(now) < parse_utc(claim["claimed_at"]):
                    raise OrchestrationError(
                        "CLOCK_REGRESSION",
                        "recovery time precedes the accepted claim time",
                    )
                if parse_utc(claim["lease_expires_at"]) > parse_utc(now):
                    continue
                evidence = claim["canonical_claim_hash"]
                self._ledger._append_event(
                    connection,
                    run_id=run_id,
                    event_type="STEP_LEASE_EXPIRED",
                    reason_token="LEASE_EXPIRED_BEFORE_FINALIZATION",
                    event_timestamp=now,
                    step_id=claim["step_id"],
                    attempt_number=claim["attempt_number"],
                    evidence_hash=evidence,
                )
                self._ledger._delete_claim(connection, run_id)
                if any(x["event_type"] == "RUN_CANCEL_REQUESTED" for x in events):
                    self._ledger._append_event(
                        connection,
                        run_id=run_id,
                        event_type="RUN_CANCELLED",
                        reason_token="OPERATOR_CANCELLED",
                        event_timestamp=now,
                        evidence_hash=evidence,
                    )
                elif claim["attempt_number"] < 3:
                    delay = RESEARCH_OBSERVATION_REFRESH_V1.retry_delays_seconds[
                        claim["attempt_number"] - 1
                    ]
                    self._ledger._append_event(
                        connection,
                        run_id=run_id,
                        event_type="STEP_RETRY_SCHEDULED",
                        reason_token="LEASE_EXPIRED_BEFORE_FINALIZATION",
                        event_timestamp=now,
                        step_id=claim["step_id"],
                        attempt_number=claim["attempt_number"],
                        not_before_at=add_seconds(now, delay),
                        evidence_hash=evidence,
                    )
                else:
                    self._ledger._append_event(
                        connection,
                        run_id=run_id,
                        event_type="RUN_FAILED",
                        reason_token="LEASE_EXPIRED_BEFORE_FINALIZATION",
                        event_timestamp=now,
                        step_id=claim["step_id"],
                        attempt_number=claim["attempt_number"],
                        evidence_hash=evidence,
                    )
                recovered.append(
                    self._ledger._snapshot(
                        *self._ledger._run_data(connection, run_id)
                    )
                )
        return tuple(recovered)

    def tick(self, worker_id: str, now: str) -> TickResult:
        validate_identifier(worker_id)
        parse_utc(now)
        recovered = self.recover_expired_claims(now)
        if recovered:
            last = recovered[-1]
            outcome = (
                TickOutcome.RUN_CANCELLED
                if last.status == WorkflowStatus.CANCELLED
                else TickOutcome.EXPIRED_CLAIM_RECOVERED
            )
            return TickResult(outcome, last)
        claimed = self._claim_one(worker_id, now)
        if claimed is None:
            return TickResult(TickOutcome.IDLE, None)
        run, receipts, claim = claimed
        action_input_hash = claim["action_input_hash"]
        idempotency_key = self._idempotency_key(
            run, claim["step_id"], action_input_hash
        )
        try:
            result = _execute(
                step_id=claim["step_id"],
                output_root=self._ledger.output_root,
                governance_root=self._ledger.governance_repository_root,
                run=run,
                receipts=receipts,
                idempotency_key=idempotency_key,
            )
        except OrchestrationError as error:
            outcome, snapshot = self._finalize_failure(
                run["run_id"], claim, error.reason_token, now
            )
            return TickResult(outcome, snapshot)
        except (KeyboardInterrupt, SystemExit, GeneratorExit):
            raise
        except Exception as error:
            outcome, snapshot = self._finalize_failure(
                run["run_id"], claim, "INTERNAL_INTEGRITY_FAILURE", now
            )
            if outcome is TickOutcome.STEP_TERMINALLY_FAILED:
                return TickResult(outcome, snapshot)
            raise OrchestrationError("INTERNAL_INTEGRITY_FAILURE") from error
        snapshot = self._finalize_success(run["run_id"], claim, result, now)
        return TickResult(TickOutcome.STEP_SUCCEEDED, snapshot)

    def run_until_idle(
        self,
        worker_id: str,
        now_provider: Callable[[], str],
        max_ticks: int,
    ) -> tuple[TickResult, ...]:
        validate_identifier(worker_id)
        if type(max_ticks) is not int or not 1 <= max_ticks <= 10000:
            raise OrchestrationError("WORKFLOW_INPUT_INVALID")
        if not callable(now_provider):
            raise OrchestrationError("WORKFLOW_INPUT_INVALID")
        outcomes: list[TickResult] = []
        previous_now: str | None = None
        for _ in range(max_ticks):
            now = now_provider()
            parse_utc(now)
            if (
                previous_now is not None
                and parse_utc(now) < parse_utc(previous_now)
            ):
                raise OrchestrationError(
                    "CLOCK_REGRESSION",
                    "now_provider returned a decreasing timestamp",
                )
            previous_now = now
            result = self.tick(worker_id, now)
            outcomes.append(result)
            if result.outcome == TickOutcome.IDLE:
                return tuple(outcomes)
        outcomes.append(TickResult(TickOutcome.MAX_TICKS_REACHED, None))
        return tuple(outcomes)
