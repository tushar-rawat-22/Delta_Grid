import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const HOST = "127.0.0.1";
const PORT = 3000;
const BASE_URL = `http://${HOST}:${PORT}`;
const CDP_STARTUP_TIMEOUT_MS = 8000;
const EXPECTED_AUTHORITY_STATE = new Map([
  ["Research result", "No validated alpha"],
  ["Paper / live", "Disabled"],
  ["Capital", "Blocked"],
]);
const PUBLIC_ROUTES = ["/", "/research", "/markets", "/evidence", "/risk", "/system", "/missions"];
const VIEWPORTS = [
  { width: 1440, height: 1000, reducedMotion: false },
  { width: 390, height: 844, reducedMotion: false },
  { width: 320, height: 720, reducedMotion: true },
];

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function normalizePublicPath(pathname) {
  if (pathname === "/") return "/";
  return pathname.replace(/\/+$/, "");
}

function assertPublicPath(actual, expected, context) {
  if (normalizePublicPath(actual) !== normalizePublicPath(expected)) {
    throw new Error(`${context} navigated to unexpected pathname ${actual}`);
  }
}

function verifyPublicPathContract() {
  assertPublicPath("/research", "/research", "path preflight canonical");
  assertPublicPath("/research/", "/research", "path preflight static-directory canonicalization");
  for (const invalid of ["/research-private", "/research/admin", "/", "/markets/"]) {
    let rejected = false;
    try { assertPublicPath(invalid, "/research", "path preflight mutation"); } catch { rejected = true; }
    if (!rejected) throw new Error(`Public path contract accepted non-equivalent route ${invalid}`);
  }
  console.log("BROWSER_PUBLIC_PATH_CONTRACT=PASS");
}

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

function parseDevToolsActivePort(content) {
  const [portLine, browserPath, ...extra] = content.trim().split(/\r?\n/);
  if (extra.length || !portLine || !browserPath) {
    throw new Error("DevToolsActivePort must contain exactly a port and browser websocket path");
  }
  if (!/^\d+$/.test(portLine)) throw new Error("DevToolsActivePort port is not numeric");
  const port = Number(portLine);
  if (!Number.isSafeInteger(port) || port < 1 || port > 65535) {
    throw new Error("DevToolsActivePort port is outside the valid TCP range");
  }
  if (!/^\/devtools\/browser\/[A-Za-z0-9._-]+$/.test(browserPath)) {
    throw new Error("DevToolsActivePort browser websocket path is malformed");
  }
  return {
    port,
    browserPath,
    httpBaseUrl: `http://${HOST}:${port}`,
    browserWebSocketUrl: `ws://${HOST}:${port}${browserPath}`,
  };
}

function verifyDevToolsActivePortContract() {
  const parsed = parseDevToolsActivePort("43123\n/devtools/browser/test-id\n");
  if (parsed.port !== 43123 || parsed.browserWebSocketUrl !== "ws://127.0.0.1:43123/devtools/browser/test-id") {
    throw new Error("DevToolsActivePort canonical parse failed");
  }
  for (const invalid of [
    "",
    "not-a-port\n/devtools/browser/test-id\n",
    "70000\n/devtools/browser/test-id\n",
    "43123\n/devtools/page/test-id\n",
    "43123\n/devtools/browser/test-id\nextra\n",
  ]) {
    let rejected = false;
    try { parseDevToolsActivePort(invalid); } catch { rejected = true; }
    if (!rejected) throw new Error(`DevToolsActivePort parser accepted malformed readiness metadata: ${JSON.stringify(invalid)}`);
  }
  console.log("BROWSER_DEVTOOLS_ACTIVE_PORT_CONTRACT=PASS");
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

async function waitForChromeDebugger(chrome, profileDir) {
  const readinessPath = join(profileDir, "DevToolsActivePort");
  const deadline = Date.now() + CDP_STARTUP_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (chrome.exitCode !== null || chrome.signalCode !== null) {
      throw new Error(`Chrome exited before debugger readiness: exit=${chrome.exitCode} signal=${chrome.signalCode}`);
    }
    let content;
    try {
      content = await readFile(readinessPath, "utf8");
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
      await delay(50);
      continue;
    }
    const readiness = parseDevToolsActivePort(content);
    const browserCdp = createCdp(readiness.browserWebSocketUrl);
    try {
      await browserCdp.ready();
      await browserCdp.send("Browser.getVersion");
    } catch (error) {
      throw new Error("Chrome published DevToolsActivePort but browser-level CDP handshake failed", { cause: error });
    } finally {
      browserCdp.close();
    }
    console.log("BROWSER_CDP_STARTUP_HANDSHAKE=PASS");
    return readiness;
  }
  throw new Error(`Chrome did not publish DevToolsActivePort within ${CDP_STARTUP_TIMEOUT_MS}ms`);
}

async function createTarget(readiness) {
  const response = await fetch(`${readiness.httpBaseUrl}/json/new?about:blank`, { method: "PUT" });
  if (!response.ok) throw new Error(`Could not create Chrome target: ${response.status}`);
  const target = await response.json();
  if (!target.webSocketDebuggerUrl) throw new Error("Chrome target omitted webSocketDebuggerUrl");
  return target;
}

async function evaluate(cdp, expression) {
  const result = await cdp.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text ?? "Browser evaluation failed");
  return result.result?.value;
}

async function pressTab(cdp) {
  await cdp.send("Input.dispatchKeyEvent", { type: "rawKeyDown", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9, nativeVirtualKeyCode: 9 });
  await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9, nativeVirtualKeyCode: 9 });
}

async function navigate(cdp, path, width, height, reducedMotion = false) {
  const consoleErrors = [];
  const exceptions = [];
  const serverErrors = [];
  const networkFailures = [];
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
  cdp.on("Network.loadingFailed", ({ errorText, canceled }) => {
    if (active && !canceled) networkFailures.push(errorText ?? "Network loading failed");
  });
  await cdp.send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: width <= 390 });
  await cdp.send("Emulation.setEmulatedMedia", {
    features: [{ name: "prefers-reduced-motion", value: reducedMotion ? "reduce" : "no-preference" }],
  });
  const loaded = new Promise((resolve) => cdp.on("Page.loadEventFired", resolve));
  await cdp.send("Page.navigate", { url: `${BASE_URL}${path}` });
  await loaded;
  await delay(350);
  const pageState = await evaluate(cdp, `(() => ({
    title: document.title,
    pathname: location.pathname,
    bodyWidth: document.body?.scrollWidth ?? 0,
    rootWidth: document.documentElement?.scrollWidth ?? 0,
    viewportWidth: window.innerWidth,
    readyState: document.readyState,
    reducedMotion: matchMedia("(prefers-reduced-motion: reduce)").matches,
    authorityRegions: Array.from(document.querySelectorAll('[aria-label^="Current DeltaGrid"]')).map((region) => ({
      pairs: Array.from(region.querySelectorAll("div")).map((cell) => {
        const label = cell.querySelector(":scope > span")?.textContent?.trim();
        const value = cell.querySelector(":scope > strong")?.textContent?.trim();
        return label && value ? [label, value] : null;
      }).filter(Boolean)
    })),
    focusableCount: Array.from(document.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')).filter((element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
    }).length,
    unsafeSameOriginTargets: Array.from(document.querySelectorAll('a[href], form[action]')).map((element) => element.href || element.action).filter(Boolean).filter((target) => {
      const url = new URL(target, location.href);
      return url.origin === location.origin && /(?:^|\\/)(?:admin|private|founder)(?:\\/|$)/i.test(url.pathname);
    }),
    demoControlCount: document.querySelectorAll('nav[aria-label="Demo research workspace"] button').length,
  }))()`);
  if (pageState.readyState !== "complete") throw new Error(`${path} at ${width}px did not reach complete readyState`);
  assertPublicPath(pageState.pathname, path, `${path} at ${width}px`);
  if (pageState.bodyWidth > pageState.viewportWidth || pageState.rootWidth > pageState.viewportWidth) {
    throw new Error(`${path} at ${width}px horizontally overflows: body=${pageState.bodyWidth}, root=${pageState.rootWidth}, viewport=${pageState.viewportWidth}`);
  }
  if (path === "/") {
    assertAuthorityState(pageState.authorityRegions.flatMap((region) => region.pairs), `${path} at ${width}px`);
  }
  if (reducedMotion && !pageState.reducedMotion) throw new Error(`${path} at ${width}px did not honor reduced-motion emulation`);
  if (pageState.focusableCount < 1) throw new Error(`${path} at ${width}px exposes no keyboard-focusable public control`);
  if (pageState.unsafeSameOriginTargets.length) {
    throw new Error(`${path} at ${width}px exposes private/admin same-origin targets: ${pageState.unsafeSameOriginTargets.join(" | ")}`);
  }

  await pressTab(cdp);
  const focusState = await evaluate(cdp, `(() => {
    const element = document.activeElement;
    if (!element || element === document.body || element === document.documentElement) return null;
    const rect = element.getBoundingClientRect();
    return { tag: element.tagName, visible: rect.width > 0 && rect.height > 0 };
  })()`);
  if (!focusState?.visible) throw new Error(`${path} at ${width}px keyboard Tab did not reach a visible focus target`);

  if (path === "/research" && width === 390) {
    const controls = await evaluate(cdp, `Array.from(document.querySelectorAll('nav[aria-label="Demo research workspace"] button')).map((button) => button.textContent?.trim()).filter(Boolean)`);
    for (let index = 0; index < controls.length; index += 1) {
      await evaluate(cdp, `(() => { const buttons = document.querySelectorAll('nav[aria-label="Demo research workspace"] button'); buttons[${index}]?.click(); })()`);
      await delay(25);
      const selected = await evaluate(cdp, `document.querySelector('nav[aria-label="Demo research workspace"] button:nth-of-type(${index + 1})')?.textContent?.trim()`);
      if (!selected) throw new Error(`/research demo control ${index + 1} disappeared after activation`);
    }
    if (controls.length !== pageState.demoControlCount || controls.length < 1) {
      throw new Error(`/research demo-control matrix changed during activation: before=${pageState.demoControlCount} exercised=${controls.length}`);
    }
  }

  active = false;
  if (consoleErrors.length) throw new Error(`${path} at ${width}px console errors: ${consoleErrors.join(" | ")}`);
  if (exceptions.length) throw new Error(`${path} at ${width}px runtime exceptions: ${exceptions.join(" | ")}`);
  if (serverErrors.length) throw new Error(`${path} at ${width}px observed 5xx responses: ${serverErrors.join(" | ")}`);
  if (networkFailures.length) throw new Error(`${path} at ${width}px network failures: ${networkFailures.join(" | ")}`);
  console.log(JSON.stringify({
    path,
    width,
    height,
    title: pageState.title,
    overflow: false,
    reduced_motion: reducedMotion,
    keyboard_focus: true,
    console_errors: 0,
    runtime_exceptions: 0,
    server_errors: 0,
    network_failures: 0,
    unsafe_same_origin_targets: 0,
    demo_controls_exercised: path === "/research" && width === 390 ? pageState.demoControlCount : 0,
    authority_state: path === "/" ? Object.fromEntries(EXPECTED_AUTHORITY_STATE) : "root_contract_only",
  }));
}

async function reloadDeepLink(cdp, path) {
  const loaded = new Promise((resolve) => cdp.on("Page.loadEventFired", resolve));
  await cdp.send("Page.navigate", { url: `${BASE_URL}${path}` });
  await loaded;
  const reloaded = new Promise((resolve) => cdp.on("Page.loadEventFired", resolve));
  await cdp.send("Page.reload", { ignoreCache: true });
  await reloaded;
  const state = await evaluate(cdp, `({ pathname: location.pathname, readyState: document.readyState })`);
  assertPublicPath(state.pathname, path, `deep-link reload ${path}`);
  if (state.readyState !== "complete") {
    throw new Error(`Deep-link reload failed for ${path}: ${JSON.stringify(state)}`);
  }
  console.log(JSON.stringify({ path, deep_link_reload: true }));
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

verifyPublicPathContract();
verifyAuthorityAssertionContract();
verifyDevToolsActivePortContract();

const chromeBinary = process.env.CHROME_BIN || "google-chrome";
const profileDir = await mkdtemp(join(tmpdir(), "deltagrid-browser-"));
const server = spawn("python", ["-m", "http.server", String(PORT), "--bind", HOST, "--directory", "out"], { cwd: new URL("..", import.meta.url), stdio: ["ignore", "pipe", "pipe"] });
server.stdout.pipe(process.stdout);
server.stderr.pipe(process.stderr);
const chrome = spawn(chromeBinary, ["--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--remote-debugging-port=0", `--user-data-dir=${profileDir}`, "about:blank"], { stdio: ["ignore", "pipe", "pipe"] });
chrome.stdout.pipe(process.stdout);
chrome.stderr.pipe(process.stderr);

let cdp;
try {
  await waitForHttp(`${BASE_URL}/`);
  const readiness = await waitForChromeDebugger(chrome, profileDir);
  const target = await createTarget(readiness);
  cdp = createCdp(target.webSocketDebuggerUrl);
  await cdp.ready();
  await Promise.all([cdp.send("Page.enable"), cdp.send("Runtime.enable"), cdp.send("Network.enable")]);

  for (const route of PUBLIC_ROUTES) {
    for (const viewport of VIEWPORTS) {
      await navigate(cdp, route, viewport.width, viewport.height, viewport.reducedMotion);
    }
  }

  await reloadDeepLink(cdp, "/research");

  const missing = await fetch(`${BASE_URL}/__deltagrid_missing_route__`, { redirect: "manual" });
  if (missing.status !== 404) throw new Error(`Missing-route contract expected 404, received ${missing.status}`);
  console.log(JSON.stringify({ path: "/__deltagrid_missing_route__", status: 404 }));
} finally {
  cdp?.close();
  await Promise.all([stopChild(chrome), stopChild(server)]);
  await rm(profileDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
}
