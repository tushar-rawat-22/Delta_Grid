import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { alphaSearchBRecord } from "../lib/public-research-record.ts";

const landing = fs.readFileSync("components/research-landing.tsx", "utf8");
const landingCss = fs.readFileSync("components/research-landing.module.css", "utf8");
const observerPage = fs.readFileSync("components/observer-page.tsx", "utf8");
const evidenceRecord = fs.readFileSync("components/research-evidence-record.tsx", "utf8");
const evidenceCss = fs.readFileSync("components/research-evidence-record.module.css", "utf8");
const machineDecision = JSON.parse(
  fs.readFileSync("../docs/evidence/alpha_search_b_development/DEVELOPMENT_DECISION.json", "utf8"),
) as Record<string, unknown>;

test("research cockpit presents the preserved decision without expanding authority", () => {
  assert.equal(alphaSearchBRecord.decision, machineDecision.decision);
  assert.equal(alphaSearchBRecord.selectedCandidate, machineDecision.selected_candidate);
  assert.equal(alphaSearchBRecord.validationOpened, machineDecision.validation_performance_accessed);
  assert.equal(alphaSearchBRecord.holdoutOpened, machineDecision.holdout_performance_accessed);
  assert.equal(machineDecision.live_trading, false);
  assert.equal(machineDecision.capital_deployment, false);
  assert.equal(alphaSearchBRecord.authorityEffect, "NONE");
});

test("featured record exposes the complete lineage and one direct evidence action", () => {
  assert.equal(alphaSearchBRecord.lineage.length, 7);
  assert.equal(alphaSearchBRecord.sourceRecords.length, 17);
  assert.match(landing, /href="\/evidence#alpha-search-b"/u);
  assert.match(landing, /Current research status/u);
  assert.match(landing, /Inspect rejected experiment/u);
  assert.match(observerPage, /page === "evidence" \? <ResearchEvidenceRecord \/>/u);
  assert.match(evidenceRecord, /id=\{alphaSearchBRecord\.id\}/u);
});

test("every advertised source is a public file preserved at the publication commit", () => {
  for (const [, path] of alphaSearchBRecord.sourceRecords) {
    assert.ok(fs.existsSync(`../${path}`), path);
  }
  assert.match(alphaSearchBRecord.publicationCommit, /^[0-9a-f]{40}$/u);
});

test("cockpit keeps deliberate mobile, focus and reduced-motion states", () => {
  assert.match(landingCss, /@media \(max-width: 520px\)/u);
  assert.match(landingCss, /\.lineage \{ grid-template-columns: 1fr; \}/u);
  assert.match(landingCss, /\.recordAction:focus-visible/u);
  assert.match(landingCss, /@media \(prefers-reduced-motion: reduce\)/u);
  assert.match(evidenceCss, /@media \(max-width: 620px\)/u);
  assert.match(evidenceCss, /\.sources a:focus-visible/u);
  assert.match(evidenceCss, /@media \(prefers-reduced-motion: reduce\)/u);
});

test("public cockpit does not add analytics or a write-capable data path", () => {
  for (const source of [landing, observerPage, evidenceRecord]) {
    assert.doesNotMatch(source, /posthog|analytics|fetch\(|XMLHttpRequest|WebSocket|method:\s*["']POST["']/iu);
  }
});
