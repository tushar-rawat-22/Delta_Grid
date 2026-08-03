"""Fail-closed, synthetic-only research admission without execution."""

from .control_registry import ControlRegistry
from .dataset_resolver import DatasetResolver
from .models import (
    AdmissionDecision,
    AdmissionError,
    BudgetDefinition,
    DatasetResolution,
    ResearchAdmissionRequest,
    TrialEvent,
    TrialResultLink,
    TrialReservation,
    ValidatedControl,
    canonical_hash,
    canonical_json,
)
from .service import ResearchAdmissionService
from .trial_ledger import ORIGINS, STATUSES, TERMINAL_STATUSES, TrialLedger

__all__ = [
    "AdmissionDecision",
    "AdmissionError",
    "BudgetDefinition",
    "ControlRegistry",
    "DatasetResolution",
    "DatasetResolver",
    "ORIGINS",
    "ResearchAdmissionRequest",
    "ResearchAdmissionService",
    "STATUSES",
    "TERMINAL_STATUSES",
    "TrialLedger",
    "TrialEvent",
    "TrialResultLink",
    "TrialReservation",
    "ValidatedControl",
    "canonical_hash",
    "canonical_json",
]
