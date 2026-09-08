import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const HOST = "127.0.0.1";
const PORT = 3000;
const DEBUG_PORT = 9222;
const BASE_URL = `http://${HOST}:${PORT}`;
const CDP_BASE_URL = `http://${HOST}:${DEBUG_PORT}`;
const CDP_STARTUP_TIMEOUT_MS = 8000;
const EXPECTED_AUTHORITY_STATE = new Map([
  ["Research result", "No validated alpha"],
  ["Paper / live", "Disabled"],
  ["Capital", "Blocked"],
]);

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function assertAuthorityState(authorityPairs, context) {
  const observed = new Map(authorityPairs);
  for (const [label, expectedValue] of EXPECTED_AUTHORITY_STATE) {
    const actualValue = observed.get(label);
    if (actualValue !== expectedValue) {
      throw new Error(`${context} authority state mismatch for ${label}: expected ${expectedValue}, received ${actualValue ?? "MISSING"}`);
    }
  }
}

function verifyAuthorityAssertionContract() {
  const canonical = [...EXPECTED_AUTHORITY_STATE.entries()];
  assertAuthorityState(canonical, "semantic preflight canonical");
  const mutations = [
    canonical.filter(([label]) => label !== "Capital"),
    canonical.map(([label, value]) => [label, label === "Paper / live" ? "Enabled" : value]),
  ];
  for (const mutation of mutations) {
    let rejected = false;
    try { assertAuthorityState(mutation, "semantic preflight mutation"); } catch { rejected = true; }
    if (!rejected) throw new Error("Semantic authority assertion accepted a protected-state mutation");
  }
  console.log("BROWSER_AUTHORITY_ASSERTION_CONTRACT=PASS");
}

function isTransientCdpBootstrapError(error) {
  const cause = error?.cause ?? error;
  return ["ECONNREFUSED", "ECONNRESET", "EPIPE"].includes(cause?.code);
}

function verifyCdpStartupClassifierContract() {
  const transient = Object.assign(new Error("connect refused"), { code: "ECONNREFUSED" });
  const wrapped = new TypeError("fetch failed", { cause: transient });
  const persistent = new Error("protocol mismatch");
  if (!isTransientCdpBootstrapError(wrapped) || isTransientCdpBootstrapError(persistent)) {
    throw new Error("CDP startup classifier contract failed");
  }
  console.log("BROWSER_CDP_STARTUP_CLASSIFIER=PASS");
}

async function waitForHttp(url, attempts = 80, pauseMs = 250) {
  let lastError;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetch(url, { redirect: "manual" });
      if (response.status < 500) return response;
      lastError = new Error(`${url} returned ${response.status}`);
    } catch (error) { lastError = error; }
    await delay(pauseMs);
  }
  throw lastError ?? new Error(`Timed out waiting for ${url}`);
}

async function waitForJson(url, attempts = 80, pauseMs = 100) {
  let lastError;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return await response.json();
      lastError = new Error(`${url} returned ${response.status}`);
    } catch (error) { lastError = error; }
    await delay(pauseMs);
  }
  throw lastError ?? new Error(`Timed out waiting for ${url}`);
}

function createCdp(wsUrl) {
  const socket = new WebSocket(wsUrl);
  let sequence = 0;
  const pending = new Map();
  const listeners = new Map();
  const opened = new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.id) {
      const waiter = pending.get(message.id);
      if (!waiter) return;
      pending.delete(message.id);
      if (message.error) waiter.reject(new Error(message.error.message));
      else waiter.resolve(message.result ?? {});
      return;
    }
    for (const handler of listeners.get(message.method) ?? []) handler(message.params ?? {});
  });
  return {
    ready: () => opened,
    on(method, handler) {
      const handlers = listeners.get(method) ?? [];
      handlers.push(handler);
      listeners.set(method, handlers);
    },
    send(method, params = {}) {
      const id = ++sequence;
      return new Promise((resolve, reject) => {
        pending.set(id, { resolve, reject });
        socket.send(JSON.stringify({ id, method, params }));
      });
    },
    close: () => socket.close(),
  };
}

async function createTargetAfterCdpHandshake(chrome) {
  const deadline = Date.now() + CDP_STARTUP_TIMEOUT_MS;
  let lastTransient;
  while (Date.now() < deadline) {
    if (chrome.exitCode !== null || chrome.signalCode !== null) {
      throw new Error(`Chrome exited before CDP became ready: exit=${chrome.exitCode} signal=${chrome.signalCode}`);
    }
    try {
      const version = await waitForJson(`${CDP_BASE_URL}/json/version`, 1, 0);
      if (!version.webSocketDebuggerUrl) throw new Error("Chrome CDP version response omitted webSocketDebuggerUrl");
      const browserCdp = createCdp(version.webSocketDebuggerUrl);
      try {
        await browserCdp.ready();
        await browserCdp.send("Browser.getVersion");
      } finally {
        browserCdp.close();
      }
      const response = await fetch(`${CDP_BASE_URL}/json/new?about:blank`, { method: "PUT" });
      if (!response.ok) throw new Error(`Could not create Chrome target: ${response.status}`);
      const target = await response.json();
      if (!target.webSocketDebuggerUrl) throw new Error("Chrome target omitted webSocketDebuggerUrl");
      console.log("BROWSER_CDP_STARTUP_HANDSHAKE=PASS");
      return target;
    } catch (error) {
      if (!isTransientCdpBootstrapError(error)) throw error;
      lastTransient = error;
      await delay(100);
    }
  }
  throw new Error(`Chrome CDP startup remained unavailable for ${CDP_STARTUP_TIMEOUT_MS}ms`, { cause: lastTransient });
}

async function evaluate(cdp, expression) {
  const result = await cdp.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text ?? "Browser evaluation failed");
  return result.result?.value;
}

async function navigate(cdp, path, width, height) {
  const consoleErrors = [];
  const exceptions = [];
  const serverErrors = [];
  let active = true;
  cdp.on("Runtime.consoleAPICalled", ({ type, args = [] }) => {
    if (active && ["error", "assert"].includes(type)) consoleErrors.push(args.map((arg) => arg.value ?? arg.description ?? "").join(" "));
  });
  cdp.on("Runtime.exceptionThrown", ({ exceptionDetails }) => {
    if (active) exceptions.push(exceptionDetails?.exception?.description ?? exceptionDetails?.text ?? "Runtime exception");
  });
  cdp.on("Network.responseReceived", ({ response }) => {
    if (active && response.status >= 500) serverErrors.push(`${response.status} ${response.url}`);
  });
  await cdp.send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: width <= 390 });
  const loaded = new Promise((resolve) => cdp.on("Page.loadEventFired", resolve));
  await cdp.send("Page.navigate", { url: `${BASE_URL}${path}` });
  await loaded;
  await delay(350);
  const pageState = await evaluate(cdp, `(() => ({
    title: document.title,
    bodyWidth: document.body?.scrollWidth ?? 0,
    rootWidth: document.documentElement?.scrollWidth ?? 0,
    viewportWidth: window.innerWidth,
    readyState: document.readyState,
    authorityRegions: Array.from(document.querySelectorAll('[aria-label^="Current DeltaGrid"]')).map((region) => ({
      pairs: Array.from(region.querySelectorAll("div")).map((cell) => {
        const label = cell.querySelector(":scope > span")?.textContent?.trim();
        const value = cell.querySelector(":scope > strong")?.textContent?.trim();
        return label && value ? [label, value] : null;
      }).filter(Boolean)
    }))
  }))()`);
  active = false;
  if (pageState.readyState !== "complete") throw new Error(`${path} at ${width}px did not reach complete readyState`);
  if (pageState.bodyWidth > pageState.viewportWidth || pageState.rootWidth > pageState.viewportWidth) {
    throw new Error(`${path} at ${width}px horizontally overflows: body=${pageState.bodyWidth}, root=${pageState.rootWidth}, viewport=${pageState.viewportWidth}`);
  }
  assertAuthorityState(pageState.authorityRegions.flatMap((region) => region.pairs), `${path} at ${width}px`);
  if (consoleErrors.length) throw new Error(`${path} at ${width}px console errors: ${consoleErrors.join(" | ")}`);
  if (exceptions.length) throw new Error(`${path} at ${width}px runtime exceptions: ${exceptions.join(" | ")}`);
  if (serverErrors.length) throw new Error(`${path} at ${width}px observed 5xx responses: ${serverErrors.join(" | ")}`);
  console.log(JSON.stringify({ path, width, height, title: pageState.title, overflow: false, console_errors: 0, runtime_exceptions: 0, server_errors: 0, authority_state: Object.fromEntries(EXPECTED_AUTHORITY_STATE) }));
}

async function stopChild(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const exited = new Promise((resolve) => child.once("exit", () => resolve(true)));
  child.kill("SIGTERM");
  const graceful = await Promise.race([exited, delay(2000).then(() => false)]);
  if (graceful || child.exitCode !== null || child.signalCode !== null) return;
  const killed = new Promise((resolve) => child.once("exit", resolve));
  child.kill("SIGKILL");
  await killed;
}

verifyAuthorityAssertionContract();
verifyCdpStartupClassifierContract();

const chromeBinary = process.env.CHROME_BIN || "google-chrome";
const profileDir = await mkdtemp(join(tmpdir(), "deltagrid-browser-"));
const server = spawn("python", ["-m", "http.server", String(PORT), "--bind", HOST, "--directory", "out"], { cwd: new URL("..", import.meta.url), stdio: ["ignore", "pipe", "pipe"] });
server.stdout.pipe(process.stdout);
server.stderr.pipe(process.stderr);
const chrome = spawn(chromeBinary, ["--headless=new", "--no-sandbox", "--disable-dev-shm-usage", `--remote-debugging-port=${DEBUG_PORT}`, `--user-data-dir=${profileDir}`, "about:blank"], { stdio: ["ignore", "pipe", "pipe"] });
chrome.stdout.pipe(process.stdout);
chrome.stderr.pipe(process.stderr);

let cdp;
try {
  await waitForHttp(`${BASE_URL}/`);
  const target = await createTargetAfterCdpHandshake(chrome);
  cdp = createCdp(target.webSocketDebuggerUrl);
  await cdp.ready();
  await Promise.all([cdp.send("Page.enable"), cdp.send("Runtime.enable"), cdp.send("Network.enable")]);
  await navigate(cdp, "/", 1440, 1000);
  await navigate(cdp, "/", 390, 844);
  const missing = await fetch(`${BASE_URL}/__deltagrid_missing_route__`, { redirect: "manual" });
  if (missing.status !== 404) throw new Error(`Missing-route contract expected 404, received ${missing.status}`);
  console.log(JSON.stringify({ path: "/__deltagrid_missing_route__", status: 404 }));
} finally {
  cdp?.close();
  await Promise.all([stopChild(chrome), stopChild(server)]);
  await rm(profileDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
}
