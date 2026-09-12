import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const HOST = "127.0.0.1";
const PORT = 3000;
const BASE_URL = `http://${HOST}:${PORT}`;
const CDP_STARTUP_TIMEOUT_MS = 20000;
const EXPECTED_AUTHORITY_STATE = new Map([
  ["Research result", "No validated alpha"],
  ["Paper / live", "Disabled"],
  ["Capital", "Blocked"],
]);
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

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

function parseDevToolsActivePort(content) {
  const [portLine, browserPath, ...extra] = content.trim().split(/\r?\n/);
  if (extra.length || !/^\d+$/.test(portLine ?? "") || !/^\/devtools\/browser\/[A-Za-z0-9._-]+$/.test(browserPath ?? "")) {
    throw new Error("Malformed Chrome DevToolsActivePort readiness metadata");
  }
  const port = Number(portLine);
  if (!Number.isSafeInteger(port) || port < 1 || port > 65535) throw new Error("Invalid Chrome debugger port");
  return { httpBaseUrl: `http://${HOST}:${port}`, browserWebSocketUrl: `ws://${HOST}:${port}${browserPath}` };
}

async function waitForChromeDebugger(chrome, profileDir) {
  const readinessPath = join(profileDir, "DevToolsActivePort");
  const deadline = Date.now() + CDP_STARTUP_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (chrome.exitCode !== null || chrome.signalCode !== null) throw new Error("Chrome exited before debugger readiness");
    try {
      const readiness = parseDevToolsActivePort(await readFile(readinessPath, "utf8"));
      const browserCdp = createCdp(readiness.browserWebSocketUrl);
      try {
        await browserCdp.ready();
        await browserCdp.send("Browser.getVersion");
        return readiness;
      } finally {
        browserCdp.close();
      }
    } catch (error) {
      if (error?.code !== "ENOENT" && !String(error?.message).includes("readiness metadata")) throw error;
    }
    await delay(50);
  }
  throw new Error(`Chrome did not publish debugger readiness within ${CDP_STARTUP_TIMEOUT_MS}ms`);
}

async function waitForHttp(url, attempts = 80) {
  let lastError;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetch(url, { redirect: "manual" });
      if (response.status < 500) return;
      lastError = new Error(`${url} returned ${response.status}`);
    } catch (error) { lastError = error; }
    await delay(250);
  }
  throw lastError ?? new Error(`Timed out waiting for ${url}`);
}

async function createTarget(readiness) {
  const response = await fetch(`${readiness.httpBaseUrl}/json/new?about:blank`, { method: "PUT" });
  if (!response.ok) throw new Error(`Could not create Chrome target: ${response.status}`);
  const target = await response.json();
  if (!target.webSocketDebuggerUrl) throw new Error("Chrome target omitted websocket URL");
  return target;
}

async function evaluate(cdp, expression) {
  const result = await cdp.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text ?? "Browser evaluation failed");
  return result.result?.value;
}

function assertAuthorityState(pairs, context) {
  const observed = new Map(pairs);
  for (const [label, expected] of EXPECTED_AUTHORITY_STATE) {
    if (observed.get(label) !== expected) {
      throw new Error(`${context} authority mismatch for ${label}: ${observed.get(label) ?? "MISSING"}`);
    }
  }
}

async function captureState(cdp) {
  return evaluate(cdp, `(() => ({
    pathname: location.pathname,
    readyState: document.readyState,
    bodyText: document.body?.innerText ?? "",
    authorityPairs: Array.from(document.querySelectorAll('[aria-label^="Current DeltaGrid"] div')).map((cell) => {
      const label = cell.querySelector(":scope > span")?.textContent?.trim();
      const value = cell.querySelector(":scope > strong")?.textContent?.trim();
      return label && value ? [label, value] : null;
    }).filter(Boolean),
    unsafeSameOriginTargets: Array.from(document.querySelectorAll('a[href], form[action]')).map((element) => element.href || element.action).filter(Boolean).filter((target) => {
      const url = new URL(target, location.href);
      return url.origin === location.origin && /(?:^|\\/)(?:admin|private|founder)(?:\\/|$)/i.test(url.pathname);
    }),
  }))()`);
}

async function navigateOnline(cdp) {
  const loaded = new Promise((resolve) => cdp.on("Page.loadEventFired", resolve));
  await cdp.send("Page.navigate", { url: `${BASE_URL}/` });
  await loaded;
  await delay(250);
  const state = await captureState(cdp);
  if (state.pathname !== "/" || state.readyState !== "complete" || !state.bodyText.trim()) throw new Error(`Online baseline invalid: ${JSON.stringify(state)}`);
  if (state.unsafeSameOriginTargets.length) throw new Error(`Online baseline exposes private targets: ${state.unsafeSameOriginTargets.join(" | ")}`);
  assertAuthorityState(state.authorityPairs, "online baseline");
  return state;
}

async function proveOfflineContinuity(cdp, baseline) {
  await cdp.send("Network.emulateNetworkConditions", { offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0 });
  const fetchResult = await evaluate(cdp, `(async () => {
    try {
      await fetch('/__offline_probe__?t=' + Date.now(), { cache: 'no-store' });
      return 'resolved';
    } catch { return 'rejected'; }
  })()`);
  if (fetchResult !== "rejected") throw new Error(`Offline network probe unexpectedly ${fetchResult}`);
  const offline = await captureState(cdp);
  if (offline.pathname !== baseline.pathname || offline.readyState !== "complete") throw new Error(`Offline document continuity failed: ${JSON.stringify(offline)}`);
  if (offline.bodyText !== baseline.bodyText) throw new Error("Already-rendered observer state changed while connectivity was unavailable");
  if (offline.unsafeSameOriginTargets.length) throw new Error(`Offline observer exposes private targets: ${offline.unsafeSameOriginTargets.join(" | ")}`);
  assertAuthorityState(offline.authorityPairs, "offline continuity");
  console.log(JSON.stringify({ offline_continuity: true, network_probe: "rejected", rendered_state_preserved: true, authority_effect: "NONE" }));
}

async function proveRecovery(cdp, baseline) {
  await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
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
  const loaded = new Promise((resolve) => cdp.on("Page.loadEventFired", resolve));
  await cdp.send("Page.reload", { ignoreCache: true });
  await loaded;
  await delay(250);
  active = false;
  const recovered = await captureState(cdp);
  if (recovered.pathname !== baseline.pathname || recovered.readyState !== "complete" || !recovered.bodyText.trim()) throw new Error(`Recovered document invalid: ${JSON.stringify(recovered)}`);
  if (recovered.unsafeSameOriginTargets.length) throw new Error(`Recovered observer exposes private targets: ${recovered.unsafeSameOriginTargets.join(" | ")}`);
  assertAuthorityState(recovered.authorityPairs, "recovered observer");
  if (consoleErrors.length) throw new Error(`Recovery console errors: ${consoleErrors.join(" | ")}`);
  if (exceptions.length) throw new Error(`Recovery runtime exceptions: ${exceptions.join(" | ")}`);
  if (serverErrors.length) throw new Error(`Recovery observed 5xx responses: ${serverErrors.join(" | ")}`);
  if (networkFailures.length) throw new Error(`Recovery network failures: ${networkFailures.join(" | ")}`);
  console.log(JSON.stringify({ recovery: true, ready_state: "complete", console_errors: 0, runtime_exceptions: 0, server_errors: 0, network_failures: 0, authority_effect: "NONE" }));
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

const chromeBinary = process.env.CHROME_BIN || "google-chrome";
const profileDir = await mkdtemp(join(tmpdir(), "deltagrid-offline-browser-"));
const staticServerScript = String.raw`import functools, http.server, os, sys
class StaticExportHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        translated = super().translate_path(path)
        if os.path.isdir(translated):
            sibling_html = translated.rstrip(os.sep) + ".html"
            if os.path.isfile(sibling_html): return sibling_html
        return translated
handler = functools.partial(StaticExportHandler, directory="out")
http.server.ThreadingHTTPServer((sys.argv[2], int(sys.argv[1])), handler).serve_forever()`;
const server = spawn("python", ["-c", staticServerScript, String(PORT), HOST], { cwd: new URL("..", import.meta.url), stdio: ["ignore", "pipe", "pipe"] });
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
  const baseline = await navigateOnline(cdp);
  await proveOfflineContinuity(cdp, baseline);
  await proveRecovery(cdp, baseline);
  console.log("BROWSER_OFFLINE_RECOVERY=PASS");
} finally {
  if (cdp) {
    try { await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 }); } catch {}
    cdp.close();
  }
  await Promise.all([stopChild(chrome), stopChild(server)]);
  await rm(profileDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
}
