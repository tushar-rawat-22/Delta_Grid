import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  DEMO_NAV,
  PUBLIC_DEMO_IDENTITY,
  assertPublicDemoInvariants,
  demoHealth,
  demoHypotheses,
  demoMarketSeries,
} from "../lib/public-demo-data.ts";

test("public research demo is deterministic, sanitized and non-authorizing", () => {
  assert.doesNotThrow(() => assertPublicDemoInvariants());
  assert.equal(PUBLIC_DEMO_IDENTITY.mode, "DEMO_MODE");
  assert.equal(PUBLIC_DEMO_IDENTITY.provenance, "DEMO_FIXTURE");
  assert.equal(PUBLIC_DEMO_IDENTITY.authority_effect, "NONE");
  assert.equal(DEMO_NAV.length, 8);
  assert.deepEqual(
    DEMO_NAV.map((item) => item.label),
    ["Cockpit", "Intelligence", "Hypotheses", "Markets", "Compare", "Macro", "Notebook", "Data health"],
  );
});

test("public demo fixtures contain no live-market or founder authority claim", () => {
  assert.ok(demoMarketSeries.length >= 7);
  assert.ok(demoHypotheses.every((item) => item.id.startsWith("DEMO-HYP-")));
  assert.ok(demoHealth.every((item) => item.rights === "DEMO_ONLY"));

  const fixtureText = JSON.stringify({ demoMarketSeries, demoHypotheses, demoHealth }).toLowerCase();
  for (const forbidden of ["live price", "validated profitable", "selected candidate", "paper trading authorized", "live trading authorized"]) {
    assert.equal(fixtureText.includes(forbidden), false, forbidden);
  }
});

test("public demo component has no private network or write surface", () => {
  const source = fs.readFileSync("components/public-research-demo.tsx", "utf8");
  for (const forbidden of ["fetch(", "XMLHttpRequest", "WebSocket(", "/api/research/v1/", "csrf_token", "method: \"POST\"", "method: 'POST'"]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
  assert.match(source, /DEMO MODE/u);
  assert.match(source, /Log in for Founder Mode/u);
});
