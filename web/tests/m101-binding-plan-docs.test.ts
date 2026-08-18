import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("M101 binding planner docs preserve the non-authority boundary", () => {
  const text = fs.readFileSync("docs/M101_BINDING_PLAN.md", "utf8");
  assert.match(text, /cannot execute any of those steps/u);
  assert.match(text, /no permit issue or consumption/u);
  assert.match(text, /no trial reservation/u);
  assert.match(text, /no Mission 104 authority/u);
  assert.match(text, /no trading authority/u);
  assert.match(text, /no capital authority/u);
});
