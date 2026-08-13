export type Provenance =
  | "VERIFIED_P1_PROJECTION"
  | "PUBLIC_DOCUMENT_DERIVED"
  | "DEMO_FIXTURE"
  | "NOT_PUBLICLY_PROJECTED";

export function assertProductionProvenance(
  provenance: Provenance,
  environment: string | undefined = process.env.NODE_ENV,
): void {
  if (environment === "production" && provenance === "DEMO_FIXTURE") {
    throw new Error("DEMO_FIXTURE_FORBIDDEN_IN_PRODUCTION");
  }
}
