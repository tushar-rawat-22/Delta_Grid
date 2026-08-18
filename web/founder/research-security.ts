import { sha256Hex } from "./crypto.ts";
import type { FounderIdentity } from "./auth.ts";

const TOKEN_VERSION = "v1";
const TOKEN_TTL_SECONDS = 15 * 60;
const TOKEN_CLOCK_SKEW_SECONDS = 30;

export type ResearchSecurityEnv = {
  DELTAGRID_RESEARCH_CSRF_KEY?: string;
};

export async function founderOwnerId(identity: FounderIdentity): Promise<string> {
  return sha256Hex(`deltagrid-research:${identity.subject ?? identity.email}`);
}

export async function issueResearchCsrf(identity: FounderIdentity, env: ResearchSecurityEnv, now = Date.now()): Promise<string> {
  const nowSeconds = Math.floor(now / 1000);
  const accessExpiry = Number.isSafeInteger(identity.expiresAt) ? Number(identity.expiresAt) : null;
  const expires = Math.min(
    nowSeconds + TOKEN_TTL_SECONDS,
    accessExpiry ?? nowSeconds + TOKEN_TTL_SECONDS,
  );
  const ownerId = await founderOwnerId(identity);
  const payload = `${TOKEN_VERSION}.${expires}.${ownerId}`;
  return `${payload}.${await sign(payload, requiredKey(env))}`;
}

export async function verifyResearchCsrf(
  request: Request,
  identity: FounderIdentity,
  env: ResearchSecurityEnv,
  now = Date.now(),
): Promise<boolean> {
  const token = request.headers.get("x-deltagrid-csrf")?.trim() ?? "";
  const parts = token.split(".");
  if (parts.length !== 4 || parts[0] !== TOKEN_VERSION || !/^\d{10}$/u.test(parts[1]) || !/^[0-9a-f]{64}$/u.test(parts[2]) || !/^[A-Za-z0-9_-]{43}$/u.test(parts[3])) return false;
  const nowSeconds = Math.floor(now / 1000);
  const expires = Number(parts[1]);
  if (
    !Number.isSafeInteger(expires) ||
    expires < nowSeconds ||
    expires > nowSeconds + TOKEN_TTL_SECONDS + TOKEN_CLOCK_SKEW_SECONDS
  ) return false;
  if (
    Number.isSafeInteger(identity.expiresAt) &&
    expires > Number(identity.expiresAt) + TOKEN_CLOCK_SKEW_SECONDS
  ) return false;
  if (parts[2] !== await founderOwnerId(identity)) return false;
  const payload = parts.slice(0, 3).join(".");
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(requiredKey(env)),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"],
  );
  return crypto.subtle.verify("HMAC", key, decodeBase64Url(parts[3]), new TextEncoder().encode(payload));
}

export function verifySameOrigin(request: Request): boolean {
  const url = new URL(request.url);
  const origin = request.headers.get("origin");
  const fetchSite = request.headers.get("sec-fetch-site");
  return origin === url.origin && (
    fetchSite === null ||
    fetchSite === "same-origin" ||
    fetchSite === "none"
  );
}

async function sign(payload: string, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return encodeBase64Url(new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload))));
}

function requiredKey(env: ResearchSecurityEnv): string {
  const key = env.DELTAGRID_RESEARCH_CSRF_KEY?.trim() ?? "";
  if (key.length < 32 || key.length > 512) throw new Error("RESEARCH_CSRF_KEY_INVALID");
  return key;
}

function encodeBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/u, "");
}

function decodeBase64Url(value: string): ArrayBuffer {
  const padded = value.replaceAll("-", "+").replaceAll("_", "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes.buffer;
}
