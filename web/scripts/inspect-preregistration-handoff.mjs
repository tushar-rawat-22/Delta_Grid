import { constants as fsConstants, closeSync, fstatSync, lstatSync, openSync, readFileSync, realpathSync } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HANDOFF_SCHEMA = "DELTAGRID_FOUNDER_PREREGISTRATION_HANDOFF_V2";
const REVIEW_SCHEMA = "DELTAGRID_FOUNDER_PREREGISTRATION_REVIEW_V1";
const MAX_BYTES = 512 * 1024;
const HASH_RE = /^[0-9a-f]{64}$/u;
const REVIEW_ID_RE = /^founder-prereg-[0-9a-f]{64}$/u;
const HANDOFF_ID_PREFIX = "founder-prereg-handoff-";

const REVIEW_HEADINGS = [
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
];

const EXPECTED_REVIEW_BINDINGS = {
  development_dataset: unresolvedReview("M101_DATASET_DESCRIPTOR"),
  development_permit: unresolvedReview("M101_DEVELOPMENT_PERMIT"),
  trial_budget_and_reservation: unresolvedReview("M94_TRIAL_LEDGER_VIA_M101"),
  execution_family_and_variant: unresolvedReview("M102_SEALED_EXPERIMENT_REGISTRY"),
  statistical_program: unresolvedReview("M103_PROGRAM_PROTOCOL"),
};

const EXPECTED_REVIEW_SIDE_EFFECTS = {
  persistence: false,
  trial_reserved: false,
  permit_consumed: false,
  execution_authorized: false,
  protected_evidence_opened: false,
  mission104_authorized: false,
  trading_authorized: false,
};

const EXPECTED_REQUIREMENTS = [
  requirement(
    "development_dataset",
    "M101_DATASET_DESCRIPTOR",
    "An exact certified REAL_MARKET_DEVELOPMENT dataset descriptor must be created and verified under Mission 101 before research admission.",
  ),
  requirement(
    "development_permit",
    "M101_DEVELOPMENT_PERMIT",
    "A founder-issued finite Mission 101 development permit must bind the exact repository, dataset, release and experiment family through the private authority runtime.",
  ),
  requirement(
    "trial_budget_and_reservation",
    "M94_TRIAL_LEDGER_VIA_M101",
    "The canonical Mission 94 budget and one exact trial reservation/admission chain must be established by Mission 101; reservation consumes finite capacity even if a later gate stops.",
  ),
  requirement(
    "execution_family_and_variant",
    "M102_SEALED_EXPERIMENT_REGISTRY",
    "A reviewed sealed Mission 102 family and exact preregistered variant definition must exist before any permitted result-bearing execution can be bound.",
  ),
  requirement(
    "statistical_program",
    "M103_PROGRAM_PROTOCOL",
    "A pre-result Mission 103 campaign/program protocol must freeze the complete inferential universe and required M94/M101/M102 identities before result-guided selection or protected-stage progression.",
  ),
];

const EXPECTED_BROWSER_EFFECTS = {
  canonical_state_write: false,
  permit_issue: false,
  permit_consume: false,
  trial_reserve: false,
  execution_spec_claim: false,
  result_execution: false,
  protected_stage_open: false,
  mission104_authorize: false,
  trading_authorize: false,
};

const RESOLUTION_PLAN = [
  plan(
    "M101_DATASET_DESCRIPTOR",
    "VERIFY_OR_PREPARE_EXACT_REAL_MARKET_DEVELOPMENT_DESCRIPTOR",
    "Confirm an exact certified release and development descriptor identity. Do not create or alter a descriptor from this verifier.",
  ),
  plan(
    "M101_DEVELOPMENT_PERMIT",
    "INSPECT_PRIVATE_AUTHORITY_RUNTIME_AND_PERMIT_ELIGIBILITY",
    "Inspect the trusted-local authority state and exact permit prerequisites. Do not issue, revoke, or consume a permit from this verifier.",
  ),
  plan(
    "M94_TRIAL_LEDGER_VIA_M101",
    "INSPECT_BUDGET_CAPACITY_AND_TRIAL_BINDING_PREREQUISITES",
    "Confirm the intended budget and reservation inputs before any acknowledged Mission 101 admission. Do not reserve a trial from this verifier.",
  ),
  plan(
    "M102_SEALED_EXPERIMENT_REGISTRY",
    "INSPECT_REVIEWED_FAMILY_AND_VARIANT_IDENTITY",
    "Confirm that a reviewed sealed family and exact preregistered variant can bind the proposed experiment. Do not claim an execution specification or run a result.",
  ),
  plan(
    "M103_PROGRAM_PROTOCOL",
    "PREPARE_PRE_RESULT_PROGRAM_BINDINGS_FOR_FOUNDER_REVIEW",
    "Prepare the complete inferential-universe and protected-stage inputs for a later separately authorized founder workflow. Do not admit, activate, or open a protected stage.",
  ),
];

export function inspectPreregistrationHandoffFile(inputPath) {
  if (typeof inputPath !== "string" || !inputPath) fail("HANDOFF_PATH_REQUIRED");
  if (!path.isAbsolute(inputPath)) fail("HANDOFF_PATH_ABSOLUTE_REQUIRED");

  const lexicalPath = path.normalize(inputPath);
  let stat;
  try {
    stat = lstatSync(lexicalPath);
  } catch {
    fail("HANDOFF_FILE_NOT_FOUND");
  }
  if (stat.isSymbolicLink()) fail("HANDOFF_SYMLINK_REJECTED");
  if (!stat.isFile()) fail("HANDOFF_REGULAR_FILE_REQUIRED");
  if (stat.size < 2 || stat.size > MAX_BYTES) fail("HANDOFF_FILE_SIZE_INVALID");

  let realPath;
  try {
    realPath = realpathSync.native(lexicalPath);
  } catch {
    fail("HANDOFF_REALPATH_FAILED");
  }
  if (realPath !== lexicalPath) fail("HANDOFF_PATH_ALIAS_REJECTED");

  let descriptor;
  try {
    descriptor = openSync(lexicalPath, fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW);
  } catch {
    fail("HANDOFF_OPEN_FAILED");
  }

  let raw;
  try {
    const opened = fstatSync(descriptor);
    if (!opened.isFile() || opened.size !== stat.size || opened.size > MAX_BYTES) {
      fail("HANDOFF_FILE_CHANGED_DURING_OPEN");
    }
    raw = readFileSync(descriptor, "utf8");
  } finally {
    closeSync(descriptor);
  }

  const canonicalText = raw.endsWith("\n") ? raw.slice(0, -1) : raw;
  if (!canonicalText || canonicalText.includes("\r") || raw.endsWith("\n\n")) {
    fail("HANDOFF_ENCODING_INVALID");
  }

  const handoff = parseJson(canonicalText, "HANDOFF_JSON_INVALID");
  if (canonicalJson(handoff) !== canonicalText) fail("HANDOFF_CANONICAL_JSON_INVALID");
  validateExactKeys(handoff, [
    "authority_effect",
    "boundary",
    "browser_effects",
    "canonical_resolution_requirements",
    "handoff_status",
    "schema_version",
    "source_review",
  ], "HANDOFF_SHAPE_INVALID");

  if (handoff.schema_version !== HANDOFF_SCHEMA) fail("HANDOFF_SCHEMA_UNSUPPORTED");
  if (handoff.boundary !== "NON_RAB1_RESEARCH_ONLY") fail("HANDOFF_BOUNDARY_INVALID");
  if (handoff.authority_effect !== "NONE") fail("HANDOFF_AUTHORITY_INVALID");
  if (handoff.handoff_status !== "READY_FOR_TRUSTED_LOCAL_RESOLUTION") {
    fail("HANDOFF_STATUS_INVALID");
  }
  if (canonicalJson(handoff.browser_effects) !== canonicalJson(EXPECTED_BROWSER_EFFECTS)) {
    fail("HANDOFF_BROWSER_EFFECT_INVALID");
  }
  if (
    canonicalJson(handoff.canonical_resolution_requirements) !==
    canonicalJson(EXPECTED_REQUIREMENTS)
  ) {
    fail("HANDOFF_REQUIREMENTS_INVALID");
  }

  const source = handoff.source_review;
  validateExactKeys(source, [
    "canonical_review_json",
    "record_id",
    "review_hash_sha256",
    "review_id",
    "revision",
    "title",
  ], "HANDOFF_SOURCE_REVIEW_SHAPE_INVALID");
  if (!HASH_RE.test(source.review_hash_sha256)) fail("HANDOFF_REVIEW_HASH_INVALID");
  if (!REVIEW_ID_RE.test(source.review_id)) fail("HANDOFF_REVIEW_ID_INVALID");
  if (source.review_id !== `founder-prereg-${source.review_hash_sha256}`) {
    fail("HANDOFF_REVIEW_IDENTITY_MISMATCH");
  }
  if (typeof source.record_id !== "string" || !source.record_id.trim()) {
    fail("HANDOFF_RECORD_ID_INVALID");
  }
  if (!Number.isInteger(source.revision) || source.revision < 1) {
    fail("HANDOFF_REVISION_INVALID");
  }
  if (typeof source.title !== "string" || !source.title.trim()) fail("HANDOFF_TITLE_INVALID");
  if (typeof source.canonical_review_json !== "string" || !source.canonical_review_json) {
    fail("HANDOFF_CANONICAL_REVIEW_MISSING");
  }

  const review = parseJson(source.canonical_review_json, "HANDOFF_REVIEW_JSON_INVALID");
  if (canonicalJson(review) !== source.canonical_review_json) {
    fail("HANDOFF_REVIEW_CANONICAL_JSON_INVALID");
  }
  const observedReviewHash = sha256(source.canonical_review_json);
  if (observedReviewHash !== source.review_hash_sha256) fail("HANDOFF_REVIEW_HASH_MISMATCH");
  validateReviewCore(review, source);

  const handoffHash = sha256(canonicalText);
  const handoffId = `${HANDOFF_ID_PREFIX}${handoffHash}`;
  const expectedFilename = `${handoffId}.json`;
  const basename = path.basename(lexicalPath);
  if (basename.startsWith(HANDOFF_ID_PREFIX) && basename !== expectedFilename) {
    fail("HANDOFF_FILENAME_IDENTITY_MISMATCH");
  }

  return {
    schema_version: "DELTAGRID_TRUSTED_LOCAL_PREREGISTRATION_INTAKE_V1",
    inspection_status: "VERIFIED_AUTHORITY_ZERO_HANDOFF",
    source_file: lexicalPath,
    source_file_bytes: stat.size,
    handoff_id: handoffId,
    handoff_hash_sha256: handoffHash,
    source_review_id: source.review_id,
    source_review_hash_sha256: observedReviewHash,
    source_record_id: source.record_id,
    source_revision: source.revision,
    source_title: source.title,
    boundary: "NON_RAB1_RESEARCH_ONLY",
    authority_effect: "NONE",
    writes_performed: false,
    permit_issued: false,
    permit_consumed: false,
    trial_reserved: false,
    execution_authorized: false,
    protected_evidence_opened: false,
    resolution_plan: RESOLUTION_PLAN.map((entry) => ({ ...entry })),
  };
}

function validateReviewCore(review, source) {
  validateExactKeys(review, [
    "authority_effect",
    "boundary",
    "canonical_bindings",
    "schema_version",
    "scientific_protocol",
    "side_effects",
    "source_thesis",
    "source_title",
  ], "HANDOFF_REVIEW_SHAPE_INVALID");
  if (review.schema_version !== REVIEW_SCHEMA) fail("HANDOFF_REVIEW_SCHEMA_INVALID");
  if (review.boundary !== "NON_RAB1_RESEARCH_ONLY" || review.authority_effect !== "NONE") {
    fail("HANDOFF_REVIEW_BOUNDARY_INVALID");
  }
  validateExactKeys(review.source_thesis, ["record_id", "revision"], "HANDOFF_REVIEW_SOURCE_INVALID");
  if (
    review.source_thesis.record_id !== source.record_id ||
    review.source_thesis.revision !== source.revision ||
    review.source_title !== source.title
  ) {
    fail("HANDOFF_REVIEW_SOURCE_MISMATCH");
  }
  if (canonicalJson(review.canonical_bindings) !== canonicalJson(EXPECTED_REVIEW_BINDINGS)) {
    fail("HANDOFF_REVIEW_BINDINGS_INVALID");
  }
  if (canonicalJson(review.side_effects) !== canonicalJson(EXPECTED_REVIEW_SIDE_EFFECTS)) {
    fail("HANDOFF_REVIEW_SIDE_EFFECTS_INVALID");
  }
  validateExactKeys(review.scientific_protocol, REVIEW_HEADINGS, "HANDOFF_REVIEW_PROTOCOL_INVALID");
  for (const heading of REVIEW_HEADINGS) {
    const text = review.scientific_protocol[heading];
    if (typeof text !== "string" || !text.trim()) fail("HANDOFF_REVIEW_SECTION_EMPTY");
    if (text.includes("[Founder:") || text.includes("[System:")) {
      fail("HANDOFF_REVIEW_PLACEHOLDER_REMAINS");
    }
  }
}

function canonicalJson(value) {
  return JSON.stringify(canonicalize(value));
}

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0)
        .map(([key, nested]) => [key, canonicalize(nested)]),
    );
  }
  if (
    value === null ||
    typeof value === "string" ||
    typeof value === "boolean" ||
    (typeof value === "number" && Number.isFinite(value))
  ) return value;
  fail("HANDOFF_CANONICAL_VALUE_INVALID");
}

function validateExactKeys(value, expected, reason) {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail(reason);
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) fail(reason);
}

function parseJson(value, reason) {
  try {
    return JSON.parse(value);
  } catch {
    fail(reason);
  }
}

function sha256(value) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function unresolvedReview(owner) {
  return { owner, status: "UNRESOLVED", browser_writable: false };
}

function requirement(binding, owner, requiredFact) {
  return {
    binding,
    owner,
    status: "UNRESOLVED",
    browser_writable: false,
    trusted_resolution_boundary: "LOCAL_OPERATOR_WORKFLOW_ONLY",
    required_fact: requiredFact,
  };
}

function plan(owner, nextCheck, description) {
  return {
    owner,
    status: "UNRESOLVED",
    next_check: nextCheck,
    description,
    mode: "READ_ONLY_PREPARATION_ONLY",
    canonical_write_authorized: false,
  };
}

function fail(reason) {
  const error = new Error(reason);
  error.reason = reason;
  throw error;
}

function isMainModule() {
  if (!process.argv[1]) return false;
  try {
    return realpathSync.native(process.argv[1]) === fileURLToPath(import.meta.url);
  } catch {
    return false;
  }
}

if (isMainModule()) {
  try {
    if (process.argv.length !== 3) fail("HANDOFF_EXACTLY_ONE_PATH_REQUIRED");
    const result = inspectPreregistrationHandoffFile(process.argv[2]);
    process.stdout.write(`${canonicalJson(result)}\n`);
  } catch (error) {
    const reason = error && typeof error === "object" && "reason" in error
      ? String(error.reason)
      : "HANDOFF_INSPECTION_FAILED";
    process.stderr.write(`${reason}\n`);
    process.exitCode = 2;
  }
}
