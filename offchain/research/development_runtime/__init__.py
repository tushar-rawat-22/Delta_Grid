"""Permitted event-driven REAL_MARKET_DEVELOPMENT execution runtime."""

from .artifacts import build_execution_specification, verify_development_result
from .authority import capture_authority_snapshot, read_trial_binding
from .core import (
    ACK_EXECUTE,
    ACK_INITIALIZE_RESULTS,
    AUTONOMY_V4_HASH,
    AUTONOMY_V4_ID,
    MISSION102_HASH,
    MISSION102_ID,
    DevelopmentRuntimeError,
    load_contracts,
)
from .finalizer import COMPLETION_REASON, finalize_verified_result
from .kernel import AccountingKernel, RevealedEvent, TargetExposureIntent
from .loader import MarketEvent, load_causal_events
from .registry import ExperimentRegistry, FamilyDefinition, VariantDefinition, production_registry
from .runtime import initialize_result_runtime, trial_lock
from .service import (
    execute_development_trial,
    inspect_development_results,
    plan_development_execution,
)

__all__ = [
    "ACK_EXECUTE", "ACK_INITIALIZE_RESULTS", "AUTONOMY_V4_HASH", "AUTONOMY_V4_ID",
    "MISSION102_HASH", "MISSION102_ID", "DevelopmentRuntimeError", "load_contracts",
    "capture_authority_snapshot", "read_trial_binding", "build_execution_specification",
    "verify_development_result", "COMPLETION_REASON", "finalize_verified_result",
    "AccountingKernel", "RevealedEvent", "TargetExposureIntent", "MarketEvent",
    "load_causal_events", "ExperimentRegistry", "FamilyDefinition", "VariantDefinition",
    "production_registry", "initialize_result_runtime", "trial_lock",
    "execute_development_trial", "inspect_development_results", "plan_development_execution",
]
