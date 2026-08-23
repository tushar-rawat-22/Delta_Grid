import assert from "node:assert/strict";
import test from "node:test";
import {
  completeCommand,
  startCommand,
  type D1DatabaseLike,
  type D1ResultLike,
  type D1StatementLike,
  type ReceiptInput,
} from "../founder/database.ts";

function statement(options: {
  first?: () => Record<string, unknown> | null;
  run?: () => D1ResultLike<Record<string, unknown>>;
}): D1StatementLike {
  const value: D1StatementLike = {
    bind: () => value,
    first: async <T>() => (options.first ? options.first() as T | null : null),
    run: async <T>() => (options.run ? options.run() as D1ResultLike<T> : { success: true, results: [] }),
    all: async <T>() => ({ success: true, results: [] as T[] }),
  };
  return value;
}

test("same agent may retry a start whose successful response was lost", async () => {
  let prepareCalls = 0;
  const db: D1DatabaseLike = {
    prepare: () => {
      prepareCalls += 1;
      if (prepareCalls === 1) {
        return statement({ run: () => ({ success: true, results: [], meta: { changes: 0 } }) });
      }
      return statement({ first: () => ({ command_id: "command-1" }) });
    },
    batch: async <T>() => [] as D1ResultLike<T>[],
  };

  assert.equal(await startCommand(db, "command-1", "agent-1", "2026-08-23T17:00:00.000Z"), true);
  assert.equal(prepareCalls, 2);
});

test("start retry still fails closed when no matching execution exists", async () => {
  let prepareCalls = 0;
  const db: D1DatabaseLike = {
    prepare: () => {
      prepareCalls += 1;
      if (prepareCalls === 1) {
        return statement({ run: () => ({ success: true, results: [], meta: { changes: 0 } }) });
      }
      return statement({ first: () => null });
    },
    batch: async <T>() => [] as D1ResultLike<T>[],
  };

  assert.equal(await startCommand(db, "command-1", "other-agent", "2026-08-23T17:00:00.000Z"), false);
});

const receipt: ReceiptInput = {
  commandId: "command-1",
  agentId: "agent-1",
  status: "SUCCEEDED",
  terminalCode: "ACTION_COMPLETED",
  startedAt: "2026-08-23T17:00:00.000Z",
  completedAt: "2026-08-23T17:00:01.000Z",
  durationMs: 1000,
  outputSha256: "1".repeat(64),
  localReceiptSha256: "2".repeat(64),
};

function completedDb(localReceiptSha256 = receipt.localReceiptSha256): D1DatabaseLike {
  return {
    prepare: () => statement({ first: () => ({
      agent_id: receipt.agentId,
      terminal_status: receipt.status,
      terminal_code: receipt.terminalCode,
      started_at: receipt.startedAt,
      completed_at: receipt.completedAt,
      duration_ms: receipt.durationMs,
      output_sha256: receipt.outputSha256,
      local_receipt_sha256: localReceiptSha256,
    }) }),
    batch: async <T>() => {
      throw new Error(`unexpected duplicate batch for ${String(([] as T[]).length)}`);
    },
  };
}

test("exact terminal receipt retry is acknowledged without another write", async () => {
  assert.equal(await completeCommand(completedDb(), receipt), true);
});

test("conflicting terminal receipt replay is rejected", async () => {
  assert.equal(await completeCommand(completedDb("3".repeat(64)), receipt), false);
});
