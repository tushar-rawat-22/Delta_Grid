import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const HOST = "127.0.0.1";
const PORT = 3000;
const DEBUG_PORT = 9222;
const BASE_URL = `http://${HOST}:${PORT}`;
const AUTHORITY_MARKERS = [
  "No validated alpha",
  "Paper/live disabled",
  "Capital blocked",
];

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitForHttp(url, attempts = 80, pauseMs = 250) {
  let lastError;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetch(url, { redirect: "manual" });
      if (response.status < 500) return response;
      lastError = new Error(`${url} returned ${response.status}`);
    } catch (error) {
      lastError = error;
    }
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
    } catch (error) {
      lastError = error;
    }
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
    const handlers = listeners.get(message.method) ?? [];
    for (const handler of handlers) handler(message.params ?? {});
  });

  return {
    async ready() {
      await opened;
    },
    on(method, handler) {
      const handlers = listeners.get(method) ?? [];
      handlers.push(handler);
      listeners.set(method, handlers);
    },
    send(method, params = {}) {
      sequence += 1;
      const id = sequence;
      return new Promise((resolve, reject) => {
        pending.set(id, { resolve, reject });
        socket.send(JSON.stringify({ id, method, params }));
      });
    },
    close() {
      socket.close();
    },
  };
}

async function evaluate(cdp, expression) {
  const result = await cdp.send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.text ?? "Browser evaluation failed");
  }
  return result.result?.value;
}

async function navigate(cdp, path, width, height) {
  const consoleErrors = [];
  const exceptions = [];
  const serverErrors = [];
  let active = true;

  const recordConsole = ({ type, args = [] }) => {
    if (!active || !["error", "assert"].includes(type)) return;
    consoleErrors.push(args.map((arg) => arg.value ?? arg.description ?? "").join(" "));
  };
  const recordException = ({ exceptionDetails }) => {
    if (!active) return;
    exceptions.push(exceptionDetails?.exception?.description ?? exceptionDetails?.text ?? "Runtime exception");
  };
  const recordResponse = ({ response }) => {
    if (!active || response.status < 500) return;
    serverErrors.push(`${response.status} ${response.url}`);
  };

  cdp.on("Runtime.consoleAPICalled", recordConsole);
  cdp.on("Runtime.exceptionThrown", recordException);
  cdp.on("Network.responseReceived", recordResponse);

  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: width <= 390,
  });

  const loaded = new Promise((resolve) => cdp.on("Page.loadEventFired", resolve));
  await cdp.send("Page.navigate", { url: `${BASE_URL}${path}` });
  await loaded;
  await delay(350);

  const pageState = await evaluate(
    cdp,
    `(() => ({
      title: document.title,
      bodyText: document.body?.innerText ?? "",
      bodyWidth: document.body?.scrollWidth ?? 0,
      rootWidth: document.documentElement?.scrollWidth ?? 0,
      viewportWidth: window.innerWidth,
      readyState: document.readyState
    }))()`,
  );

  active = false;

  if (pageState.readyState !== "complete") {
    throw new Error(`${path} at ${width}px did not reach complete readyState`);
  }
  if (pageState.bodyWidth > pageState.viewportWidth || pageState.rootWidth > pageState.viewportWidth) {
    throw new Error(
      `${path} at ${width}px horizontally overflows: body=${pageState.bodyWidth}, root=${pageState.rootWidth}, viewport=${pageState.viewportWidth}`,
    );
  }
  for (const marker of AUTHORITY_MARKERS) {
    if (!pageState.bodyText.includes(marker)) {
      throw new Error(`${path} at ${width}px is missing authority marker: ${marker}`);
    }
  }
  if (consoleErrors.length) {
    throw new Error(`${path} at ${width}px console errors: ${consoleErrors.join(" | ")}`);
  }
  if (exceptions.length) {
    throw new Error(`${path} at ${width}px runtime exceptions: ${exceptions.join(" | ")}`);
  }
  if (serverErrors.length) {
    throw new Error(`${path} at ${width}px observed 5xx responses: ${serverErrors.join(" | ")}`);
  }

  console.log(
    JSON.stringify({
      path,
      width,
      height,
      title: pageState.title,
      overflow: false,
      console_errors: 0,
      runtime_exceptions: 0,
      server_errors: 0,
      authority_markers: AUTHORITY_MARKERS,
    }),
  );
}

const chromeBinary = process.env.CHROME_BIN || "google-chrome";
const profileDir = await mkdtemp(join(tmpdir(), "deltagrid-browser-"));
const next = spawn("./node_modules/.bin/next", ["start", "-H", HOST, "-p", String(PORT)], {
  cwd: new URL("..", import.meta.url),
  stdio: ["ignore", "pipe", "pipe"],
});
next.stdout.pipe(process.stdout);
next.stderr.pipe(process.stderr);

const chrome = spawn(
  chromeBinary,
  [
    "--headless=new",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    `--remote-debugging-port=${DEBUG_PORT}`,
    `--user-data-dir=${profileDir}`,
    "about:blank",
  ],
  { stdio: ["ignore", "pipe", "pipe"] },
);
chrome.stdout.pipe(process.stdout);
chrome.stderr.pipe(process.stderr);

let cdp;
try {
  await waitForHttp(`${BASE_URL}/`);
  await waitForJson(`http://${HOST}:${DEBUG_PORT}/json/version`);
  const target = await fetch(`http://${HOST}:${DEBUG_PORT}/json/new?about:blank`, { method: "PUT" }).then((response) => {
    if (!response.ok) throw new Error(`Could not create Chrome target: ${response.status}`);
    return response.json();
  });

  cdp = createCdp(target.webSocketDebuggerUrl);
  await cdp.ready();
  await Promise.all([
    cdp.send("Page.enable"),
    cdp.send("Runtime.enable"),
    cdp.send("Network.enable"),
  ]);

  await navigate(cdp, "/", 1440, 1000);
  await navigate(cdp, "/", 390, 844);

  const missing = await fetch(`${BASE_URL}/__deltagrid_missing_route__`, { redirect: "manual" });
  if (missing.status !== 404) {
    throw new Error(`Missing-route contract expected 404, received ${missing.status}`);
  }
  console.log(JSON.stringify({ path: "/__deltagrid_missing_route__", status: 404 }));
} finally {
  cdp?.close();
  chrome.kill("SIGTERM");
  next.kill("SIGTERM");
  await rm(profileDir, { recursive: true, force: true });
}
