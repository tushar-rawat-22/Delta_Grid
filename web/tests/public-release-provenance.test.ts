import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { derivePublicReleaseProvenance } from "../lib/public-release-provenance.ts";

const headers = readFileSync(new URL("../public/_headers", import.meta.url), "utf8");
const observerPage = readFileSync(new URL("../components/observer-page.tsx", import.meta.url), "utf8");

test("valid public release marker produces verified-live provenance", () => {
  const sha = "a".repeat(40);
  const provenance = derivePublicReleaseProvenance({ release_sha: sha });
  assert.equal(provenance.status, "VERIFIED LIVE");
  assert.equal(provenance.releaseSha, sha);
  assert.match(provenance.detail, /live observer identity only/i);
});

test("release provenance fails closed for malformed or expanded public markers", () => {
  for (const value of [
    null,
    {},
    { release_sha: "abc" },
    { release_sha: "A".repeat(40) },
    { release_sha: "a".repeat(40), private_state: "must-not-be-consumed" },
  ]) {
    const provenance = derivePublicReleaseProvenance(value);
    assert.equal(provenance.status, "UNVERIFIED");
    assert.equal(provenance.releaseSha, null);
  }
});

test("observer boundary derives release provenance instead of hard-coding deployment success", () => {
  assert.match(observerPage, /ReleaseProvenanceCard/);
  assert.doesNotMatch(observerPage, /label:\s*"Release provenance"[\s\S]*?value:\s*"(?:VERIFIED|UNVERIFIED)/);
});

test("public static assets set conservative host-only HSTS without preload scope expansion", () => {
  assert.match(headers, /Strict-Transport-Security:\s*max-age=31536000/);
  assert.doesNotMatch(headers, /Strict-Transport-Security:[^\n]*(?:includeSubDomains|preload)/i);
});
