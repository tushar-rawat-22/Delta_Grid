import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

type RoadmapLane = {
  id: string;
  state: string;
  blocker?: string;
  evidence?: string;
  current_focus?: string;
};

type DeliveryRoadmap = {
  lanes: RoadmapLane[];
};

const roadmap = JSON.parse(
  readFileSync(new URL("../../docs/DELIVERY_ROADMAP.json", import.meta.url), "utf8"),
) as DeliveryRoadmap;

function lane(id: string): RoadmapLane {
  const result = roadmap.lanes.find((candidate) => candidate.id === id);
  assert.ok(result, `missing delivery roadmap lane: ${id}`);
  return result;
}

test("delivery roadmap has one explicit active lane", () => {
  const active = roadmap.lanes.filter((candidate) => candidate.state === "ACTIVE");
  assert.deepEqual(active.map((candidate) => candidate.id), ["operator-release-candidate"]);
});

test("shipped deployment provenance cannot retain the retired credential blocker", () => {
  const provenance = lane("deployment-provenance");
  assert.equal(provenance.state, "SHIPPED");
  assert.equal(provenance.blocker, undefined);
  assert.match(provenance.evidence ?? "", /Public Observer Release #35/);
  assert.match(provenance.evidence ?? "", /6feb2323b3bced523bd052191281d6e391ccedc5/);

  const serialized = JSON.stringify(provenance);
  assert.equal(serialized.includes("CLOUDFLARE_API_TOKEN"), false);
  assert.equal(serialized.includes("BLOCKED_EXTERNAL"), false);
});

test("operator release-candidate focus treats verified deployment provenance as closed", () => {
  const candidate = lane("operator-release-candidate");
  assert.equal(candidate.state, "ACTIVE");
  assert.match(candidate.current_focus ?? "", /verified deployment provenance/i);
  assert.equal((candidate.current_focus ?? "").includes("external credentials"), false);
  assert.equal((candidate.current_focus ?? "").includes("CLOUDFLARE_API_TOKEN"), false);
});
