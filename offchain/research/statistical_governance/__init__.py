"""Independent statistical and protected-evidence governance (Mission 103)."""

from .core import GovernanceError, load_contracts
from .protocol import (
    proposal_commitment, validate_campaign_proposal, validate_partition_spec,
    validate_program_protocol, verify_development_binding,
)
from .registry import (
    ProtectedEvaluator, ProtectedEvaluatorRegistry, StatisticalAdapter,
    StatisticalAdapterRegistry, production_protected_evaluator_registry,
    production_statistical_adapter_registry,
)
from .integrations import M102ResultSource, ProtectedCustodySource
from .statistics import (
    PRNG_ID, SHA256CounterPRNG, derive_null_seed, empirical_one_sided,
    empirical_p_value, holm_step_down, minimum_repetitions,
    validate_monte_carlo_resolution,
)
from .store import (
    ACK_ACTIVATE_PROGRAM, ACK_ADMIT_CAMPAIGN, ACK_AUTHORIZE_STAGE, ACK_INITIALIZE, ACK_REVOKE_STAGE,
    activate_program, admit_campaign, authorize_stage, commit_campaign_proposal, create_program,
    derive_program_null_seed, initialize_governance, inspect_governance,
    open_protected_stage, qualify_development, record_development_result,
    recover_protected_stage, register_materialization, revoke_stage_authorization,
)

__all__ = [
    "GovernanceError", "load_contracts", "proposal_commitment",
    "validate_campaign_proposal", "validate_partition_spec", "validate_program_protocol",
    "verify_development_binding", "StatisticalAdapter", "StatisticalAdapterRegistry",
    "ProtectedEvaluator", "ProtectedEvaluatorRegistry", "M102ResultSource", "ProtectedCustodySource",
    "production_statistical_adapter_registry",
    "production_protected_evaluator_registry", "PRNG_ID", "SHA256CounterPRNG",
    "derive_null_seed", "empirical_one_sided", "empirical_p_value", "holm_step_down",
    "minimum_repetitions", "validate_monte_carlo_resolution", "ACK_INITIALIZE",
    "ACK_ADMIT_CAMPAIGN", "ACK_ACTIVATE_PROGRAM", "ACK_AUTHORIZE_STAGE", "ACK_REVOKE_STAGE",
    "initialize_governance", "commit_campaign_proposal", "admit_campaign", "create_program", "activate_program",
    "record_development_result", "qualify_development", "derive_program_null_seed",
    "register_materialization", "authorize_stage", "revoke_stage_authorization",
    "open_protected_stage", "recover_protected_stage", "inspect_governance",
]
