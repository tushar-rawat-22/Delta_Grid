export const PROJECTION_SCHEMA_ID = "DELTAGRID_PUBLIC_PROJECTION_V1";
export const MANIFEST_SCHEMA_ID = "DELTAGRID_PUBLIC_PROJECTION_MANIFEST_V1";
export const PUBLIC_PROJECTION_CONTRACT_HASH =
  "bf288d8b6349c2843b5196fa1857ae9c464773bbcf7cad9d821785ea67dfb6e8";

export const SOURCE_CLASSES = [
  "REPOSITORY_IDENTITY",
  "CONTRACT_DERIVED",
  "PUBLIC_DOCUMENT_IDENTITY",
] as const;

export const AUTHORITY_BOOLEAN_FIELDS = [
  "m104_observation",
  "model_training_or_ml",
  "paper_trading",
  "live_trading",
  "exchange_account_access",
  "credential_access",
  "signed_exchange_requests",
  "order_placement",
  "portfolio_allocation",
  "capital_deployment",
  "self_authorization",
] as const;
