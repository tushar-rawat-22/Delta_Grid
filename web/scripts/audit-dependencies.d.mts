export type AuditPolicyInput = {
  fullAudit: unknown;
  runtimeAudit: unknown;
  lock: unknown;
  policy: unknown;
  today: string;
};

export type AcceptedAuditException = {
  advisory: string;
  package: string;
  version: string;
  expiresOn: string;
};

export function evaluateAudit(input: AuditPolicyInput): AcceptedAuditException[];
