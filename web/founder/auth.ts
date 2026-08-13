import {
  createRemoteJWKSet,
  jwtVerify,
  type JWTPayload,
  type JWTVerifyGetKey,
} from "jose";

export type FounderAccessEnv = {
  DELTAGRID_ACCESS_TEAM_DOMAIN?: string;
  DELTAGRID_ACCESS_AUD?: string;
  DELTAGRID_FOUNDER_EMAIL?: string;
};

export type FounderIdentity = {
  subject: string | null;
  email: string;
  expiresAt: number | null;
};

const ACCESS_HEADER = "cf-access-jwt-assertion";

export function validateFounderAccessEnv(env: FounderAccessEnv): {
  teamDomain: string;
  audience: string;
  founderEmail: string;
} {
  const teamDomain = env.DELTAGRID_ACCESS_TEAM_DOMAIN?.trim().replace(/\/$/u, "");
  const audience = env.DELTAGRID_ACCESS_AUD?.trim();
  const founderEmail = env.DELTAGRID_FOUNDER_EMAIL?.trim().toLowerCase();

  if (!teamDomain || !/^https:\/\/[A-Za-z0-9.-]+\.cloudflareaccess\.com$/u.test(teamDomain)) {
    throw new Error("FOUNDER_ACCESS_TEAM_DOMAIN_INVALID");
  }
  if (!audience || !/^[A-Za-z0-9_-]{16,256}$/u.test(audience)) {
    throw new Error("FOUNDER_ACCESS_AUDIENCE_INVALID");
  }
  if (!founderEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/u.test(founderEmail)) {
    throw new Error("FOUNDER_ACCESS_EMAIL_INVALID");
  }

  return { teamDomain, audience, founderEmail };
}

export async function verifyFounderToken(
  token: string,
  env: FounderAccessEnv,
  keySet?: JWTVerifyGetKey,
): Promise<FounderIdentity> {
  const config = validateFounderAccessEnv(env);
  const jwks = keySet ?? createRemoteJWKSet(new URL(`${config.teamDomain}/cdn-cgi/access/certs`));
  const { payload } = await jwtVerify(token, jwks, {
    issuer: config.teamDomain,
    audience: config.audience,
    algorithms: ["RS256"],
  });
  return validateFounderClaims(payload, config.founderEmail);
}

export async function verifyFounderRequest(
  request: Request,
  env: FounderAccessEnv,
  keySet?: JWTVerifyGetKey,
): Promise<FounderIdentity> {
  const token = request.headers.get(ACCESS_HEADER)?.trim();
  if (!token) throw new Error("FOUNDER_ACCESS_TOKEN_MISSING");
  return verifyFounderToken(token, env, keySet);
}

function validateFounderClaims(payload: JWTPayload, expectedEmail: string): FounderIdentity {
  const email = typeof payload.email === "string" ? payload.email.trim().toLowerCase() : "";
  if (!email || email !== expectedEmail) throw new Error("FOUNDER_ACCESS_IDENTITY_MISMATCH");

  return {
    subject: typeof payload.sub === "string" && payload.sub ? payload.sub : null,
    email,
    expiresAt: typeof payload.exp === "number" ? payload.exp : null,
  };
}
