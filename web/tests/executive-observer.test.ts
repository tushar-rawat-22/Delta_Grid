import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const landing = readFileSync(new URL("../components/research-landing.tsx", import.meta.url), "utf8");
const shell = readFileSync(new URL("../app/public-shell.css", import.meta.url), "utf8");
const roadmap = JSON.parse(
  readFileSync(new URL("../../docs/DELIVERY_ROADMAP.json", import.meta.url), "utf8"),
) as {
  delivery_mode: string;
  software_complete_target: string;
  fixed_rules: string[];
  lanes: Array<{ id: string; state: string; options?: string[]; selection_rule: string }>;
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
  assert.doesNotMatch(shell, /border-radius:/i);
});

test("delivery roadmap remains re-plannable without weakening fixed safety rules", () => {
  assert.equal(roadmap.delivery_mode, "CONVERGENCE");
  assert.equal(roadmap.software_complete_target, "2026-09-07");
  assert.ok(roadmap.fixed_rules.some((rule) => rule.includes("security") && rule.includes("block")));
  assert.ok(roadmap.fixed_rules.some((rule) => rule.includes("last green main")));
  assert.ok(roadmap.replan_triggers.length >= 3);

  const uiLane = roadmap.lanes.find((lane) => lane.id === "executive-observer-ui");
  assert.ok(uiLane);
  assert.equal(uiLane.state, "ACTIVE");
  assert.ok((uiLane.options?.length ?? 0) >= 2);
  assert.match(uiLane.selection_rule, /least decorative/i);
});
