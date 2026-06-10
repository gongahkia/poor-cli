import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  clearToolInvocationAuditStoreForTests,
  getToolInvocationAuditByTraceId,
  getToolInvocationAuditStats,
  listRecentToolInvocationAudits,
  recordToolInvocationAudit,
} from "../request-audit.js";

const ORIG_MAX_ENTRIES = process.env["SG_APIS_AUDIT_MAX_ENTRIES"];
const ORIG_RETENTION_SEC = process.env["SG_APIS_AUDIT_RETENTION_SEC"];

const record = (params: Readonly<{ traceId: string; requestId: string; finishedAt: string }>) => {
  recordToolInvocationAudit({
    traceId: params.traceId,
    requestId: params.requestId,
    tool: "sg_config_get",
    status: "success",
    startedAt: params.finishedAt,
    finishedAt: params.finishedAt,
    durationMs: 1,
  });
};

describe("request audit store", () => {
  beforeEach(() => {
    clearToolInvocationAuditStoreForTests();
    delete process.env["SG_APIS_AUDIT_MAX_ENTRIES"];
    delete process.env["SG_APIS_AUDIT_RETENTION_SEC"];
  });

  afterEach(() => {
    clearToolInvocationAuditStoreForTests();
    if (ORIG_MAX_ENTRIES === undefined) {
      delete process.env["SG_APIS_AUDIT_MAX_ENTRIES"];
    } else {
      process.env["SG_APIS_AUDIT_MAX_ENTRIES"] = ORIG_MAX_ENTRIES;
    }
    if (ORIG_RETENTION_SEC === undefined) {
      delete process.env["SG_APIS_AUDIT_RETENTION_SEC"];
    } else {
      process.env["SG_APIS_AUDIT_RETENTION_SEC"] = ORIG_RETENTION_SEC;
    }
  });

  it("enforces configured max entries", () => {
    process.env["SG_APIS_AUDIT_MAX_ENTRIES"] = "100";
    const now = new Date().toISOString();
    for (let index = 1; index <= 140; index++) {
      const suffix = index.toString().padStart(12, "0");
      record({
        traceId: `10000000-0000-4000-8000-${suffix}`,
        requestId: `20000000-0000-4000-8000-${suffix}`,
        finishedAt: now,
      });
    }

    const recent = listRecentToolInvocationAudits(500);
    expect(recent).toHaveLength(100);
    const stats = getToolInvocationAuditStats();
    expect(stats.recordCount).toBe(100);
    expect(stats.maxEntries).toBe(100);
  });

  it("evicts stale records past configured retention window", () => {
    process.env["SG_APIS_AUDIT_RETENTION_SEC"] = "300";
    const expired = new Date(Date.now() - (10 * 60 * 1000)).toISOString();
    const fresh = new Date().toISOString();

    record({
      traceId: "31111111-1111-4111-8111-111111111111",
      requestId: "32222222-2222-4222-8222-222222222222",
      finishedAt: expired,
    });
    record({
      traceId: "41111111-1111-4111-8111-111111111111",
      requestId: "42222222-2222-4222-8222-222222222222",
      finishedAt: fresh,
    });

    const freshRecord = getToolInvocationAuditByTraceId("41111111-1111-4111-8111-111111111111");
    const expiredRecord = getToolInvocationAuditByTraceId("31111111-1111-4111-8111-111111111111");

    expect(freshRecord).not.toBeNull();
    expect(expiredRecord).toBeNull();
    const stats = getToolInvocationAuditStats();
    expect(stats.recordCount).toBe(1);
    expect(stats.retentionSeconds).toBe(300);
  });
});
