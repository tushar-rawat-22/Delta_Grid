import { createHash } from "node:crypto";
import {
  AUTHORITY_BOOLEAN_FIELDS,
  MANIFEST_SCHEMA_ID,
  PROJECTION_SCHEMA_ID,
  PUBLIC_PROJECTION_CONTRACT_HASH,
  SOURCE_CLASSES,
} from "./constants.ts";
import { canonicalText } from "./canonical.ts";
import type {
  PublicProjection,
  PublicProjectionManifest,
  VerifiedProjectionPackage,
} from "./types.ts";

const HASH_RE = /^[0-9a-f]{64}$/u;
const COMMIT_RE = /^[0-9a-f]{40}$/u;

function exactObject(
  value: unknown,
  keys: readonly string[],
  reason: string,
): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(reason);
  }
  const actual = Object.keys(value as Record<string, unknown>).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new Error(reason);
  }
  return value as Record<string, unknown>;
}

function requireText(value: unknown, reason: string, maximum = 512): string {
  if (typeof value !== "string" || value.length === 0 || value.length > maximum) {
    throw new Error(reason);
  }
  return value;
}

function requireHash(value: unknown, reason: string): string {
  const text = requireText(value, reason, 64);
  if (!HASH_RE.test(text)) throw new Error(reason);
  return text;
}

function requireCommit(value: unknown, reason: string): string {
  const text = requireText(value, reason, 40);
  if (!COMMIT_RE.test(text)) throw new Error(reason);
  return text;
}

function requireCount(value: unknown, reason: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw new Error(reason);
  }
  return value;
}

function parseCanonical(raw: string, reason: string): unknown {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error(reason);
  }
  if (canonicalText(value) !== raw) throw new Error("NONCANONICAL_JSON");
  return value;
}

function validateProjection(value: unknown): PublicProjection {
  const projection = exactObject(
    value,
    [
      "schema_id",
      "source_classes",
      "core_identity",
      "authority",
      "contract_identities",
      "public_document_identities",
    ],
    "PROJECTION_SCHEMA_INVALID",
  );
  if (projection.schema_id !== PROJECTION_SCHEMA_ID) throw new Error("PROJECTION_SCHEMA_INVALID");

  if (
    !Array.isArray(projection.source_classes) ||
    projection.source_classes.length !== SOURCE_CLASSES.length ||
    projection.source_classes.some((item, index) => item !== SOURCE_CLASSES[index])
  ) {
    throw new Error("PROJECTION_SOURCE_CLASSES_INVALID");
  }

  const core = exactObject(projection.core_identity, ["repository_commit"], "PROJECTION_CORE_IDENTITY_INVALID");
  requireCommit(core.repository_commit, "PROJECTION_COMMIT_INVALID");

  const authorityKeys = [
    "maximum_verdict",
    "maximum_verdict_authority_effect",
    "production_statistical_adapter_count",
    "production_protected_evaluator_count",
    ...AUTHORITY_BOOLEAN_FIELDS,
  ];
  const authority = exactObject(projection.authority, authorityKeys, "PROJECTION_AUTHORITY_INVALID");
  requireText(authority.maximum_verdict, "PROJECTION_AUTHORITY_INVALID");
  if (authority.maximum_verdict_authority_effect !== "NONE") throw new Error("PROJECTION_AUTHORITY_INVALID");
  requireCount(authority.production_statistical_adapter_count, "PROJECTION_AUTHORITY_INVALID");
  requireCount(authority.production_protected_evaluator_count, "PROJECTION_AUTHORITY_INVALID");
  for (const field of AUTHORITY_BOOLEAN_FIELDS) {
    if (authority[field] !== false) throw new Error(`PROJECTION_AUTHORITY_INVALID:${field}`);
  }

  if (!Array.isArray(projection.contract_identities) || projection.contract_identities.length < 1 || projection.contract_identities.length > 16) {
    throw new Error("PROJECTION_CONTRACT_IDENTITIES_INVALID");
  }
  const contractPaths = new Set<string>();
  for (const item of projection.contract_identities) {
    const identity = exactObject(item, ["path", "contract_id", "contract_hash_sha256"], "PROJECTION_CONTRACT_IDENTITY_INVALID");
    const path = requireText(identity.path, "PROJECTION_CONTRACT_IDENTITY_INVALID");
    if (contractPaths.has(path)) throw new Error("PROJECTION_CONTRACT_IDENTITY_DUPLICATE");
    contractPaths.add(path);
    requireText(identity.contract_id, "PROJECTION_CONTRACT_IDENTITY_INVALID");
    requireHash(identity.contract_hash_sha256, "PROJECTION_CONTRACT_IDENTITY_INVALID");
  }

  if (!Array.isArray(projection.public_document_identities) || projection.public_document_identities.length < 1 || projection.public_document_identities.length > 32) {
    throw new Error("PROJECTION_DOCUMENT_IDENTITIES_INVALID");
  }
  const documentPaths = new Set<string>();
  for (const item of projection.public_document_identities) {
    const identity = exactObject(item, ["path", "sha256"], "PROJECTION_DOCUMENT_IDENTITY_INVALID");
    const path = requireText(identity.path, "PROJECTION_DOCUMENT_IDENTITY_INVALID");
    if (documentPaths.has(path)) throw new Error("PROJECTION_DOCUMENT_IDENTITY_DUPLICATE");
    documentPaths.add(path);
    requireHash(identity.sha256, "PROJECTION_DOCUMENT_IDENTITY_INVALID");
  }

  return projection as unknown as PublicProjection;
}

function validateManifest(value: unknown): PublicProjectionManifest {
  const manifest = exactObject(
    value,
    [
      "manifest_schema",
      "public_projection_contract_hash",
      "repository_commit",
      "projection_sha256",
    ],
    "MANIFEST_SCHEMA_INVALID",
  );
  if (manifest.manifest_schema !== MANIFEST_SCHEMA_ID) throw new Error("MANIFEST_SCHEMA_INVALID");
  if (manifest.public_projection_contract_hash !== PUBLIC_PROJECTION_CONTRACT_HASH) {
    throw new Error("MANIFEST_CONTRACT_HASH_MISMATCH");
  }
  requireCommit(manifest.repository_commit, "MANIFEST_COMMIT_INVALID");
  requireHash(manifest.projection_sha256, "MANIFEST_PROJECTION_HASH_INVALID");
  return manifest as unknown as PublicProjectionManifest;
}

export function verifyProjectionPackage(
  projectionRaw: string,
  manifestRaw: string,
  expectedRepositoryCommit?: string,
): VerifiedProjectionPackage {
  const projection = validateProjection(parseCanonical(projectionRaw, "PROJECTION_JSON_INVALID"));
  const manifest = validateManifest(parseCanonical(manifestRaw, "MANIFEST_JSON_INVALID"));
  const digest = createHash("sha256").update(projectionRaw, "utf8").digest("hex");

  if (digest !== manifest.projection_sha256) throw new Error("PROJECTION_HASH_MISMATCH");
  if (projection.core_identity.repository_commit !== manifest.repository_commit) {
    throw new Error("REPOSITORY_COMMIT_MISMATCH");
  }
  if (expectedRepositoryCommit && manifest.repository_commit !== expectedRepositoryCommit) {
    throw new Error("UNEXPECTED_REPOSITORY_COMMIT");
  }

  return { projection, manifest, projectionSha256: digest };
}
