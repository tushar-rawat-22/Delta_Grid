import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  issueResearchCsrf,
  verifyResearchCsrf,
  verifySameOrigin,
} from "../founder/research-security.ts";

const env = {
  DELTAGRID_RESEARCH_CSRF_KEY: "r".repeat(64),
};

const now = Date.UTC(2026, 7, 18, 6, 0, 0);
const nowSeconds = Math.floor(now / 1000);

function writeRequest(token: string, origin = "https://founder.example.test", fetchSite?: string): Request {
  const headers = new Headers({
    origin,
    "content-type": "application/json",
    "x-deltagrid-csrf": token,
  });
  if (fetchSite !== undefined) headers.set("sec-fetch-site", fetchSite);
  return new Request("https://founder.example.test/api/research/v1/records/example", {
    method: "PUT",
    headers,
    body: "{}",
  });
}

test("founder research write token survives long-form editing but never outlives the Access session", async () => {
  const identity = {
    subject: "founder-subject",
    email: "founder@example.test",
    expiresAt: nowSeconds + 12 * 60 * 60,
  };
  const token = await issueResearchCsrf(identity, env, now);

  assert.equal(
    await verifyResearchCsrf(writeRequest(token, "https://founder.example.test", "same-origin"), identity, env, now + 60 * 60 * 1000),
    true,
    "a one-hour scientific edit must not silently invalidate its write token",
  );
  assert.equal(
    await verifyResearchCsrf(writeRequest(token, "https://founder.example.test", "same-origin"), identity, env, now + 8 * 60 * 60 * 1000 + 1000),
    false,
    "the token must still fail closed after its bounded maximum lifetime",
  );

  const shortIdentity = {
    ...identity,
    expiresAt: nowSeconds + 30 * 60,
  };
  const shortToken = await issueResearchCsrf(shortIdentity, env, now);
  const encodedExpiry = Number(shortToken.split(".")[1]);
  assert.equal(encodedExpiry, shortIdentity.expiresAt, "write token must not outlive Cloudflare Access identity expiry");
});

test("same-origin integrity accepts browsers that omit Fetch Metadata but still rejects a foreign Origin", () => {
  assert.equal(verifySameOrigin(writeRequest("token")), true);
  assert.equal(verifySameOrigin(writeRequest("token", "https://founder.example.test", "same-origin")), true);
  assert.equal(verifySameOrigin(writeRequest("token", "https://attacker.example", "cross-site")), false);
});

test("preregistration drawer refreshes saved THESIS records every time it opens", () => {
  const source = fs.readFileSync("research-app/src/preregistration-workbench.tsx", "utf8");
  assert.equal(source.includes('loadState === "READY" || loadState === "LOADING"'), false);
  assert.match(source, /if \(loadState === "LOADING"\) return;/u);
  assert.match(source, /setReview\(null\);/u);
  assert.match(source, /next\.some\(\(record\) => record\.record_id === current\)/u);
});
