import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const navSource = fs.readFileSync("components/public-site-nav.tsx", "utf8");
const layoutSource = fs.readFileSync("app/layout.tsx", "utf8");

test("public shell exposes the complete public product map without promoting founder login", () => {
  for (const route of ["/research", "/markets", "/evidence", "/missions", "/system", "/risk", "/docs", "/about"]) {
    assert.ok(navSource.includes(`\"${route}\"`), route);
  }
  assert.match(navSource, /Demo Mode/u);
  assert.match(navSource, /Access model/u);
  assert.doesNotMatch(navSource, /Founder Log in/u);
  assert.match(navSource, /Public demo/u);
  assert.match(navSource, /Sanitized fixtures · no writes/u);
});

test("public shell marks the active route without introducing a private data surface", () => {
  assert.match(navSource, /usePathname/u);
  assert.match(navSource, /aria-current/u);
  assert.match(navSource, /is-active/u);

  for (const forbidden of ["fetch(", "XMLHttpRequest", "WebSocket(", "/api/research/v1/", "csrf_token", "method: \"POST\""]) {
    assert.equal(navSource.includes(forbidden), false, forbidden);
  }
});

test("root layout uses the shared shell once for every public route", () => {
  assert.match(layoutSource, /<PublicSiteNav \/>/u);
  assert.match(layoutSource, /\.\/public-shell\.css/u);
  assert.match(layoutSource, /Public Demo Mode uses sanitized deterministic fixtures/u);
});
