import { createRemoteJWKSet, jwtVerify, type JWTVerifyGetKey } from "jose";
import { hmacHex, requestSigningMessage, safeEqualHex, sha256Hex } from "./crypto.ts";
import { registerAgentNonce, type D1DatabaseLike } from "./database.ts";

export type AgentAccessEnv = {
  DELTAGRID_ACCESS_TEAM_DOMAIN?: string;
  DELTAGRID_AGENT_ACCESS_AUD?: string;
  DELTAGRID_AGENT_HMAC_KEY?: string;
  DELTAGRID_SYSTEM_DB?: D1DatabaseLike;
};

export type AgentIdentity = { commonName: string; agentId: string };

export async function verifyAgentRequest(
  request: Request,
  body: string,
  env: AgentAccessEnv,
  keySet?: JWTVerifyGetKey,
): Promise<AgentIdentity> {
  const teamDomain = env.DELTAGRID_ACCESS_TEAM_DOMAIN?.trim().replace(/\/$/u, "");
  const audience = env.DELTAGRID_AGENT_ACCESS_AUD?.trim();
  const hmacKey = env.DELTAGRID_AGENT_HMAC_KEY;
  const db = env.DELTAGRID_SYSTEM_DB;
  if (!teamDomain || !/^https:\/\/[A-Za-z0-9.-]+\.cloudflareaccess\.com$/u.test(teamDomain)) {
    throw new Error("AGENT_TEAM_DOMAIN_INVALID");
  }
  if (!audience || !/^[A-Za-z0-9_-]{16,256}$/u.test(audience)) throw new Error("AGENT_AUDIENCE_INVALID");
  if (!hmacKey || hmacKey.length < 32) throw new Error("AGENT_HMAC_KEY_INVALID");
  if (!db) throw new Error("AGENT_DATABASE_MISSING");

  const accessToken = request.headers.get("cf-access-jwt-assertion")?.trim();
  if (!accessToken) throw new Error("AGENT_ACCESS_TOKEN_MISSING");
  const jwks = keySet ?? createRemoteJWKSet(new URL(`${teamDomain}/cdn-cgi/access/certs`));
  const { payload } = await jwtVerify(accessToken, jwks, {
    issuer: teamDomain,
    audience,
    algorithms: ["RS256"],
  });
  const commonName = typeof payload.common_name === "string" ? payload.common_name : "";
  if (!/^[A-Za-z0-9-]+\.access$/u.test(commonName)) throw new Error("AGENT_SERVICE_IDENTITY_INVALID");

  const agentId = request.headers.get("x-dg-agent-id")?.trim() ?? "";
  const timestamp = request.headers.get("x-dg-timestamp")?.trim() ?? "";
  const nonce = request.headers.get("x-dg-nonce")?.trim() ?? "";
  const suppliedSignature = request.headers.get("x-dg-signature")?.trim().toLowerCase() ?? "";
  if (!/^[a-z0-9][a-z0-9._-]{2,63}$/u.test(agentId)) throw new Error("AGENT_ID_INVALID");
  if (!/^\d{10}$/u.test(timestamp)) throw new Error("AGENT_TIMESTAMP_INVALID");
  if (!/^[0-9a-f]{32}$/u.test(nonce)) throw new Error("AGENT_NONCE_INVALID");
  const observedSeconds = Math.floor(Date.now() / 1000);
  if (Math.abs(observedSeconds - Number(timestamp)) > 120) throw new Error("AGENT_TIMESTAMP_STALE");

  const url = new URL(request.url);
  const bodyHash = await sha256Hex(body);
  const expected = await hmacHex(
    hmacKey,
    requestSigningMessage(request.method, url.pathname, timestamp, nonce, bodyHash),
  );
  if (!safeEqualHex(expected, suppliedSignature)) throw new Error("AGENT_SIGNATURE_INVALID");
  const registered = await registerAgentNonce(db, agentId, nonce, new Date().toISOString());
  if (!registered) throw new Error("AGENT_NONCE_REPLAY");
  return { commonName, agentId };
}
