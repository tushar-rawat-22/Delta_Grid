import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const landing = readFileSync(new URL("../components/research-landing.tsx", import.meta.url), "utf8");
const shell = readFileSync(new URL("../app/public-shell.css", import.meta.url), "utf8");
const roadmapSource = readFileSync(new URL("../../docs/DELIVERY_ROADMAP.json", import.meta.url), "utf8");
const roadmap = JSON.parse(roadmapSource) as {
  delivery_mode: string;
  software_complete_target: string;
  fixed_rules: string[];
  lanes: Array<{ id: string; state: string; options?: string[]; selection_rule?: string; evidence?: string }>;
  replan_triggers: Array<{ trigger: string; action: string }>;
};

test("public observer keeps the durable research and authority markers prominent", () => {
  for (const marker of [
    "No validated alpha",
    "None selected",
    "Disabled",
    "Blocked",
    "Candidate observation",
    "NOT AUTHORIZED",
    "authority effect NONE",
  ]) {
    assert.match(landing, new RegExp(marker.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
});

test("observer landing is a dense research console rather than a screenshot-led marketing page", () => {
  assert.doesNotMatch(landing, /next\/image/i);
  assert.doesNotMatch(landing, /snapshots?/i);
  assert.doesNotMatch(shell, /box-shadow:/i);
  assert.doesNotMatch(shell, /border-radius:\s*(?:\.5|\.55|\.58|\.6|\.65|\.7|\.72|\.8|1)rem/i);
});

test("delivery roadmap remains re-plannable without weakening fixed safety rules", () => {
  assert.equal(roadmap.delivery_mode, "CONVERGENCE");
  assert.equal(roadmap.software_complete_target, "2026-09-07");
  assert.ok(roadmap.fixed_rules.some((rule) => rule.includes("security") && rule.includes("block")));
  assert.ok(roadmap.fixed_rules.some((rule) => rule.includes("last green main")));
  assert.ok(roadmap.replan_triggers.length >= 3);

  const observerLane = roadmap.lanes.find((lane) => lane.id === "executive-observer-ui");
  assert.ok(observerLane);
  assert.equal(observerLane.state, "SHIPPED");
  assert.match(observerLane.evidence ?? "", /PR #89/);
  assert.ok((observerLane.options?.length ?? 0) >= 2);
  assert.match(observerLane.selection_rule ?? "", /least decorative/i);

  const workspaceLane = roadmap.lanes.find((lane) => lane.id === "executive-research-workspace");
  assert.ok(workspaceLane);
  assert.equal(workspaceLane.state, "ACTIVE");
  assert.ok((workspaceLane.options?.length ?? 0) >= 2);
  assert.match(workspaceLane.selection_rule ?? "", /reversible presentation-only option/i);
});

test("delivery roadmap cannot schedule paper or live execution under current authority", () => {
  assert.doesNotMatch(roadmapSource, /supported-paper-operator-flow/i);
  assert.doesNotMatch(roadmapSource, /durable paper operation/i);
  assert.doesNotMatch(roadmapSource, /run only authorized paper components/i);
  assert.ok(roadmap.fixed_rules.some((rule) => rule.includes("paper/live execution") && rule.includes("out of scope")));

  const readinessLane = roadmap.lanes.find((lane) => lane.id === "supported-readiness-operator-flow");
  assert.ok(readinessLane);
  assert.match(readinessLane.selection_rule ?? "", /do not invoke or rewrite paper\/live execution engines/i);
});
