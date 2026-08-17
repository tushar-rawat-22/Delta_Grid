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
import {
  compilePreregistrationHandoffManifest,
  PREREGISTRATION_HANDOFF_SCHEMA,
} from "../research-app/src/preregistration-handoff-model.ts";
import { inspectPreregistrationHandoffFile } from "../scripts/inspect-preregistration-handoff.mjs";

function completeBody(): string {
  return PREREGISTRATION_HEADINGS.map(
    (heading, index) => `${heading}\nFounder declaration ${index + 1}.`,
  ).join("\n\n");
}

async function fixture() {
  const review = await compilePreregistrationReview({
    record_id: "99999999-9999-4999-8999-999999999999",
    revision: 4,
    title: "Trusted local intake fixture",
    body: completeBody(),
  });
  return compilePreregistrationHandoffManifest(review);
}

function temporaryFile(name: string, content: string): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "deltagrid-handoff-"));
  const target = path.join(root, name);
  fs.writeFileSync(target, content, { encoding: "utf8", mode: 0o600 });
  return target;
}

test("V2 handoff carries the canonical scientific review for independent local rehash", async () => {
  const manifest = await fixture();
  assert.equal(manifest.schema_version, PREREGISTRATION_HANDOFF_SCHEMA);
  assert.equal(manifest.schema_version, "DELTAGRID_FOUNDER_PREREGISTRATION_HANDOFF_V2");
  assert.ok(manifest.source_review.canonical_review_json.length > 0);
  assert.equal(
    canonicalJson(JSON.parse(manifest.source_review.canonical_review_json)),
    manifest.source_review.canonical_review_json,
  );
});

test("trusted-local intake rehashes both handoff and embedded review without authority", async () => {
  const manifest = await fixture();
  const target = temporaryFile(`${manifest.handoff_id}.json`, `${manifest.canonical_handoff_json}\n`);
  const inspected = inspectPreregistrationHandoffFile(target);

  assert.equal(inspected.inspection_status, "VERIFIED_AUTHORITY_ZERO_HANDOFF");
  assert.equal(inspected.handoff_id, manifest.handoff_id);
  assert.equal(inspected.handoff_hash_sha256, manifest.canonical_handoff_hash_sha256);
  assert.equal(inspected.source_review_hash_sha256, manifest.source_review.review_hash_sha256);
  assert.equal(inspected.source_review_id, manifest.source_review.review_id);
  assert.equal(inspected.authority_effect, "NONE");
  assert.equal(inspected.writes_performed, false);
  assert.equal(inspected.permit_issued, false);
  assert.equal(inspected.permit_consumed, false);
  assert.equal(inspected.trial_reserved, false);
  assert.equal(inspected.execution_authorized, false);
  assert.equal(inspected.protected_evidence_opened, false);
  assert.equal(inspected.resolution_plan.length, 5);
  assert.ok(
    inspected.resolution_plan.every(
      (step: { status: string; mode: string; canonical_write_authorized: boolean }) =>
        step.status === "UNRESOLVED" &&
        step.mode === "READ_ONLY_PREPARATION_ONLY" &&
        step.canonical_write_authorized === false,
    ),
  );
});

test("trusted-local intake rejects an altered embedded review even when outer JSON is recanonicalized", async () => {
  const manifest = await fixture();
  const outer = JSON.parse(manifest.canonical_handoff_json);
  const review = JSON.parse(outer.source_review.canonical_review_json);
  review.source_title = "Tampered title";
  outer.source_review.canonical_review_json = canonicalJson(review);
  const target = temporaryFile("tampered-handoff.json", `${canonicalJson(outer)}\n`);

  assert.throws(
    () => inspectPreregistrationHandoffFile(target),
    /HANDOFF_REVIEW_HASH_MISMATCH/u,
  );
});

test("trusted-local intake rejects legacy V1 handoffs rather than guessing missing custody evidence", async () => {
  const manifest = await fixture();
  const outer = JSON.parse(manifest.canonical_handoff_json);
  outer.schema_version = "DELTAGRID_FOUNDER_PREREGISTRATION_HANDOFF_V1";
  delete outer.source_review.canonical_review_json;
  const target = temporaryFile("legacy-handoff.json", `${canonicalJson(outer)}\n`);

  assert.throws(
    () => inspectPreregistrationHandoffFile(target),
    /HANDOFF_SCHEMA_UNSUPPORTED|HANDOFF_SOURCE_REVIEW_SHAPE_INVALID/u,
  );
});

test("trusted-local intake source contains no network, database, process or write capability", () => {
  const source = fs.readFileSync("scripts/inspect-preregistration-handoff.mjs", "utf8");
  for (const forbidden of [
    "writeFileSync",
    "appendFile",
    "createWriteStream",
    "fetch(",
    "node:http",
    "node:https",
    "child_process",
    "execSync",
    "spawnSync",
    "sqlite",
    "wrangler",
    "issue-development-permit",
    "admit-development",
    "run-development",
  ]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
  assert.match(source, /READ_ONLY_PREPARATION_ONLY/u);
  assert.match(source, /canonical_write_authorized: false/u);
});
