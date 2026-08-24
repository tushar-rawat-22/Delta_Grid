import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const main = readFileSync(
  new URL("../research-app/src/main.tsx", import.meta.url),
  "utf8",
);
const app = readFileSync(
  new URL("../research-app/src/research-app.tsx", import.meta.url),
  "utf8",
);
const executive = readFileSync(
  new URL("../research-app/src/executive-workspace.css", import.meta.url),
  "utf8",
);

test("executive workspace presentation loads after functional workspace styles", () => {
  const base = main.indexOf('import "./styles.css"');
  const prereg = main.indexOf('import "./preregistration-workbench.css"');
  const resilience = main.indexOf('import "./research-write-resilience.css"');
  const executiveLayer = main.indexOf('import "./executive-workspace.css"');

  assert.ok(base >= 0);
  assert.ok(prereg > base);
  assert.ok(resilience > prereg);
  assert.ok(executiveLayer > resilience);
  assert.match(main, /installResearchWriteResilience\(\)/);
  assert.match(main, /<PreregistrationWorkbench \/>/);
  assert.match(main, /<ResearchWriteFeedback \/>/);
});

test("research workspace keeps its non-authorizing boundary", () => {
  assert.match(app, /boundary: "NON_RAB1_RESEARCH_ONLY"/);
  assert.match(app, /authority_effect: "NONE"/);
  assert.match(app, /NON_RAB1 · AUTHORITY NONE/);
  assert.doesNotMatch(executive, /exchange[_ -]?access[_ -]?allowed\s*:\s*true/i);
  assert.doesNotMatch(executive, /capital[_ -]?deployment[_ -]?allowed\s*:\s*true/i);
  assert.doesNotMatch(executive, /live[_ -]?trading[_ -]?allowed\s*:\s*true/i);
});

test("executive treatment reduces decorative chrome without hiding operational state", () => {
  assert.match(executive, /\.research-nav button span\s*\{\s*display:\s*none;/s);
  assert.match(executive, /\.metric-card\s*\{[^}]*border-radius:\s*0;/s);
  assert.match(executive, /\.panel,[\s\S]*?border-radius:\s*0;/);
  assert.match(executive, /\.prereg-launcher\s*\{[^}]*box-shadow:\s*none;/s);
  assert.match(executive, /font-variant-numeric:\s*tabular-nums/);
  assert.match(executive, /\.health\.good/);
  assert.match(executive, /\.health\.failed/);
  assert.doesNotMatch(executive, /linear-gradient|radial-gradient/);
});
