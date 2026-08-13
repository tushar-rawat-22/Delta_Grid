import { canonicalJson, type CommandRecord } from "./contracts.ts";

const encoder = new TextEncoder();

export async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", encoder.encode(value));
  return bytesToHex(new Uint8Array(digest));
}

export async function hmacHex(keyValue: string, message: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(keyValue),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(message));
  return bytesToHex(new Uint8Array(signature));
}

export async function commandIntegrityProof(
  command: Pick<
    CommandRecord,
    | "command_id"
    | "schema_version"
    | "requested_action_id"
    | "founder_user_id"
    | "requested_at"
    | "expires_at"
    | "one_use_nonce"
    | "expected_core_commit"
    | "expected_authority_state"
    | "parameter_hash"
    | "canonical_request_hash"
  >,
  key: string,
): Promise<string> {
  return hmacHex(key, canonicalJson(command));
}

export function requestSigningMessage(
  method: string,
  pathname: string,
  timestamp: string,
  nonce: string,
  bodyHash: string,
): string {
  return `${method.toUpperCase()}\n${pathname}\n${timestamp}\n${nonce}\n${bodyHash}`;
}

export function safeEqualHex(left: string, right: string): boolean {
  if (!/^[0-9a-f]{64}$/u.test(left) || !/^[0-9a-f]{64}$/u.test(right)) return false;
  let difference = 0;
  for (let index = 0; index < left.length; index += 1) {
    difference |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return difference === 0;
}

function bytesToHex(bytes: Uint8Array): string {
  return [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}
