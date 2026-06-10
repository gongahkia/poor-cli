import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { ShieldAuditStore } from "../audit-store.js";

const decision = {
  mode: "enforce",
  decision: "allow",
  toolName: "swee_pulse_snapshot",
  riskLevel: "low",
  reasonCodes: ["default_allow"],
  message: "Swee Shield allowed swee_pulse_snapshot.",
} as const;

describe("ShieldAuditStore", () => {
  it("persists audit rows with redacted input, hashes, lookups, and replay metadata", () => {
    const store = new ShieldAuditStore(":memory:");
    const record = store.record({
      traceId: "trace-1",
      requestId: "request-1",
      toolName: "swee_pulse_snapshot",
      decision,
      status: "success",
      startedAt: "2026-05-22T07:00:00.000Z",
      finishedAt: "2026-05-22T07:00:01.000Z",
      durationMs: 1000,
      input: { area: "Bedok", apiKey: "secret" },
      output: { ok: true },
    });

    expect(record.sanitizedInput).toEqual({ area: "Bedok", apiKey: "[redacted]" });
    expect(record.inputHash).toHaveLength(64);
    expect(record.outputHash).toHaveLength(64);
    expect(store.get(record.auditId)?.auditId).toBe(record.auditId);
    expect(store.query({ traceId: "trace-1" })).toHaveLength(1);
    expect(store.query({ requestId: "request-1" })).toHaveLength(1);
    expect(store.query({ toolName: "swee_pulse_snapshot" })).toHaveLength(1);
    expect(store.getReplay(record.auditId)).toEqual({
      auditId: record.auditId,
      toolName: "swee_pulse_snapshot",
      sanitizedInput: { area: "Bedok", apiKey: "[redacted]" },
      decision,
      status: "success",
      outputHash: record.outputHash,
      rawOutputHash: null,
      runtimeFindings: [],
      durationMs: 1000,
    });
  });

  it("persists runtime findings and raw output hashes", () => {
    const store = new ShieldAuditStore(":memory:");
    const record = store.record({
      toolName: "splunk_search",
      decision: { ...decision, toolName: "splunk_search" },
      status: "success",
      startedAt: "2026-06-10T07:00:00.000Z",
      finishedAt: "2026-06-10T07:00:00.100Z",
      durationMs: 100,
      input: { query: "index=main" },
      rawOutput: { event: "token=abc1234567890" },
      output: { event: "token=[redacted]" },
      runtimeFindings: [{
        severity: "high",
        code: "SECRET_ASSIGNMENT_REDACTED",
        message: "Credential-shaped output was redacted before returning to the caller.",
        path: "$.event",
        action: "redacted",
        evidence: "credential-shaped assignment",
      }],
    });

    expect(record.rawOutputHash).toHaveLength(64);
    expect(record.outputHash).toHaveLength(64);
    expect(record.rawOutputHash).not.toBe(record.outputHash);
    expect(record.runtimeFindings).toHaveLength(1);
    expect(store.getReplay(record.auditId)?.runtimeFindings[0]?.code).toBe("SECRET_ASSIGNMENT_REDACTED");
  });

  it("reopens persisted audit rows from disk", () => {
    const tempDir = mkdtempSync(join(tmpdir(), "swee-shield-audit-"));
    const databasePath = join(tempDir, "shield-audit.db");

    try {
      const firstStore = new ShieldAuditStore(databasePath);
      const record = firstStore.record({
        toolName: "swee_pulse_snapshot",
        decision,
        status: "success",
        startedAt: "2026-05-22T07:00:00.000Z",
        finishedAt: "2026-05-22T07:00:00.250Z",
        durationMs: 250,
        input: { focus: "all" },
        output: { ok: true },
      });

      const secondStore = new ShieldAuditStore(databasePath);
      expect(secondStore.get(record.auditId)).toMatchObject({
        auditId: record.auditId,
        toolName: "swee_pulse_snapshot",
        durationMs: 250,
      });
      expect(secondStore.getReplay(record.auditId)?.outputHash).toBe(record.outputHash);
      expect(secondStore.getReplay(record.auditId)?.runtimeFindings).toEqual([]);
    } finally {
      rmSync(tempDir, { recursive: true, force: true });
    }
  });
});
