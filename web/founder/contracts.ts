export const AUTHORITY_STATE = "NONE" as const;
export const COMMAND_SCHEMA_VERSION = 1 as const;
export const COMMAND_TTL_SECONDS = 300;

export const ACTION_IDS = [
  "VERIFY_CORE_STATUS",
  "VERIFY_M100_JOURNAL",
  "CAPTURE_M100_ONCE",
  "EXPORT_M100_BACKUP",
  "VERIFY_M100_BACKUP",
  "REFRESH_PUBLIC_PROJECTION",
  "VERIFY_PUBLIC_PROJECTION",
  "RUN_APPROVED_TEST_PROFILE",
  "SHOW_CONTRACT_IDENTITIES",
  "SHOW_WORKTREE_STATUS",
] as const;

export type ActionId = (typeof ACTION_IDS)[number];
export type CommandStatus =
  | "REQUESTED"
  | "CLAIMED"
  | "EXECUTING"
  | "SUCCEEDED"
  | "FAILED"
  | "REJECTED"
  | "EXPIRED";

export type CommandRecord = {
  command_id: string;
  schema_version: number;
  requested_action_id: ActionId;
  founder_user_id: string;
  requested_at: string;
  expires_at: string;
  one_use_nonce: string;
  expected_core_commit: string;
  expected_authority_state: typeof AUTHORITY_STATE;
  parameter_json: string;
  parameter_hash: string;
  canonical_request_hash: string;
  integrity_proof: string;
  status: CommandStatus;
  claimed_at: string | null;
  claimed_by: string | null;
  executing_at: string | null;
  completed_at: string | null;
  terminal_code: string | null;
};

export function isActionId(value: string): value is ActionId {
  return (ACTION_IDS as readonly string[]).includes(value);
}

export function canonicalJson(value: unknown): string {
  return JSON.stringify(sortValue(value));
}

function sortValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, entry]) => [key, sortValue(entry)]),
    );
  }
  return value;
}
