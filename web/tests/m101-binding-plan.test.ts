import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  canonicalJson,
  compilePreregistrationReview,
  PREREGISTRATION_HEADINGS,
} from "../research-app/src/preregistration-model.ts";
import { compilePreregistrationHandoffManifest } from "../research-app/src/preregistration-handoff-model.ts";
// @ts-expect-error -- trusted-local Node tool is intentionally unbundled.
import { planM101BindingFromHandoff } from "../scripts/plan-m101-binding.mjs";

function body({ instrument = "SOLUSDT", benchmark = "BTCUSDT", provider = "Binance public spot OHLCV" } = {}): string {
  const sections = new Map<string, string>();
  for (const [index, heading] of PREREGISTRATION_HEADINGS.entries()) sections.set(heading, `Founder declaration ${index + 1}.`);
  sections.set("DATA AND CHRONOLOGY", `The intended result-bearing market inputs are ${instrument} and ${benchmark} settled one-hour ${provider} records from the exact REAL_MARKET_DEVELOPMENT dataset later bound by the Mission 101 dataset descriptor.`);
  sections.set("CANDIDATE AND PARAMETER BUDGET", `This is one preregistered research family containing exactly one candidate.\n\nInstrument: ${instrument}.\nBenchmark: ${benchmark}.\nForward horizon: exactly 24 hours.`);
  return PREREGISTRATION_HEADINGS.map((heading) => `${heading}\n${sections.get(heading)}`).join("\n\n");
}

async function handoffFile(overrides = {}): Promise<string> {
  const review = await compilePreregistrationReview({ record_id: "55555555-5555-4555-8555-555555555555", revision: 2, title: "SOL: investigate seven day drawdown", body: body(overrides) });
  const manifest = await compilePreregistrationHandoffManifest(review);
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "deltagrid-m101-plan-"));
  const target = path.join(root, `${manifest.handoff_id}.json`);
  fs.writeFileSync(target, `${manifest.canonical_handoff_json}\n`, { encoding: "utf8", mode: 0o600 });
  return target;
}

test("M101 binding planner compiles deterministic SOL/BTC Binance intent and exact authority dependencies", async () => {
  const target = await handoffFile();
  const left = planM101BindingFromHandoff(target);
  const right = planM101BindingFromHandoff(target);

  assert.equal(canonicalJson(left), canonicalJson(right));
  assert.equal(left.schema_version, "DELTAGRID_M101_HANDOFF_BINDING_PLAN_V1");
  assert.equal(left.status, "READY_FOR_TRUSTED_LOCAL_FACT_RESOLUTION");
  assert.deepEqual(left.declared_development_intent, {
    provider: "BINANCE_PUBLIC",
    symbols: ["BTCUSDT", "SOLUSDT"],
    primary_instrument: "SOLUSDT",
    benchmark: "BTCUSDT",
    streams: ["spot_ohlcv"],
    stream_intervals: { spot_ohlcv: "1h" },
    data_class: "REAL_MARKET_DEVELOPMENT",
    split_identity: "REAL_MARKET_DEVELOPMENT",
  });
  assert.equal(left.source_handoff.revision, 2);
  assert.match(left.plan_id, /^m101-binding-plan-[0-9a-f]{64}$/u);
  assert.match(left.plan_hash_sha256, /^[0-9a-f]{64}$/u);
  assert.equal(left.resolution_sequence.length, 10);
  assert.deepEqual(left.resolution_sequence.map((step: { action: string }) => step.action), [
    "CERTIFY_EXISTING_FORWARD_RELEASE",
    "CREATE_EXACT_DEVELOPMENT_DATASET_DESCRIPTOR",
    "INSPECT_PRIVATE_AUTHORITY_RUNTIME",
    "INITIALIZE_PRIVATE_AUTHORITY_RUNTIME_IF_ABSENT",
    "VERIFY_STABLE_REGISTRY_FAMILY_AND_VARIANT_IDENTITY",
    "ISSUE_FINITE_DEVELOPMENT_PERMIT",
    "REGISTER_FINITE_DEVELOPMENT_BUDGET",
    "ADMIT_ONE_METADATA_ONLY_DEVELOPMENT_TRIAL",
    "PREPARE_AND_FREEZE_PRE_RESULT_PROGRAM_BINDINGS",
    "FOUNDER_ACTIVATE_EXACT_FROZEN_PROGRAM_BEFORE_RESULTS",
  ]);
  assert.equal(left.resolution_sequence[2].read_only, true);
  assert.equal(left.resolution_sequence[3].requires_explicit_acknowledgement, true);
  assert.ok(left.resolution_sequence.every((step: { status: string; executable_from_planner: boolean }) => step.status === "NOT_EXECUTED" && step.executable_from_planner === false));
  assert.equal(left.stop_boundary, "PLAN_STOPS_BEFORE_RESULT_BEARING_M102_EXECUTION");
  assert.ok(left.dependency_invariants.includes("M102_STABLE_FAMILY_IDENTITY_PRECEDES_M101_PERMIT_ISSUANCE"));
  assert.ok(left.dependency_invariants.includes("M103_PRE_RESULT_PROGRAM_BINDS_EXACT_M94_M101_AND_STABLE_M102_IDENTITIES"));
  assert.equal(left.execution_boundary.authority_effect, "NONE");
  assert.equal(left.execution_boundary.commands_executed, false);
  assert.equal(left.execution_boundary.writes_performed, false);
  assert.equal(left.execution_boundary.permit_issued, false);
  assert.equal(left.execution_boundary.permit_consumed, false);
  assert.equal(left.execution_boundary.trial_reserved, false);
  assert.equal(left.execution_boundary.m103_program_frozen, false);
  assert.equal(left.execution_boundary.m103_program_activated, false);
  assert.equal(left.execution_boundary.result_execution_authorized, false);
});

test("M101 binding planner fails closed on unsupported provider or symbol declarations", async () => {
  const badProvider = await handoffFile({ provider: "Coinbase spot OHLCV" });
  assert.throws(() => planM101BindingFromHandoff(badProvider), /M101_PLAN_PROVIDER_DECLARATION_UNSUPPORTED/u);
  const badSymbol = await handoffFile({ instrument: "DOGEUSDT" });
  assert.throws(() => planM101BindingFromHandoff(badSymbol), /M101_PLAN_SYMBOL_UNSUPPORTED/u);
});

test("M101 binding planner refuses self-benchmarking declarations", async () => {
  const same = await handoffFile({ instrument: "SOLUSDT", benchmark: "SOLUSDT" });
  assert.throws(() => planM101BindingFromHandoff(same), /M101_PLAN_DISTINCT_SYMBOLS_REQUIRED/u);
});

test("M101 binding planner source has no execution, network, database, or write capability", () => {
  const source = fs.readFileSync("scripts/plan-m101-binding.mjs", "utf8");
  for (const forbidden of ["writeFileSync", "appendFile", "createWriteStream", "fetch(", "node:http", "node:https", "child_process", "execSync", "spawnSync", "sqlite", "wrangler", "issue-development-permit", "admit-development", "create-development-dataset"]) assert.equal(source.includes(forbidden), false, forbidden);
  assert.match(source, /READ_ONLY_PREPARATION_ONLY/u);
  assert.match(source, /executable_from_planner: false/u);
  assert.match(source, /writes_performed: false/u);
  assert.match(source, /authority_effect: "NONE"/u);
});

test("package and documentation expose one bounded trusted-local planner surface", () => {
  const pkg = JSON.parse(fs.readFileSync("package.json", "utf8"));
  assert.equal(pkg.scripts["plan:m101-binding"], "node scripts/plan-m101-binding.mjs");
  const docs = fs.readFileSync("docs/M101_BINDING_PLAN.md", "utf8");
  assert.match(docs, /planner cannot execute/u);
  assert.match(docs, /before result-bearing Mission 102 execution/u);
});
