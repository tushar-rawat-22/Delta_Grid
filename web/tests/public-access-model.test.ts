import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const nav = readFileSync(new URL("../components/public-site-nav.tsx", import.meta.url), "utf8");
const landing = readFileSync(new URL("../components/research-landing.tsx", import.meta.url), "utf8");
const researchPage = readFileSync(new URL("../app/research/page.tsx", import.meta.url), "utf8");

test("primary public observer surfaces do not funnel visitors into founder authentication", () => {
  for (const source of [nav, landing, researchPage]) {
    assert.doesNotMatch(source, /deltagrid-founder-gateway/i);
    assert.doesNotMatch(source, /Founder Log in/i);
    assert.doesNotMatch(source, /Founder access/i);
    assert.doesNotMatch(source, /log in for authenticated Founder Mode/i);
  }
});

test("public observer explains the restricted access model without creating authority", () => {
  assert.match(nav, /Access model/);
  assert.match(landing, /Invite-only, scoped, isolated, revocable/);
  assert.match(landing, /explicit founder approval plus fresh security\/legal\/authority review/);
  assert.match(researchPage, /Restricted workspaces are not publicly available/);
  assert.match(landing, /Public website state has authority effect NONE/);
});
