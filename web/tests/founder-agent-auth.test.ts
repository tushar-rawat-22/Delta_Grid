import assert from "node:assert/strict";
import test from "node:test";
import {
  SignJWT,
  createLocalJWKSet,
  exportJWK,
  generateKeyPair,
  type JSONWebKeySet,
} from "jose";
import { verifyAgentRequest } from "../founder/agent-auth.ts";
import { hmacHex, requestSigningMessage, sha256Hex } from "../founder/crypto.ts";
import type { D1DatabaseLike, D1ResultLike, D1StatementLike } from "../founder/database.ts";

const teamDomain = "https://deltagrid-unit.cloudflareaccess.com";
const audience = "deltagridAgentAccessAudience123456";
const hmacKey = "agent-unit-signing-key-".repeat(3);

class NonceStatement implements D1StatementLike {
  values: unknown[] = [];
  private readonly nonces: Set<string>;

  constructor(nonces: Set<string>) { this.nonces = nonces; }

  bind(...values: unknown[]): D1StatementLike {
    this.values = values;
    return this;
  }

  async first<T>(): Promise<T | null> { return null; }
  async all<T>(): Promise<D1ResultLike<T>> { return { success: true, results: [] }; }
  async run<T>(): Promise<D1ResultLike<T>> {
    const identity = `${String(this.values[0])}:${String(this.values[1])}`;
    if (this.nonces.has(identity)) throw new Error("duplicate");
    this.nonces.add(identity);
    return { success: true, results: [], meta: { changes: 1 } };
  }
}

class NonceDb implements D1DatabaseLike {
  readonly nonces = new Set<string>();
  prepare(): D1StatementLike { return new NonceStatement(this.nonces); }
  async batch<T>(): Promise<D1ResultLike<T>[]> { return []; }
}

type FixtureOptions = {
  tokenType?: string;
  subject?: string;
  omitIssuedAt?: boolean;
  omitExpiration?: boolean;
};

async function fixture(options: FixtureOptions = {}) {
  const pair = await generateKeyPair("RS256");
  const jwk = await exportJWK(pair.publicKey);
  jwk.kid = "agent-unit-key";
  jwk.alg = "RS256";
  const keySet = createLocalJWKSet({ keys: [jwk] } as JSONWebKeySet);
  const now = Math.floor(Date.now() / 1000);
  let signer = new SignJWT({
    common_name: "unit-agent.access",
    type: options.tokenType ?? "app",
  })
    .setProtectedHeader({ alg: "RS256", kid: "agent-unit-key" })
    .setIssuer(teamDomain)
    .setAudience(audience)
    .setSubject(options.subject ?? "");
  if (!options.omitIssuedAt) signer = signer.setIssuedAt(now);
  if (!options.omitExpiration) signer = signer.setExpirationTime(now + 300);
  const token = await signer.sign(pair.privateKey);
  return { keySet, token };
}

async function signedRequest(token: string, nonce = "0".repeat(32), signatureOverride?: string): Promise<Request> {
  const body = JSON.stringify({ authority_state: "NONE", core_commit: "0".repeat(40) });
  const timestamp = String(Math.floor(Date.now() / 1000));
  const signature = signatureOverride ?? await hmacHex(
    hmacKey,
    requestSigningMessage("POST", "/agent/v1/claim", timestamp, nonce, await sha256Hex(body)),
  );
  return new Request("https://founder.example.test/agent/v1/claim", {
    method: "POST",
    body,
    headers: {
      "cf-access-jwt-assertion": token,
      "x-dg-agent-id": "unit-agent",
      "x-dg-timestamp": timestamp,
      "x-dg-nonce": nonce,
      "x-dg-signature": signature,
    },
  });
}

const env = () => ({
  DELTAGRID_ACCESS_TEAM_DOMAIN: teamDomain,
  DELTAGRID_AGENT_ACCESS_AUD: audience,
  DELTAGRID_AGENT_HMAC_KEY: hmacKey,
  DELTAGRID_SYSTEM_DB: new NonceDb(),
});

test("agent requires both Access service identity and signed one-use request", async () => {
  const { keySet, token } = await fixture();
  const db = new NonceDb();
  const request = await signedRequest(token);
  const body = await request.clone().text();
  const identity = await verifyAgentRequest(request, body, {
    DELTAGRID_ACCESS_TEAM_DOMAIN: teamDomain,
    DELTAGRID_AGENT_ACCESS_AUD: audience,
    DELTAGRID_AGENT_HMAC_KEY: hmacKey,
    DELTAGRID_SYSTEM_DB: db,
  }, keySet);
  assert.equal(identity.commonName, "unit-agent.access");
  assert.equal(identity.agentId, "unit-agent");

  const replay = await signedRequest(token);
  const replayBody = await replay.clone().text();
  await assert.rejects(() => verifyAgentRequest(replay, replayBody, {
    DELTAGRID_ACCESS_TEAM_DOMAIN: teamDomain,
    DELTAGRID_AGENT_ACCESS_AUD: audience,
    DELTAGRID_AGENT_HMAC_KEY: hmacKey,
    DELTAGRID_SYSTEM_DB: db,
  }, keySet), /AGENT_NONCE_REPLAY/u);
});

test("agent accepts only a complete Access service application token", async () => {
  const wrongType = await fixture({ tokenType: "org" });
  let request = await signedRequest(wrongType.token, "2".repeat(32));
  let body = await request.clone().text();
  await assert.rejects(
    () => verifyAgentRequest(request, body, env(), wrongType.keySet),
    /AGENT_ACCESS_TOKEN_TYPE_INVALID/u,
  );

  const identitySubject = await fixture({ subject: "human-subject" });
  request = await signedRequest(identitySubject.token, "3".repeat(32));
  body = await request.clone().text();
  await assert.rejects(
    () => verifyAgentRequest(request, body, env(), identitySubject.keySet),
    /AGENT_SERVICE_SUBJECT_INVALID/u,
  );

  const noIssuedAt = await fixture({ omitIssuedAt: true });
  request = await signedRequest(noIssuedAt.token, "4".repeat(32));
  body = await request.clone().text();
  await assert.rejects(
    () => verifyAgentRequest(request, body, env(), noIssuedAt.keySet),
    /AGENT_ACCESS_ISSUED_AT_INVALID/u,
  );

  const noExpiration = await fixture({ omitExpiration: true });
  request = await signedRequest(noExpiration.token, "5".repeat(32));
  body = await request.clone().text();
  await assert.rejects(
    () => verifyAgentRequest(request, body, env(), noExpiration.keySet),
    /AGENT_ACCESS_EXPIRY_INVALID/u,
  );
});

test("agent rejects invalid request HMAC", async () => {
  const { keySet, token } = await fixture();
  const request = await signedRequest(token, "1".repeat(32), "f".repeat(64));
  const body = await request.clone().text();
  await assert.rejects(
    () => verifyAgentRequest(request, body, env(), keySet),
    /AGENT_SIGNATURE_INVALID/u,
  );
});
