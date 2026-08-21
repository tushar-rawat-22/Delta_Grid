import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const layoutSource = fs.readFileSync("app/layout.tsx", "utf8");
const navSource = fs.readFileSync("components/public-site-nav.tsx", "utf8");
const shellCss = fs.readFileSync("app/public-shell.css", "utf8");

test("public shell keeps a keyboard-usable skip link", () => {
  assert.match(layoutSource, /href="#main-content"/u);
  assert.match(layoutSource, /id="main-content"\s+tabIndex=\{-1\}/u);
});

test("public navigation exposes stable accessibility labels", () => {
  assert.match(navSource, /<nav[^>]+aria-label="DeltaGrid public product"/u);
  assert.match(navSource, /aria-label="DeltaGrid Research Engine home"/u);
  assert.match(navSource, /aria-current=\{active \? "page" : undefined\}/u);
});

test("decorative navigation marks stay hidden from assistive technology", () => {
  assert.match(navSource, /public-brand-mark" aria-hidden="true"/u);
  assert.match(navSource, /<i aria-hidden="true"/u);
});

test("public motion respects the operating-system reduced-motion preference", () => {
  assert.match(shellCss, /@media\s*\(prefers-reduced-motion:\s*reduce\)/u);
  assert.match(shellCss, /html\s*\{\s*scroll-behavior:\s*auto;/u);
  assert.match(shellCss, /\.snapshot-grid img\s*\{\s*transition:\s*none;/u);
  assert.match(shellCss, /\.snapshot-grid figure:hover img\s*\{\s*transform:\s*none;/u);
});
