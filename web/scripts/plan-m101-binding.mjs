import { createHash } from "node:crypto";
import { readFileSync, realpathSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { inspectPreregistrationHandoffFile } from "./inspect-preregistration-handoff.mjs";

const SUPPORTED_SYMBOLS = new Set(["BTCUSDT", "ETHUSDT", "SOLUSDT"]);
const PROVIDER = "BINANCE_PUBLIC";
const STREAM = "spot_ohlcv";
const INTERVAL = "1h";

export function planM101BindingFromHandoff(inputPath) {
  const inspected = inspectPreregistrationHandoffFile(inputPath);

  const raw = readFileSync(inputPath, "utf8");
  const canonicalText = raw.endsWith("\n") ? raw.slice(0, -1) : raw;
  if (sha256(canonicalText) !== inspected.handoff_hash_sha256) fail("M101_PLAN_HANDOFF_CHANGED_AFTER_INSPECTION");

  const handoff = JSON.parse(canonicalText);
  const review = JSON.parse(handoff.source_review.canonical_review_json);
  const protocol = review.scientific_protocol;
  const dataSection = protocol["DATA AND CHRONOLOGY"];
  const budgetSection = protocol["CANDIDATE AND PARAMETER BUDGET"];

  if (typeof dataSection !== "string" || typeof budgetSection !== "string") {
    fail("M101_PLAN_PROTOCOL_SECTIONS_INVALID");
  }
  if (!dataSection.includes("Binance public spot OHLCV")) fail("M101_PLAN_PROVIDER_DECLARATION_UNSUPPORTED");
  if (!dataSection.includes("settled one-hour")) fail("M101_PLAN_INTERVAL_DECLARATION_UNSUPPORTED");

  const instrument = exactLineValue(budgetSection, "Instrument");
  const benchmark = exactLineValue(budgetSection, "Benchmark");
  if (instrument === benchmark) fail("M101_PLAN_DISTINCT_SYMBOLS_REQUIRED");
  for (const symbol of [instrument, benchmark]) {
    if (!SUPPORTED_SYMBOLS.has(symbol)) fail("M101_PLAN_SYMBOL_UNSUPPORTED");
  }

  const symbols = [instrument, benchmark].sort();
  const unresolved = {
    certified_release_id: "UNRESOLVED_TRUSTED_LOCAL_FACT",
    release_core_hash: "UNRESOLVED_TRUSTED_LOCAL_FACT",
    release_certificate_hash: "UNRESOLVED_TRUSTED_LOCAL_FACT",
    temporal_start: "UNRESOLVED_TRUSTED_LOCAL_FACT",
    temporal_end_as_of: "UNRESOLVED_TRUSTED_LOCAL_FACT",
    causal_availability_cutoff: "UNRESOLVED_TRUSTED_LOCAL_FACT",
    provenance_reference: "UNRESOLVED_TRUSTED_LOCAL_FACT",
    descriptor_destination: "UNRESOLVED_TRUSTED_LOCAL_FACT",
    authority_root: "UNRESOLVED_TRUSTED_LOCAL_FACT",
    trial_ledger: "UNRESOLVED_TRUSTED_LOCAL_FACT",
    experiment_family: "UNRESOLVED_TRUSTED_LOCAL_FACT",
    budget_id: "UNRESOLVED_TRUSTED_LOCAL_FACT",
    fixed_trial_budget: "UNRESOLVED_TRUSTED_LOCAL_FACT",
    permit_expiry: "UNRESOLVED_TRUSTED_LOCAL_FACT",
    m94_request_and_reservation_identity: "UNRESOLVED_TRUSTED_LOCAL_FACT",
    m102_registry_snapshot_identity: "UNRESOLVED_TRUSTED_LOCAL_FACT",
    m102_family_variant_identity: "UNRESOLVED_TRUSTED_LOCAL_FACT",
    m103_campaign_program_identity: "UNRESOLVED_TRUSTED_LOCAL_FACT",
  };

  const core = {
    schema_version: "DELTAGRID_M101_HANDOFF_BINDING_PLAN_V1",
    status: "READY_FOR_TRUSTED_LOCAL_FACT_RESOLUTION",
    source_handoff: {
      handoff_id: inspected.handoff_id,
      handoff_hash_sha256: inspected.handoff_hash_sha256,
      review_id: inspected.source_review_id,
      review_hash_sha256: inspected.source_review_hash_sha256,
      record_id: inspected.source_record_id,
      revision: inspected.source_revision,
      title: inspected.source_title,
    },
    declared_development_intent: {
      provider: PROVIDER,
      symbols,
      primary_instrument: instrument,
      benchmark,
      streams: [STREAM],
      stream_intervals: { [STREAM]: INTERVAL },
      data_class: "REAL_MARKET_DEVELOPMENT",
      split_identity: "REAL_MARKET_DEVELOPMENT",
    },
    unresolved_trusted_local_facts: unresolved,
    resolution_sequence: [
      step(1, "M101_CONTRACT", "VERIFY_M101_CONTRACT_AND_CLOSED_RESULT_AUTHORITY", true, false),
      step(2, "M101_DATASET_DESCRIPTOR", "CERTIFY_EXISTING_FORWARD_RELEASE", true, false),
      step(3, "M102_SEALED_EXPERIMENT_REGISTRY", "VERIFY_STABLE_REGISTRY_FAMILY_AND_VARIANT_IDENTITY", true, false),
      step(4, "M101_DEVELOPMENT_PERMIT", "INSPECT_PRIVATE_AUTHORITY_RUNTIME", true, false),
      step(5, "M101_DATASET_DESCRIPTOR", "CREATE_EXACT_DEVELOPMENT_DATASET_DESCRIPTOR", false, true),
      step(6, "M101_DEVELOPMENT_PERMIT", "INITIALIZE_PRIVATE_AUTHORITY_RUNTIME_IF_ABSENT", false, true),
      step(7, "M101_DEVELOPMENT_PERMIT", "ISSUE_FINITE_DEVELOPMENT_PERMIT", false, true),
      step(8, "M94_TRIAL_LEDGER_VIA_M101", "REGISTER_FINITE_DEVELOPMENT_BUDGET", false, true),
      step(9, "M94_TRIAL_LEDGER_VIA_M101", "ADMIT_ONE_METADATA_ONLY_DEVELOPMENT_TRIAL", false, true),
      step(10, "M103_PROGRAM_PROTOCOL", "PREPARE_AND_FREEZE_PRE_RESULT_PROGRAM_BINDINGS", false, true),
      step(11, "M103_PROGRAM_PROTOCOL", "FOUNDER_ACTIVATE_EXACT_FROZEN_PROGRAM_BEFORE_RESULTS", false, true),
    ],
    dependency_invariants: [
      "ALL_READ_ONLY_ELIGIBILITY_CHECKS_PRECEDE_CANONICAL_WRITES",
      "M102_STABLE_FAMILY_IDENTITY_PRECEDES_M101_PERMIT_ISSUANCE",
      "M101_PERMIT_AND_M94_BUDGET_PRECEDE_METADATA_ONLY_ADMISSION",
      "M101_ADMISSION_PRECEDES_RESULT_BEARING_M102_EXECUTION",
      "M103_PRE_RESULT_PROGRAM_BINDS_EXACT_M94_M101_AND_STABLE_M102_IDENTITIES",
      "M103_FOUNDER_ACTIVATION_PRECEDES_RESULT_BEARING_EXECUTION_AUTHORITY",
    ],
    stop_boundary: "PLAN_STOPS_BEFORE_RESULT_BEARING_M102_EXECUTION",
    execution_boundary: {
      planner_mode: "READ_ONLY_PREPARATION_ONLY",
      commands_executed: false,
      writes_performed: false,
      descriptor_created: false,
      authority_runtime_created: false,
      permit_issued: false,
      permit_consumed: false,
      budget_registered: false,
      trial_reserved: false,
      development_admitted: false,
      m103_campaign_admitted: false,
      m103_program_frozen: false,
      m103_program_activated: false,
      result_execution_authorized: false,
      protected_evidence_opened: false,
      mission104_authorized: false,
      trading_authorized: false,
      capital_authorized: false,
      authority_effect: "NONE",
    },
  };

  const canonicalCore = canonicalJson(core);
  const planHash = sha256(canonicalCore);
  return { ...core, plan_id: `m101-binding-plan-${planHash}`, plan_hash_sha256: planHash };
}

function exactLineValue(section, label) {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&");
  const matches = [...section.matchAll(new RegExp(`^${escaped}: ([A-Z0-9]+)\\.$`, "gmu"))];
  if (matches.length !== 1) fail(`M101_PLAN_${label.toUpperCase()}_DECLARATION_INVALID`);
  return matches[0][1];
}

function step(order, owner, action, readOnly, requiresExplicitAcknowledgement) {
  return {
    order,
    owner,
    action,
    status: "NOT_EXECUTED",
    read_only: readOnly,
    requires_explicit_acknowledgement: requiresExplicitAcknowledgement,
    executable_from_planner: false,
  };
}

function canonicalJson(value) { return JSON.stringify(canonicalize(value)); }
function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([key, nested]) => [key, canonicalize(nested)]));
  }
  if (value === null || typeof value === "string" || typeof value === "boolean" || (typeof value === "number" && Number.isFinite(value))) return value;
  fail("M101_PLAN_CANONICAL_VALUE_INVALID");
}
function sha256(value) { return createHash("sha256").update(value, "utf8").digest("hex"); }
function fail(reason) { const error = new Error(reason); error.reason = reason; throw error; }
function isMainModule() {
  if (!process.argv[1]) return false;
  try { return realpathSync.native(process.argv[1]) === fileURLToPath(import.meta.url); } catch { return false; }
}

if (isMainModule()) {
  try {
    if (process.argv.length !== 3) fail("M101_PLAN_EXACTLY_ONE_HANDOFF_PATH_REQUIRED");
    process.stdout.write(`${canonicalJson(planM101BindingFromHandoff(process.argv[2]))}\n`);
  } catch (error) {
    const reason = error && typeof error === "object" && "reason" in error ? String(error.reason) : "M101_BINDING_PLAN_FAILED";
    process.stderr.write(`${reason}\n`);
    process.exitCode = 2;
  }
}
