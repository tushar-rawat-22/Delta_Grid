import { useEffect, useState } from "react";

const EVENT_NAME = "deltagrid:research-write-feedback";
const RECORD_PATH = /^\/api\/research\/v1\/records(?:\/[0-9a-f-]{36})?$/u;

type Feedback = {
  kind: "success" | "error";
  message: string;
};

type BootstrapToken = {
  csrf_token?: unknown;
};

type RecordWriteResponse = {
  record?: {
    revision?: unknown;
  };
};

let installed = false;

export function installResearchWriteResilience(): void {
  if (installed || typeof window === "undefined") return;
  installed = true;

  const nativeFetch = window.fetch.bind(window);

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = requestUrl(input);
    const method = requestMethod(input, init);
    const eligible =
      url.origin === window.location.origin &&
      RECORD_PATH.test(url.pathname) &&
      (method === "POST" || method === "PUT");

    if (!eligible) return nativeFetch(input, init);

    let response: Response;
    try {
      response = await nativeFetch(input, init);
    } catch (cause) {
      dispatchFeedback({
        kind: "error",
        message: cause instanceof Error ? `Save failed: ${cause.message}` : "Save failed: network request failed",
      });
      throw cause;
    }

    if (
      response.status === 403 &&
      (await responseErrorCode(response.clone())) === "REQUEST_INTEGRITY_FAILED" &&
      typeof input === "string"
    ) {
      response = await retryWithFreshToken(nativeFetch, input, init, response);
    }

    await announceResult(response.clone());
    return response;
  };
}

export function ResearchWriteFeedback() {
  const [feedback, setFeedback] = useState<Feedback | null>(null);

  useEffect(() => {
    function receive(event: Event): void {
      const detail = (event as CustomEvent<Feedback>).detail;
      if (!detail || (detail.kind !== "success" && detail.kind !== "error")) return;
      setFeedback(detail);
    }
    window.addEventListener(EVENT_NAME, receive);
    return () => window.removeEventListener(EVENT_NAME, receive);
  }, []);

  useEffect(() => {
    if (!feedback) return;
    const timer = window.setTimeout(() => setFeedback(null), feedback.kind === "success" ? 5000 : 12000);
    return () => window.clearTimeout(timer);
  }, [feedback]);

  if (!feedback) return null;

  return (
    <div
      className={`research-write-feedback ${feedback.kind}`}
      role={feedback.kind === "error" ? "alert" : "status"}
      aria-live={feedback.kind === "error" ? "assertive" : "polite"}
    >
      <strong>{feedback.kind === "success" ? "Research saved" : "Save failed"}</strong>
      <span>{feedback.message}</span>
      <button type="button" onClick={() => setFeedback(null)} aria-label="Dismiss save message">×</button>
    </div>
  );
}

async function retryWithFreshToken(
  nativeFetch: typeof window.fetch,
  input: string,
  init: RequestInit | undefined,
  original: Response,
): Promise<Response> {
  try {
    const bootstrap = await nativeFetch("/api/research/v1/bootstrap", {
      credentials: "same-origin",
      headers: { accept: "application/json" },
    });
    if (!bootstrap.ok) return original;
    const payload = await bootstrap.json() as BootstrapToken;
    if (typeof payload.csrf_token !== "string" || !payload.csrf_token) return original;

    const headers = new Headers(init?.headers);
    headers.set("x-deltagrid-csrf", payload.csrf_token);
    return nativeFetch(input, { ...init, headers });
  } catch {
    return original;
  }
}

async function announceResult(response: Response): Promise<void> {
  if (response.ok) {
    let revision: number | null = null;
    try {
      const payload = await response.json() as RecordWriteResponse;
      revision = Number.isInteger(payload.record?.revision) ? Number(payload.record?.revision) : null;
    } catch {
      revision = null;
    }
    dispatchFeedback({
      kind: "success",
      message: revision ? `Saved as revision ${revision}.` : "Saved successfully.",
    });
    return;
  }

  const code = await responseErrorCode(response);
  dispatchFeedback({
    kind: "error",
    message: humanizeWriteError(code, response.status),
  });
}

async function responseErrorCode(response: Response): Promise<string | null> {
  try {
    const payload = await response.json() as { error?: unknown; request_id?: unknown };
    const error = typeof payload.error === "string" ? payload.error : null;
    const requestId = typeof payload.request_id === "string" ? payload.request_id : null;
    return requestId && error ? `${error}|${requestId}` : error;
  } catch {
    return null;
  }
}

function humanizeWriteError(value: string | null, status: number): string {
  const [code, requestId] = (value ?? "").split("|", 2);
  const known: Record<string, string> = {
    REQUEST_INTEGRITY_FAILED: "The secure write session could not be refreshed. Reload Founder Mode and try once more; your current text has not been saved.",
    REVISION_CONFLICT: "This record changed since you opened it. Reload before editing again so an older revision cannot overwrite newer research.",
    INVALID_RECORD_SHAPE: "The research record contains a field the server does not accept.",
    INVALID_RECORD_TAGS: "One or more tags are invalid.",
    INVALID_SOURCE_URL: "The source URL is invalid. Leave it blank or use a complete http/https URL.",
    SERVICE_UNAVAILABLE: "The research database is temporarily unavailable. Your current text remains in the editor; retry after the service recovers.",
  };
  const base = known[code] ?? `The research API rejected the save (HTTP ${status}${code ? ` · ${code.replaceAll("_", " ").toLowerCase()}` : ""}).`;
  return requestId ? `${base} Request ${requestId}.` : base;
}

function dispatchFeedback(feedback: Feedback): void {
  window.dispatchEvent(new CustomEvent<Feedback>(EVENT_NAME, { detail: feedback }));
}

function requestUrl(input: RequestInfo | URL): URL {
  if (typeof input === "string") return new URL(input, window.location.href);
  if (input instanceof URL) return new URL(input.href, window.location.href);
  return new URL(input.url, window.location.href);
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  if (init?.method) return init.method.toUpperCase();
  if (typeof Request !== "undefined" && input instanceof Request) return input.method.toUpperCase();
  return "GET";
}
