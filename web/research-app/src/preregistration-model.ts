export const PREREGISTRATION_SCHEMA =
  "DELTAGRID_FOUNDER_PREREGISTRATION_REVIEW_V1" as const;

export const PREREGISTRATION_BOUNDARY =
  "NON_RAB1_RESEARCH_ONLY" as const;

export const PREREGISTRATION_AUTHORITY = "NONE" as const;

export const PREREGISTRATION_HEADINGS = [
  "OBSERVATION",
  "ECONOMIC MECHANISM",
  "FALSIFICATION CONDITION",
  "DATA AND CHRONOLOGY",
  "TEST PLAN",
  "CANDIDATE AND PARAMETER BUDGET",
  "COST AND EXECUTION ASSUMPTIONS",
  "MULTIPLE-TESTING FAMILY",
  "SUCCESS AND FAILURE RULE",
  "NEXT REVIEW",
] as const;

type Heading = (typeof PREREGISTRATION_HEADINGS)[number];

export type PreregistrationThesisInput = {
  record_id: string;
  revision: number;
  title: string;
  body: string;
};

export type CanonicalBindingOwner =
  | "M101_DATASET_DESCRIPTOR"
  | "M101_DEVELOPMENT_PERMIT"
  | "M94_TRIAL_LEDGER_VIA_M101"
  | "M102_SEALED_EXPERIMENT_REGISTRY"
  | "M103_PROGRAM_PROTOCOL";

export type CanonicalBinding = {
  owner: CanonicalBindingOwner;
  status: "UNRESOLVED";
  browser_writable: false;
};

export type PreregistrationReviewCore = {
  schema_version: typeof PREREGISTRATION_SCHEMA;
  source_thesis: {
    record_id: string;
    revision: number;
  };
  source_title: string;
  scientific_protocol: Record<Heading, string>;
  canonical_bindings: {
    development_dataset: CanonicalBinding;
    development_permit: CanonicalBinding;
    trial_budget_and_reservation: CanonicalBinding;
    execution_family_and_variant: CanonicalBinding;
    statistical_program: CanonicalBinding;
  };
  boundary: typeof PREREGISTRATION_BOUNDARY;
  authority_effect: typeof PREREGISTRATION_AUTHORITY;
  side_effects: {
    persistence: false;
    trial_reserved: false;
    permit_consumed: false;
    execution_authorized: false;
    protected_evidence_opened: false;
    mission104_authorized: false;
    trading_authorized: false;
  };
};

export type PreregistrationReview = PreregistrationReviewCore & {
  scientific_lock_ready: boolean;
  blocking_reasons: string[];
  canonical_review_json: string;
  canonical_review_hash_sha256: string;
  review_id: string;
};

const PLACEHOLDER_PREFIXES = ["[Founder:", "[System:"] as const;

export async function compilePreregistrationReview(
  thesis: PreregistrationThesisInput,
): Promise<PreregistrationReview> {
  validateThesisIdentity(thesis);
  const protocol = parseScientificProtocol(thesis.body);
  const blockingReasons = readinessReasons(protocol);
  const core: PreregistrationReviewCore = {
    schema_version: PREREGISTRATION_SCHEMA,
    source_thesis: {
      record_id: thesis.record_id,
      revision: thesis.revision,
    },
    source_title: thesis.title.trim(),
    scientific_protocol: protocol,
    canonical_bindings: {
      development_dataset: unresolved("M101_DATASET_DESCRIPTOR"),
      development_permit: unresolved("M101_DEVELOPMENT_PERMIT"),
      trial_budget_and_reservation: unresolved("M94_TRIAL_LEDGER_VIA_M101"),
      execution_family_and_variant: unresolved("M102_SEALED_EXPERIMENT_REGISTRY"),
      statistical_program: unresolved("M103_PROGRAM_PROTOCOL"),
    },
    boundary: PREREGISTRATION_BOUNDARY,
    authority_effect: PREREGISTRATION_AUTHORITY,
    side_effects: {
      persistence: false,
      trial_reserved: false,
      permit_consumed: false,
      execution_authorized: false,
      protected_evidence_opened: false,
      mission104_authorized: false,
      trading_authorized: false,
    },
  };
  const canonical = canonicalJson(core);
  const digest = await sha256Hex(canonical);
  return {
    ...core,
    scientific_lock_ready: blockingReasons.length === 0,
    blocking_reasons: blockingReasons,
    canonical_review_json: canonical,
    canonical_review_hash_sha256: digest,
    review_id: `founder-prereg-${digest}`,
  };
}

export function parseScientificProtocol(body: string): Record<Heading, string> {
  if (typeof body !== "string") {
    throw new Error("PREREGISTRATION_BODY_INVALID");
  }

  const positions = PREREGISTRATION_HEADINGS.map((heading) => ({
    heading,
    index: body.indexOf(`\n${heading}\n`) >= 0
      ? body.indexOf(`\n${heading}\n`) + 1
      : body.startsWith(`${heading}\n`)
        ? 0
        : -1,
  }));

  if (positions.some(({ index }) => index < 0)) {
    throw new Error("PREREGISTRATION_SECTION_MISSING");
  }

  for (let index = 1; index < positions.length; index += 1) {
    if (positions[index].index <= positions[index - 1].index) {
      throw new Error("PREREGISTRATION_SECTION_ORDER_INVALID");
    }
  }

  const result = {} as Record<Heading, string>;
  for (let index = 0; index < positions.length; index += 1) {
    const current = positions[index];
    const contentStart = current.index + current.heading.length + 1;
    const contentEnd = index + 1 < positions.length
      ? positions[index + 1].index - 1
      : body.length;
    result[current.heading] = body.slice(contentStart, contentEnd).trim();
  }
  return result;
}

export function canonicalJson(value: unknown): string {
  return JSON.stringify(canonicalize(value));
}

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(canonicalize);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0)
        .map(([key, nested]) => [key, canonicalize(nested)]),
    );
  }
  if (
    value === null ||
    typeof value === "string" ||
    typeof value === "boolean" ||
    (typeof value === "number" && Number.isFinite(value))
  ) {
    return value;
  }
  throw new Error("PREREGISTRATION_CANONICAL_VALUE_INVALID");
}

function readinessReasons(protocol: Record<Heading, string>): string[] {
  const reasons: string[] = [];
  for (const heading of PREREGISTRATION_HEADINGS) {
    const content = protocol[heading];
    if (!content) {
      reasons.push(`EMPTY_SECTION:${heading}`);
      continue;
    }
    if (
      PLACEHOLDER_PREFIXES.some((prefix) => content.includes(prefix))
    ) {
      reasons.push(`PLACEHOLDER_REMAINS:${heading}`);
    }
  }
  return reasons;
}

function unresolved(owner: CanonicalBindingOwner): CanonicalBinding {
  return {
    owner,
    status: "UNRESOLVED",
    browser_writable: false,
  };
}

function validateThesisIdentity(thesis: PreregistrationThesisInput): void {
  if (
    typeof thesis.record_id !== "string" ||
    !thesis.record_id.trim() ||
    !Number.isInteger(thesis.revision) ||
    thesis.revision < 1 ||
    typeof thesis.title !== "string" ||
    !thesis.title.trim()
  ) {
    throw new Error("PREREGISTRATION_THESIS_IDENTITY_INVALID");
  }
}

async function sha256Hex(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}
