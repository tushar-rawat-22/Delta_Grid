import type { AUTHORITY_BOOLEAN_FIELDS, SOURCE_CLASSES } from "./constants";

export type ProjectionSourceClass = (typeof SOURCE_CLASSES)[number];
export type AuthorityBooleanField = (typeof AUTHORITY_BOOLEAN_FIELDS)[number];

export type ProjectionAuthority = {
  maximum_verdict: string;
  maximum_verdict_authority_effect: "NONE";
  production_statistical_adapter_count: number;
  production_protected_evaluator_count: number;
} & Record<AuthorityBooleanField, false>;

export type ContractIdentity = {
  path: string;
  contract_id: string;
  contract_hash_sha256: string;
};

export type PublicDocumentIdentity = {
  path: string;
  sha256: string;
};

export type PublicProjection = {
  schema_id: "DELTAGRID_PUBLIC_PROJECTION_V1";
  source_classes: ProjectionSourceClass[];
  core_identity: {
    repository_commit: string;
  };
  authority: ProjectionAuthority;
  contract_identities: ContractIdentity[];
  public_document_identities: PublicDocumentIdentity[];
};

export type PublicProjectionManifest = {
  manifest_schema: "DELTAGRID_PUBLIC_PROJECTION_MANIFEST_V1";
  public_projection_contract_hash: string;
  repository_commit: string;
  projection_sha256: string;
};

export type VerifiedProjectionPackage = {
  projection: PublicProjection;
  manifest: PublicProjectionManifest;
  projectionSha256: string;
};
