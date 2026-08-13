import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";
import { canonicalText } from "../lib/projection/canonical.ts";
import { PUBLIC_PROJECTION_CONTRACT_HASH } from "../lib/projection/constants.ts";
import { verifyProjectionPackage } from "../lib/projection/verify.ts";

const COMMIT = "546b9a589275d0a883c6934f244e17dd951755e5";

function makePackage() {
  const projection = {
    schema_id: "DELTAGRID_PUBLIC_PROJECTION_V1",
    source_classes: ["REPOSITORY_IDENTITY", "CONTRACT_DERIVED", "PUBLIC_DOCUMENT_IDENTITY"],
    core_identity: { repository_commit: COMMIT },
    authority: {
      maximum_verdict: "QUALIFIED_FOR_M104_OBSERVATION",
      maximum_verdict_authority_effect: "NONE",
      production_statistical_adapter_count: 0,
      production_protected_evaluator_count: 0,
      m104_observation: false,
      model_training_or_ml: false,
      paper_trading: false,
      live_trading: false,
      exchange_account_access: false,
      credential_access: false,
      signed_exchange_requests: false,
      order_placement: false,
      portfolio_allocation: false,
      capital_deployment: false,
      self_authorization: false,
    },
    contract_identities: [
      {
        path: "contracts/DELTAGRID_AUTONOMY_CONSTITUTION_V5.json",
        contract_id: "deltagrid-autonomy-constitution-v5",
        contract_hash_sha256: "7055bba73f10ebb78f8791511d0b926ef1d8d7dae9099b843fae81d9aa074767",
      },
      {
        path: "contracts/DELTAGRID_INDEPENDENT_RESEARCH_VALIDATION_GOVERNANCE_V1.json",
        contract_id: "deltagrid-independent-research-validation-governance-v1",
        contract_hash_sha256: "19cc7af157e6350a736a272dd73c16a407eb42e68368ad84f970896da60d10f4",
      },
    ],
    public_document_identities: [
      { path: "README.md", sha256: "1".repeat(64) },
      { path: "docs/RESEARCH_POLICY.md", sha256: "2".repeat(64) },
      { path: "docs/RISK_POLICY.md", sha256: "3".repeat(64) },
      { path: "docs/SAFETY_INVARIANTS.md", sha256: "4".repeat(64) },
    ],
  };
  const projectionRaw = canonicalText(projection);
  const projectionSha256 = createHash("sha256").update(projectionRaw, "utf8").digest("hex");
  const manifest = {
    manifest_schema: "DELTAGRID_PUBLIC_PROJECTION_MANIFEST_V1",
    public_projection_contract_hash: PUBLIC_PROJECTION_CONTRACT_HASH,
    repository_commit: COMMIT,
    projection_sha256: projectionSha256,
  };
  return { projection, projectionRaw, manifest, manifestRaw: canonicalText(manifest) };
}

test("accepts a canonical, non-authorizing P1 package", () => {
  const pkg = makePackage();
  const verified = verifyProjectionPackage(pkg.projectionRaw, pkg.manifestRaw, COMMIT);
  assert.equal(verified.manifest.repository_commit, COMMIT);
  assert.equal(verified.projection.authority.live_trading, false);
});

test("rejects projection tampering", () => {
  const pkg = makePackage();
  const tampered = pkg.projectionRaw.replace('"paper_trading":false', '"paper_trading":true');
  assert.throws(() => verifyProjectionPackage(tampered, pkg.manifestRaw), /PROJECTION_AUTHORITY_INVALID|PROJECTION_HASH_MISMATCH/u);
});

test("rejects unknown projection fields", () => {
  const pkg = makePackage();
  const changed = { ...pkg.projection, unexpected: "no" };
  assert.throws(() => verifyProjectionPackage(canonicalText(changed), pkg.manifestRaw), /PROJECTION_SCHEMA_INVALID/u);
});

test("rejects noncanonical JSON bytes", () => {
  const pkg = makePackage();
  const pretty = `${JSON.stringify(pkg.projection, null, 2)}\n`;
  assert.throws(() => verifyProjectionPackage(pretty, pkg.manifestRaw), /NONCANONICAL_JSON/u);
});

test("rejects manifest contract substitution", () => {
  const pkg = makePackage();
  const manifest = { ...pkg.manifest, public_projection_contract_hash: "0".repeat(64) };
  assert.throws(() => verifyProjectionPackage(pkg.projectionRaw, canonicalText(manifest)), /MANIFEST_CONTRACT_HASH_MISMATCH/u);
});

test("rejects commit substitution", () => {
  const pkg = makePackage();
  assert.throws(() => verifyProjectionPackage(pkg.projectionRaw, pkg.manifestRaw, "0".repeat(40)), /UNEXPECTED_REPOSITORY_COMMIT/u);
});
