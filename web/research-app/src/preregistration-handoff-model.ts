import {
  canonicalJson,
  type PreregistrationReview,
} from "./preregistration-model.ts";

export const PREREGISTRATION_HANDOFF_SCHEMA =
  "DELTAGRID_FOUNDER_PREREGISTRATION_HANDOFF_V2" as const;

export type CanonicalResolutionRequirement = {
  binding:
    | "development_dataset"
    | "development_permit"
    | "trial_budget_and_reservation"
    | "execution_family_and_variant"
    | "statistical_program";
  owner:
    | "M101_DATASET_DESCRIPTOR"
    | "M101_DEVELOPMENT_PERMIT"
    | "M94_TRIAL_LEDGER_VIA_M101"
    | "M102_SEALED_EXPERIMENT_REGISTRY"
    | "M103_PROGRAM_PROTOCOL";
  status: "UNRESOLVED";
  browser_writable: false;
  trusted_resolution_boundary: "LOCAL_OPERATOR_WORKFLOW_ONLY";
  required_fact: string;
};

export type PreregistrationHandoffCore = {
  schema_version: typeof PREREGISTRATION_HANDOFF_SCHEMA;
  source_review: {
    review_id: string;
    review_hash_sha256: string;
    canonical_review_json: string;
    record_id: string;
    revision: number;
    title: string;
  };
  boundary: "NON_RAB1_RESEARCH_ONLY";
  authority_effect: "NONE";
  handoff_status: "READY_FOR_TRUSTED_LOCAL_RESOLUTION";
  canonical_resolution_requirements: CanonicalResolutionRequirement[];
  browser_effects: {
    canonical_state_write: false;
    permit_issue: false;
    permit_consume: false;
    trial_reserve: false;
    execution_spec_claim: false;
    result_execution: false;
    protected_stage_open: false;
    mission104_authorize: false;
    trading_authorize: false;
  };
};

export type PreregistrationHandoffManifest = PreregistrationHandoffCore & {
  canonical_handoff_json: string;
  canonical_handoff_hash_sha256: string;
  handoff_id: string;
};

const REQUIREMENTS: CanonicalResolutionRequirement[] = [
  {
    binding: "development_dataset",
    owner: "M101_DATASET_DESCRIPTOR",
    status: "UNRESOLVED",
    browser_writable: false,
    trusted_resolution_boundary: "LOCAL_OPERATOR_WORKFLOW_ONLY",
    required_fact:
      "An exact certified REAL_MARKET_DEVELOPMENT dataset descriptor must be created and verified under Mission 101 before research admission.",
  },
  {
    binding: "development_permit",
    owner: "M101_DEVELOPMENT_PERMIT",
    status: "UNRESOLVED",
    browser_writable: false,
    trusted_resolution_boundary: "LOCAL_OPERATOR_WORKFLOW_ONLY",
    required_fact:
      "A founder-issued finite Mission 101 development permit must bind the exact repository, dataset, release and experiment family through the private authority runtime.",
  },
  {
    binding: "trial_budget_and_reservation",
    owner: "M94_TRIAL_LEDGER_VIA_M101",
    status: "UNRESOLVED",
    browser_writable: false,
    trusted_resolution_boundary: "LOCAL_OPERATOR_WORKFLOW_ONLY",
    required_fact:
      "The canonical Mission 94 budget and one exact trial reservation/admission chain must be established by Mission 101; reservation consumes finite capacity even if a later gate stops.",
  },
  {
    binding: "execution_family_and_variant",
    owner: "M102_SEALED_EXPERIMENT_REGISTRY",
    status: "UNRESOLVED",
    browser_writable: false,
    trusted_resolution_boundary: "LOCAL_OPERATOR_WORKFLOW_ONLY",
    required_fact:
      "A reviewed sealed Mission 102 family and exact preregistered variant definition must exist before any permitted result-bearing execution can be bound.",
  },
  {
    binding: "statistical_program",
    owner: "M103_PROGRAM_PROTOCOL",
    status: "UNRESOLVED",
    browser_writable: false,
    trusted_resolution_boundary: "LOCAL_OPERATOR_WORKFLOW_ONLY",
    required_fact:
      "A pre-result Mission 103 campaign/program protocol must freeze the complete inferential universe and required M94/M101/M102 identities before result-guided selection or protected-stage progression.",
  },
];

export async function compilePreregistrationHandoffManifest(
  review: PreregistrationReview,
): Promise<PreregistrationHandoffManifest> {
  await validateReview(review);
  const core: PreregistrationHandoffCore = {
    schema_version: PREREGISTRATION_HANDOFF_SCHEMA,
    source_review: {
      review_id: review.review_id,
      review_hash_sha256: review.canonical_review_hash_sha256,
      canonical_review_json: review.canonical_review_json,
      record_id: review.source_thesis.record_id,
      revision: review.source_thesis.revision,
      title: review.source_title,
    },
    boundary: "NON_RAB1_RESEARCH_ONLY",
    authority_effect: "NONE",
    handoff_status: "READY_FOR_TRUSTED_LOCAL_RESOLUTION",
    canonical_resolution_requirements: REQUIREMENTS.map((requirement) => ({
      ...requirement,
    })),
    browser_effects: {
      canonical_state_write: false,
      permit_issue: false,
      permit_consume: false,
      trial_reserve: false,
      execution_spec_claim: false,
      result_execution: false,
      protected_stage_open: false,
      mission104_authorize: false,
      trading_authorize: false,
    },
  };
  const canonical = canonicalJson(core);
  const digest = await sha256Hex(canonical);
  return {
    ...core,
    canonical_handoff_json: canonical,
    canonical_handoff_hash_sha256: digest,
    handoff_id: `founder-prereg-handoff-${digest}`,
  };
}

async function validateReview(review: PreregistrationReview): Promise<void> {
  if (!review.structural_lock_ready || review.blocking_reasons.length !== 0) {
    throw new Error("PREREGISTRATION_HANDOFF_STRUCTURAL_REVIEW_BLOCKED");
  }
  if (
    review.boundary !== "NON_RAB1_RESEARCH_ONLY" ||
    review.authority_effect !== "NONE"
  ) {
    throw new Error("PREREGISTRATION_HANDOFF_BOUNDARY_INVALID");
  }
  if (
    !/^[0-9a-f]{64}$/u.test(review.canonical_review_hash_sha256) ||
    review.review_id !== `founder-prereg-${review.canonical_review_hash_sha256}`
  ) {
    throw new Error("PREREGISTRATION_HANDOFF_REVIEW_IDENTITY_INVALID");
  }

  let canonicalReview: unknown;
  try {
    canonicalReview = JSON.parse(review.canonical_review_json);
  } catch {
    throw new Error("PREREGISTRATION_HANDOFF_REVIEW_CANONICAL_INVALID");
  }
  if (canonicalJson(canonicalReview) !== review.canonical_review_json) {
    throw new Error("PREREGISTRATION_HANDOFF_REVIEW_CANONICAL_INVALID");
  }
  if (await sha256Hex(review.canonical_review_json) !== review.canonical_review_hash_sha256) {
    throw new Error("PREREGISTRATION_HANDOFF_REVIEW_HASH_MISMATCH");
  }
  if (!canonicalReview || typeof canonicalReview !== "object") {
    throw new Error("PREREGISTRATION_HANDOFF_REVIEW_SOURCE_MISMATCH");
  }
  const core = canonicalReview as {
    source_thesis?: { record_id?: unknown; revision?: unknown };
    source_title?: unknown;
    boundary?: unknown;
    authority_effect?: unknown;
    canonical_bindings?: unknown;
    side_effects?: unknown;
  };
  if (
    core.source_thesis?.record_id !== review.source_thesis.record_id ||
    core.source_thesis?.revision !== review.source_thesis.revision ||
    core.source_title !== review.source_title ||
    core.boundary !== review.boundary ||
    core.authority_effect !== review.authority_effect ||
    canonicalJson(core.canonical_bindings) !== canonicalJson(review.canonical_bindings) ||
    canonicalJson(core.side_effects) !== canonicalJson(review.side_effects)
  ) {
    throw new Error("PREREGISTRATION_HANDOFF_REVIEW_SOURCE_MISMATCH");
  }

  const bindings = Object.values(review.canonical_bindings);
  if (
    bindings.some(
      (binding) => binding.status !== "UNRESOLVED" || binding.browser_writable !== false,
    )
  ) {
    throw new Error("PREREGISTRATION_HANDOFF_CANONICAL_BINDING_INVALID");
  }
  if (Object.values(review.side_effects).some((value) => value !== false)) {
    throw new Error("PREREGISTRATION_HANDOFF_SIDE_EFFECT_INVALID");
  }
}

async function sha256Hex(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}
