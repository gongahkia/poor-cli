import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ShieldApprovalStore, setShieldApprovalStoreForTesting } from "../../shield/approval-store.js";
import { ShieldAuditStore, setShieldAuditStoreForTesting } from "../../shield/audit-store.js";
import { simulateSplunkSearchPolicy } from "../../shield/splunk-policy-simulator.js";
import { shieldToolDefinitions } from "../shield-tools.js";

const getTool = (name: string) => {
  const tool = shieldToolDefinitions.find((definition) => definition.name === name);
  if (tool === undefined) throw new Error(`Missing tool ${name}`);
  return tool;
};

describe("Shield tools", () => {
  let approvalStore: ShieldApprovalStore;
  let auditStore: ShieldAuditStore;

  beforeEach(() => {
    approvalStore = new ShieldApprovalStore(":memory:");
    auditStore = new ShieldAuditStore(":memory:");
    setShieldApprovalStoreForTesting(approvalStore);
    setShieldAuditStoreForTesting(auditStore);
  });

  afterEach(() => {
    setShieldApprovalStoreForTesting(null);
    setShieldAuditStoreForTesting(null);
  });

  it("ships output schemas for all Shield tools", () => {
    expect(shieldToolDefinitions.map((definition) => definition.name)).toEqual(expect.arrayContaining([
      "swee_shield_audit_lookup",
      "swee_shield_scan_tools",
      "swee_shield_approval_list",
      "swee_shield_approval_decide",
      "swee_shield_policy_simulate",
    ]));
    expect(shieldToolDefinitions.every((definition) => definition.outputSchema !== undefined)).toBe(true);
  });

  it("simulates policy and returns the red-team matrix", async () => {
    const result = await getTool("swee_shield_policy_simulate").handler({
      query: "index=* error",
      limit: 75,
    });

    expect(result.structuredContent).toMatchObject({
      simulation: { status: "approval_required" },
    });
    expect((result.structuredContent?.["redTeamMatrix"] as readonly unknown[]).length).toBeGreaterThan(3);
  });

  it("lists and decides approval records", async () => {
    const request = { query: "index=security failed login", limit: 25 };
    const approval = approvalStore.create({
      toolName: "splunk_search",
      request,
      risk: simulateSplunkSearchPolicy(request),
    });

    const list = await getTool("swee_shield_approval_list").handler({ status: "pending" });
    expect(list.structuredContent?.["records"]).toMatchObject([{ approvalId: approval.approvalId }]);

    const decided = await getTool("swee_shield_approval_decide").handler({
      approvalId: approval.approvalId,
      decision: "approved",
      reviewer: "test",
    });
    expect(decided.structuredContent?.["record"]).toMatchObject({ approvalId: approval.approvalId, status: "approved" });
  });

  it("looks up audit records and replay metadata", async () => {
    const audit = auditStore.record({
      toolName: "splunk_search",
      decision: {
        decision: "allow",
        mode: "enforce",
        reasonCodes: ["default_allow"],
        riskLevel: "low",
        toolName: "splunk_search",
        message: "allowed",
      },
      status: "success",
      startedAt: "2026-06-10T02:00:00.000Z",
      finishedAt: "2026-06-10T02:00:00.001Z",
      durationMs: 1,
      input: { query: "index=security failed login" },
      output: { ok: true },
      rawOutput: { ok: true },
    });

    const result = await getTool("swee_shield_audit_lookup").handler({ auditId: audit.auditId });

    expect(result.structuredContent?.["record"]).toMatchObject({ auditId: audit.auditId });
    expect(result.structuredContent?.["replay"]).toMatchObject({ auditId: audit.auditId, outputHash: audit.outputHash });
  });
});
