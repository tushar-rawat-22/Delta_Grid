import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const layoutSource = fs.readFileSync("app/layout.tsx", "utf8");

test("public observer exposes restrained social metadata without external URLs", () => {
  assert.match(layoutSource, /openGraph:\s*\{/u);
  assert.match(layoutSource, /siteName:\s*"DeltaGrid"/u);
  assert.match(layoutSource, /twitter:\s*\{/u);
  assert.match(layoutSource, /card:\s*"summary"/u);
  assert.doesNotMatch(layoutSource, /metadataBase|alternates:\s*\{\s*canonical|openGraph:[\s\S]*?url:\s*["']/u);
  assert.doesNotMatch(layoutSource, /https:\/\/deltagrid-observer\.tushar142004\.workers\.dev/u);
});

test("public metadata stays research-oriented and avoids trading claims", () => {
  assert.match(layoutSource, /Publicly inspectable quantitative research system/u);
  assert.doesNotMatch(layoutSource, /guaranteed returns|validated alpha|live trading|autonomous trading/iu);
});
