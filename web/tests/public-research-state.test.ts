import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const landingSource = fs.readFileSync("components/research-landing.tsx", "utf8");

test("public authority table describes Mission 104 as observation, not capital authority", () => {
  assert.match(
    landingSource,
    /\["Mission 104", "Candidate observation", "NOT AUTHORIZED"\]/u,
  );
  assert.doesNotMatch(
    landingSource,
    /\["Mission 104", "Capital authority",/u,
  );
});
