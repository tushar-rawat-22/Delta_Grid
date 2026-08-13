import assert from "node:assert/strict";
import test from "node:test";
import {
  SignJWT,
  createLocalJWKSet,
  exportJWK,
  generateKeyPair,
  type JSONWebKeySet,
} from "jose";
import { validateFounderAccessEnv, verifyFounderToken } from "../founder/auth.ts";

const teamDomain = "https://deltagrid-unit.cloudflareaccess.com";
const audience = "deltagridFounderAccessAudience123456";
const founderEmail = "founder@example.test";
const env = {
  DELTAGRID_ACCESS_TEAM_DOMAIN: teamDomain,
  DELTAGRID_ACCESS_AUD: audience,
  DELTAGRID_FOUNDER_EMAIL: founderEmail,
};

async function keys() {
  const pair = await generateKeyPair("RS256");
  const jwk = await exportJWK(pair.publicKey);
  jwk.kid = "unit-key";
  jwk.alg = "RS256";
  return {
    privateKey: pair.privateKey,
    keySet: createLocalJWKSet({ keys: [jwk] } as JSONWebKeySet),
  };
}

async function signedToken(
  privateKey: CryptoKey,
  overrides: { email?: string; issuer?: string; audience?: string; expiresAt?: number } = {},
) {
  const now = Math.floor(Date.now() / 1000);
  return new SignJWT({ email: overrides.email ?? founderEmail })
    .setProtectedHeader({ alg: "RS256", kid: "unit-key" })
    .setIssuer(overrides.issuer ?? teamDomain)
    .setAudience(overrides.audience ?? audience)
    .setSubject("founder-subject")
    .setIssuedAt(now)
    .setExpirationTime(overrides.expiresAt ?? now + 300)
    .sign(privateKey);
}

test("valid exact founder Access token is accepted", async () => {
  const { privateKey, keySet } = await keys();
  const token = await signedToken(privateKey);
  const identity = await verifyFounderToken(token, env, keySet);
  assert.equal(identity.email, founderEmail);
  assert.equal(identity.subject, "founder-subject");
});

test("wrong founder email is rejected", async () => {
  const { privateKey, keySet } = await keys();
  const token = await signedToken(privateKey, { email: "attacker@example.test" });
  await assert.rejects(() => verifyFounderToken(token, env, keySet), /FOUNDER_ACCESS_IDENTITY_MISMATCH/u);
});

test("wrong issuer, audience and expired tokens are rejected", async () => {
  const { privateKey, keySet } = await keys();

  const wrongIssuer = await signedToken(privateKey, { issuer: "https://wrong.cloudflareaccess.com" });
  await assert.rejects(() => verifyFounderToken(wrongIssuer, env, keySet));

  const wrongAudience = await signedToken(privateKey, { audience: "wrongAudienceValue123456" });
  await assert.rejects(() => verifyFounderToken(wrongAudience, env, keySet));

  const expired = await signedToken(privateKey, { expiresAt: Math.floor(Date.now() / 1000) - 10 });
  await assert.rejects(() => verifyFounderToken(expired, env, keySet));
});

test("wrong signature is rejected", async () => {
  const trusted = await keys();
  const untrusted = await keys();
  const token = await signedToken(untrusted.privateKey);
  await assert.rejects(() => verifyFounderToken(token, env, trusted.keySet));
});

test("missing or malformed founder configuration fails closed", () => {
  assert.throws(() => validateFounderAccessEnv({}), /FOUNDER_ACCESS_TEAM_DOMAIN_INVALID/u);
  assert.throws(
    () => validateFounderAccessEnv({ ...env, DELTAGRID_ACCESS_TEAM_DOMAIN: "http://not-secure.cloudflareaccess.com" }),
    /FOUNDER_ACCESS_TEAM_DOMAIN_INVALID/u,
  );
  assert.throws(
    () => validateFounderAccessEnv({ ...env, DELTAGRID_ACCESS_AUD: "short" }),
    /FOUNDER_ACCESS_AUDIENCE_INVALID/u,
  );
  assert.throws(
    () => validateFounderAccessEnv({ ...env, DELTAGRID_FOUNDER_EMAIL: "not-an-email" }),
    /FOUNDER_ACCESS_EMAIL_INVALID/u,
  );
});
