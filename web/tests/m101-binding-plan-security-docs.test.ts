import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("M101 binding planner security documentation states the fail-closed boundary", () => {
  const text = fs.readFileSync("docs/M101_BINDING_PLAN_SECURITY.md", "utf8");
  assert.match(text, /fails closed/u);
  assert.match(text, /has no network client/u);
  assert.match(text, /no .*database binding/u);
  assert.match(text, /no .*permit issuer/u);
  assert.match(text, /no .*admission path/u);
  assert.match(text, /no .*order path/u);
  assert.match(text, /no .*capital authority/u);
});
