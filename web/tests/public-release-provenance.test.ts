import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { bindPublicReleaseProvenance } from "../scripts/bind-public-release-provenance.mjs";

const headers = readFileSync(new URL("../public/_headers", import.meta.url), "utf8");
const observerPage = readFileSync(new URL("../components/observer-page.tsx", import.meta.url), "utf8");
const routes = ["", "markets", "research", "evidence", "missions", "system", "risk", "docs", "about"];
const unverifiedDetail =
  "This build has not been bound to a verified live release. Production deployment must prove the exact deployed revision before this status changes.";

function unverifiedHtml() {
  return `<article data-release-provenance="UNVERIFIED"><span data-release-provenance-status="UNVERIFIED">UNVERIFIED</span><p data-release-provenance-detail="UNVERIFIED">${unverifiedDetail}</p></article>`;
}

test("guarded release binding upgrades all public routes and emits the exact public marker", () => {
  const root = mkdtempSync(path.join(tmpdir(), "deltagrid-release-"));
  try {
    for (const route of routes) {
      const file = route === "" ? path.join(root, "index.html") : path.join(root, route, "index.html");
      mkdirSync(path.dirname(file), { recursive: true });
      writeFileSync(file, unverifiedHtml());
    }

    const sha = "a".repeat(40);
    const result = bindPublicReleaseProvenance(root, sha);
    assert.equal(result.boundRoutes, 9);
    assert.equal(result.releaseSha, sha);

    for (const route of routes) {
      const file = route === "" ? path.join(root, "index.html") : path.join(root, route, "index.html");
      const html = readFileSync(file, "utf8");
      assert.match(html, /data-release-provenance="VERIFIED LIVE"/);
      assert.match(html, />VERIFIED LIVE<\/span>/);
      assert.match(html, /Verified live release aaaaaaaaaaaa/);
      assert.doesNotMatch(html, /data-release-provenance="UNVERIFIED"/);
    }
    assert.equal(
      readFileSync(path.join(root, "deltagrid-release.json"), "utf8"),
      `${JSON.stringify({ release_sha: sha })}\n`,
    );
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("release binding rejects invalid identity and non-canonical binding points", () => {
  const root = mkdtempSync(path.join(tmpdir(), "deltagrid-release-invalid-"));
  try {
    assert.throws(() => bindPublicReleaseProvenance(root, "abc"), /PUBLIC_RELEASE_SHA_INVALID/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("observer source stays fail closed and contains no runtime network surface", () => {
  assert.match(observerPage, /data-release-provenance="UNVERIFIED"/);
  assert.match(observerPage, /data-release-provenance-status="UNVERIFIED">UNVERIFIED/);
  assert.doesNotMatch(observerPage, /\bfetch\s*\(/);
  assert.doesNotMatch(observerPage, /VERIFIED LIVE/);
});

test("public static assets set conservative host-only HSTS without preload scope expansion", () => {
  assert.match(headers, /Strict-Transport-Security:\s*max-age=31536000/);
  assert.doesNotMatch(headers, /Strict-Transport-Security:[^\n]*(?:includeSubDomains|preload)/i);
});
