import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const headers = readFileSync(new URL("../public/_headers", import.meta.url), "utf8");
const observerPage = readFileSync(new URL("../components/observer-page.tsx", import.meta.url), "utf8");
const releaseProvenance = readFileSync(new URL("../lib/public-release-provenance.ts", import.meta.url), "utf8");
const browserAcceptance = readFileSync(new URL("../scripts/verify-browser-acceptance.mjs", import.meta.url), "utf8");
const researchLanding = readFileSync(new URL("../components/research-landing.tsx", import.meta.url), "utf8");
const publicResearchDemo = readFileSync(new URL("../components/public-research-demo.tsx", import.meta.url), "utf8");
const binder = fileURLToPath(new URL("../scripts/bind-public-release-provenance.mjs", import.meta.url));
const provenanceRoutes = ["markets", "evidence", "missions", "system", "risk", "docs", "about"];
const markerFreeRoutes = ["", "research"];
function verifiedHtml(sha: string) {
  const card = `<article data-release-provenance="VERIFIED LIVE" data-release-sha="${sha}"><span data-release-provenance-status="VERIFIED LIVE">VERIFIED LIVE</span><p data-release-provenance-detail="VERIFIED LIVE">Verified live release ${sha.slice(0, 12)}. The public release pipeline proved this exact deployed revision and rechecked the public/private boundary. This does not grant research, trading or capital authority.</p></article>`;
  return `${card}<template data-next-static-payload>${card}</template>`;
}

test("guarded release binding verifies a consistently rendered release build without rewriting route payloads", () => {
  const workspace = mkdtempSync(path.join(tmpdir(), "deltagrid-release-"));
  const root = path.join(workspace, "out");
  try {
    mkdirSync(root, { recursive: true });
    const markerFreeHtml = new Map([
      ["", "<main data-public-research-landing>Research control</main>"],
      ["research", "<main data-public-research-demo>Public demo</main>"],
    ]);
    for (const route of markerFreeRoutes) {
      const file = route === "" ? path.join(root, "index.html") : path.join(root, route, "index.html");
      mkdirSync(path.dirname(file), { recursive: true });
      writeFileSync(file, markerFreeHtml.get(route) ?? "");
    }
    const sha = "a".repeat(40);
    for (const route of provenanceRoutes) {
      const file = path.join(root, route, "index.html");
      mkdirSync(path.dirname(file), { recursive: true });
      writeFileSync(file, verifiedHtml(sha));
    }

    const stdout = execFileSync(process.execPath, [binder, sha], { cwd: workspace, encoding: "utf8" });
    assert.match(stdout, /PUBLIC_RELEASE_PROVENANCE_VERIFIED=7/);
    assert.match(stdout, new RegExp(`PUBLIC_RELEASE_SHA=${sha}`));

    for (const route of markerFreeRoutes) {
      const file = route === "" ? path.join(root, "index.html") : path.join(root, route, "index.html");
      assert.equal(readFileSync(file, "utf8"), markerFreeHtml.get(route));
    }
    for (const route of provenanceRoutes) {
      const file = path.join(root, route, "index.html");
      const html = readFileSync(file, "utf8");
      assert.equal(html, verifiedHtml(sha));
      assert.equal(html.match(/data-release-provenance="VERIFIED LIVE"/g)?.length, 2);
      assert.match(html, />VERIFIED LIVE<\/span>/);
      assert.match(html, /Verified live release aaaaaaaaaaaa/);
      assert.match(html, new RegExp(`data-release-sha="${sha}"`));
      assert.doesNotMatch(html, /data-release-provenance(?:-status|-detail)?="UNVERIFIED"/);
    }
    assert.equal(
      readFileSync(path.join(root, "deltagrid-release.json"), "utf8"),
      `${JSON.stringify({ release_sha: sha })}\n`,
    );
  } finally {
    rmSync(workspace, { recursive: true, force: true });
  }
});

test("release binding refuses an unverified hydration payload instead of patching exported HTML", () => {
  const workspace = mkdtempSync(path.join(tmpdir(), "deltagrid-release-stale-"));
  const root = path.join(workspace, "out");
  try {
    for (const route of provenanceRoutes) {
      const file = path.join(root, route, "index.html");
      mkdirSync(path.dirname(file), { recursive: true });
      writeFileSync(file, '<article data-release-provenance="UNVERIFIED"></article>');
    }
    assert.throws(
      () => execFileSync(process.execPath, [binder, "b".repeat(40)], { cwd: workspace, stdio: "pipe" }),
      /Command failed/,
    );
    assert.equal(
      readFileSync(path.join(root, "evidence", "index.html"), "utf8"),
      '<article data-release-provenance="UNVERIFIED"></article>',
    );
  } finally {
    rmSync(workspace, { recursive: true, force: true });
  }
});

test("release binding rejects invalid identity", () => {
  const workspace = mkdtempSync(path.join(tmpdir(), "deltagrid-release-invalid-"));
  try {
    assert.throws(
      () => execFileSync(process.execPath, [binder, "abc"], { cwd: workspace, stdio: "pipe" }),
      /Command failed/,
    );
  } finally {
    rmSync(workspace, { recursive: true, force: true });
  }
});

test("observer source stays fail closed and contains no runtime network surface", () => {
  assert.match(observerPage, /publicReleaseProvenance\(\)/);
  assert.match(observerPage, /data-release-provenance=\{releaseProvenance\.status\}/);
  assert.match(observerPage, /data-release-sha=\{releaseProvenance\.releaseSha \?\? undefined\}/);
  assert.doesNotMatch(observerPage, /\bfetch\s*\(/);
  assert.doesNotMatch(observerPage, /suppressHydrationWarning/);
  assert.match(releaseProvenance, /status: "UNVERIFIED"/);
  assert.match(releaseProvenance, /process\.env\.DELTAGRID_PUBLIC_RELEASE_SHA/);
  assert.match(releaseProvenance, /PUBLIC_RELEASE_SHA_INVALID/);
  assert.doesNotMatch(releaseProvenance, /\bfetch\s*\(/);
});

test("browser acceptance proves exact release identity and rejects post-hydration fallback", () => {
  assert.match(browserAcceptance, /data-release-sha/);
  assert.match(browserAcceptance, /release provenance fell back after hydration/);
  assert.match(browserAcceptance, /hydration warnings/);
  assert.match(browserAcceptance, /deltagrid-release\.json\?hydrated_browser=/);
  assert.match(browserAcceptance, /sample < 5/);
});

test("landing and interactive research demo are intentionally marker-free; site-wide identity is the release JSON", () => {
  for (const source of [researchLanding, publicResearchDemo]) {
    assert.doesNotMatch(source, /data-release-provenance/);
    assert.doesNotMatch(source, /VERIFIED LIVE/);
  }
});

test("public static assets set conservative host-only HSTS without preload scope expansion", () => {
  assert.match(headers, /Strict-Transport-Security:\s*max-age=31536000/);
  assert.doesNotMatch(headers, /Strict-Transport-Security:[^\n]*(?:includeSubDomains|preload)/i);
});
