import assert from "node:assert/strict";
import test from "node:test";
import { calculateMetrics, compareSeries } from "../founder/research-metrics.ts";
import { founderOwnerId, issueResearchCsrf, verifyResearchCsrf, verifySameOrigin } from "../founder/research-security.ts";
import { coinbaseCandleWindow, fetchProviderPayload, parseAlphaDaily, parseProviderJson, providerRetrySeconds, readBoundedText } from "../founder/research-providers.ts";

const identity = { subject: "founder-subject", email: "private@example.test", expiresAt: 1_900_000_000 };
const securityEnv = { DELTAGRID_RESEARCH_CSRF_KEY: "s".repeat(64) };

test("research metrics are deterministic and preserve missing-data honesty", () => {
  const bars = [100, 110, 99, 121].map((close, index) => ({
    observed_at: new Date(Date.UTC(2026, 0, index + 1)).toISOString(),
    close,
  }));
  const metrics = calculateMetrics(bars, 252);
  assert.equal(metrics.latest, 121);
  assert.equal(metrics.return_1d, 121 / 99 - 1);
  assert.equal(metrics.maximum_drawdown, 99 / 110 - 1);
  assert.equal(calculateMetrics([]).latest, null);
  assert.equal(calculateMetrics([{ observed_at: "bad", close: Number.NaN }]).realized_volatility, null);
});

test("comparison aligns timestamps and returns null for zero-variance statistics", () => {
  const comparison = compareSeries({
    left: [
      { observed_at: "2026-01-01T00:00:00.000Z", close: 100 },
      { observed_at: "2026-01-02T00:00:00.000Z", close: 100 },
      { observed_at: "2026-01-03T00:00:00.000Z", close: 100 },
    ],
    right: [
      { observed_at: "2026-01-01T00:00:00.000Z", close: 50 },
      { observed_at: "2026-01-03T00:00:00.000Z", close: 55 },
      { observed_at: "2026-01-04T00:00:00.000Z", close: 60 },
    ],
  });
  assert.equal(comparison.points.length, 2);
  assert.equal(comparison.correlations.left, null);
  assert.equal(comparison.beta_to_first.right, null);
});

test("CSRF proof is founder-bound, same-origin, expiring, and tamper-evident", async () => {
  const now = Date.UTC(2026, 7, 13, 8);
  const token = await issueResearchCsrf(identity, securityEnv, now);
  const request = new Request("https://founder.example.test/api/research/v1/records", {
    method: "POST",
    headers: {
      origin: "https://founder.example.test",
      "sec-fetch-site": "same-origin",
      "x-deltagrid-csrf": token,
    },
  });
  assert.equal(verifySameOrigin(request), true);
  assert.equal(await verifyResearchCsrf(request, identity, securityEnv, now + 1_000), true);
  assert.equal(await verifyResearchCsrf(request, { ...identity, subject: "other" }, securityEnv, now + 1_000), false);
  assert.equal(await verifyResearchCsrf(request, identity, securityEnv, now + 901_000), false);
  const tampered = new Request(request, { headers: { ...Object.fromEntries(request.headers), "x-deltagrid-csrf": `${token.slice(0, -1)}x` } });
  assert.equal(await verifyResearchCsrf(tampered, identity, securityEnv, now + 1_000), false);
  assert.match(await founderOwnerId(identity), /^[0-9a-f]{64}$/u);
});

test("bounded provider reader rejects declared and streamed oversize payloads", async () => {
  await assert.rejects(
    readBoundedText(new Response("{}", { headers: { "content-length": "100" } }), 10),
    /PROVIDER_RESPONSE_TOO_LARGE/u,
  );
  await assert.rejects(readBoundedText(new Response("x".repeat(20)), 10), /PROVIDER_RESPONSE_TOO_LARGE/u);
  assert.equal(await readBoundedText(new Response('{"ok":true}'), 32), '{"ok":true}');

  const pieces = Array.from({ length: 512 }, (_, index) => `chunk-${String(index).padStart(4, "0")};`);
  const manyChunkBody = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const piece of pieces) controller.enqueue(new TextEncoder().encode(piece));
      controller.close();
    },
  });
  assert.equal(await readBoundedText(new Response(manyChunkBody), 16_384), pieces.join(""));
});

test("provider transport fails explicitly on timeout and upstream outage", async () => {
  const timeoutFetcher: typeof fetch = async (_input, init) => new Promise<Response>((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(new Error("aborted")));
  });
  await assert.rejects(
    fetchProviderPayload(new URL("https://provider.example.test/data"), new Headers(), 1024, 5, timeoutFetcher),
    /PROVIDER_NETWORK_FAILURE/u,
  );
  const outageFetcher: typeof fetch = async () => new Response("unavailable", { status: 503 });
  await assert.rejects(
    fetchProviderPayload(new URL("https://provider.example.test/data"), new Headers(), 1024, 100, outageFetcher),
    /PROVIDER_HTTP_503/u,
  );

  const stalledBodyFetcher: typeof fetch = async (_input, init) => new Response(new ReadableStream({
    start(controller) {
      init?.signal?.addEventListener("abort", () => controller.error(new Error("aborted")));
    },
  }));
  await assert.rejects(
    fetchProviderPayload(new URL("https://provider.example.test/data"), new Headers(), 1024, 5, stalledBodyFetcher),
    /PROVIDER_NETWORK_FAILURE/u,
  );
});

test("provider transport uses Worker-compatible manual redirects and rejects every redirect", async () => {
  let redirectMode: RequestRedirect | undefined;
  const redirectFetcher: typeof fetch = async (_input, init) => {
    redirectMode = init?.redirect;
    return new Response(null, { status: 302, headers: { location: "https://other.example.test/data" } });
  };
  await assert.rejects(
    fetchProviderPayload(new URL("https://provider.example.test/data"), new Headers(), 1024, 100, redirectFetcher),
    /PROVIDER_REDIRECT_REJECTED/u,
  );
  assert.equal(redirectMode, "manual");
});

test("provider retry policy isolates quota, transient, and structural failures", () => {
  assert.equal(providerRetrySeconds("OPERATIONAL", "COLLECTION_SUCCEEDED", 3_600), 3_600);
  assert.equal(providerRetrySeconds("DEGRADED", "PROVIDER_SECRET_MISSING", 3_600), 21_600);
  assert.equal(providerRetrySeconds("DEGRADED", "PROVIDER_QUOTA_REACHED", 3_600), 86_400);
  assert.equal(providerRetrySeconds("FAILED", "PROVIDER_NETWORK_FAILURE", 3_600), 300);
  assert.equal(providerRetrySeconds("FAILED", "PROVIDER_HTTP_429", 3_600), 300);
  assert.equal(providerRetrySeconds("FAILED", "PROVIDER_HTTP_525", 3_600), 300);
  assert.equal(providerRetrySeconds("FAILED", "PROVIDER_SCHEMA_INVALID", 3_600), 3_600);
});

test("Coinbase collection uses a bounded settled 240-hour window", () => {
  const window = coinbaseCandleWindow(Date.UTC(2026, 7, 13, 10, 47, 29));
  assert.equal(window.end, "2026-08-13T10:00:00.000Z");
  assert.equal(window.start, "2026-08-03T10:00:00.000Z");
  assert.equal(window.settledBeforeMs, Date.UTC(2026, 7, 13, 10));
});

test("Alpha Vantage schema rejects quota messages and malformed values", () => {
  assert.throws(() => parseAlphaDaily('{"Note":"daily quota reached"}'), /PROVIDER_QUOTA_REACHED/u);
  assert.throws(() => parseProviderJson("not-json"), /PROVIDER_JSON_INVALID/u);
  assert.throws(() => parseAlphaDaily('{"Time Series (Daily)":{"2026-08-12":{"1. open":"bad"}}}'), /PROVIDER_SCHEMA_INVALID/u);
  assert.deepEqual(parseAlphaDaily('{"Time Series (Daily)":{"2026-08-12":{"1. open":"10","2. high":"11","3. low":"9","4. close":"10.5","5. volume":"100"}}}'), [
    { date: "2026-08-12", open: 10, high: 11, low: 9, close: 10.5, volume: 100 },
  ]);
});
