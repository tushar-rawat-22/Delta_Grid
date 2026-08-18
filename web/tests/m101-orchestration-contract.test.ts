import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const planner = fs.readFileSync("scripts/plan-m101-binding.mjs", "utf8");
const m101Cli = fs.readFileSync("../offchain/research/reopening/__main__.py", "utf8");
const m101Authority = fs.readFileSync("../offchain/research/reopening/authority.py", "utf8");
const m101Dataset = fs.readFileSync("../offchain/research/reopening/dataset.py", "utf8");
const m101Admission = fs.readFileSync("../offchain/research/reopening/admission.py", "utf8");
const m102Cli = fs.readFileSync("../offchain/research/development_runtime/__main__.py", "utf8");

const readOnlyBindings = [
  ["VERIFY_M101_CONTRACT_AND_CLOSED_RESULT_AUTHORITY", m101Cli, 'commands.add_parser("show-contract"'],
  ["CERTIFY_EXISTING_FORWARD_RELEASE", m101Cli, 'commands.add_parser("certify-forward-custody-release"'],
  ["VERIFY_STABLE_REGISTRY_FAMILY_AND_VARIANT_IDENTITY", m102Cli, 'sub.add_parser("inspect-experiment-registry")'],
  ["INSPECT_PRIVATE_AUTHORITY_RUNTIME", m101Cli, 'commands.add_parser("inspect-authority-runtime"'],
] as const;

const writeBindings = [
  ["CREATE_EXACT_DEVELOPMENT_DATASET_DESCRIPTOR", m101Cli, 'commands.add_parser("create-development-dataset"', m101Dataset, 'ACK_WRITE_DESCRIPTOR = "WRITE_M101_DEVELOPMENT_DATASET_DESCRIPTOR"'],
  ["INITIALIZE_PRIVATE_AUTHORITY_RUNTIME_IF_ABSENT", m101Cli, 'commands.add_parser("init-research-authority-runtime"', m101Authority, 'ACK_INITIALIZE_AUTHORITY = "INITIALIZE_M101_RESEARCH_AUTHORITY_RUNTIME"'],
  ["ISSUE_FINITE_DEVELOPMENT_PERMIT", m101Cli, 'commands.add_parser("issue-development-permit"', m101Authority, 'ACK_ISSUE_PERMIT = "ISSUE_M101_DEVELOPMENT_PERMIT"'],
  ["REGISTER_FINITE_DEVELOPMENT_BUDGET", m101Cli, 'commands.add_parser("register-development-budget"', m101Admission, 'ACK_REGISTER_BUDGET = "REGISTER_M101_DEVELOPMENT_TRIAL_BUDGET"'],
  ["ADMIT_ONE_METADATA_ONLY_DEVELOPMENT_TRIAL", m101Cli, 'commands.add_parser("admit-development"', m101Admission, 'ACK_ADMIT_DEVELOPMENT = "RESERVE_M101_DEVELOPMENT_ADMISSION_TRIAL"'],
] as const;

test("M101 binding planner read-only phase is backed by canonical Mission 101/102 operator surfaces", () => {
  for (const [plannerAction, operatorSource, operatorMarker] of readOnlyBindings) {
    assert.ok(planner.includes(`"${plannerAction}"`), `planner action missing: ${plannerAction}`);
    assert.ok(operatorSource.includes(operatorMarker), `canonical read-only operator missing for ${plannerAction}`);
  }

  const firstWrite = planner.indexOf('"CREATE_EXACT_DEVELOPMENT_DATASET_DESCRIPTOR"');
  assert.ok(firstWrite > 0);
  for (const [plannerAction] of readOnlyBindings) {
    assert.ok(planner.indexOf(`"${plannerAction}"`) < firstWrite, `${plannerAction} must precede the first planned write`);
  }
});

test("M101 binding planner mutation phase remains tied to explicit canonical acknowledgement contracts", () => {
  for (const [plannerAction, cliSource, cliMarker, acknowledgementSource, acknowledgementMarker] of writeBindings) {
    assert.ok(planner.includes(`"${plannerAction}"`), `planner action missing: ${plannerAction}`);
    assert.ok(cliSource.includes(cliMarker), `canonical mutation operator missing for ${plannerAction}`);
    assert.ok(acknowledgementSource.includes(acknowledgementMarker), `canonical acknowledgement changed for ${plannerAction}`);
  }
});

test("cross-language orchestration verifier preserves the result-bearing execution stop", () => {
  assert.ok(planner.includes('stop_boundary: "PLAN_STOPS_BEFORE_RESULT_BEARING_M102_EXECUTION"'));
  assert.ok(m102Cli.includes('sub.add_parser("execute-development-trial")'));
  assert.equal(planner.includes('"EXECUTE_DEVELOPMENT_TRIAL"'), false);
  assert.equal(planner.includes('execute-development-trial'), false);
});
