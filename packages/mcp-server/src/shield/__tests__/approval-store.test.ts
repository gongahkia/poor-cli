import { afterEach, describe, expect, it } from "vitest";
import { ShieldApprovalStore, resolveApprovalMode } from "../approval-store.js";
import { simulateSplunkSearchPolicy } from "../splunk-policy-simulator.js";

describe("Shield approval store", () => {
  const previousMode = process.env["SWEE_SHIELD_APPROVAL_MODE"];

  afterEach(() => {
    if (previousMode === undefined) {
      delete process.env["SWEE_SHIELD_APPROVAL_MODE"];
    } else {
      process.env["SWEE_SHIELD_APPROVAL_MODE"] = previousMode;
    }
  });

  it("deduplicates pending approval requests by request hash", () => {
    const store = new ShieldApprovalStore(":memory:");
    const request = { query: "index=security failed login", limit: 25 };
    const risk = simulateSplunkSearchPolicy(request);

    const first = store.create({ toolName: "splunk_search", request, risk });
    const second = store.create({ toolName: "splunk_search", request, risk });

    expect(second.approvalId).toBe(first.approvalId);
    expect(store.list({ status: "pending" })).toHaveLength(1);
  });

  it("records reviewer decisions and enforces request matching", () => {
    const store = new ShieldApprovalStore(":memory:");
    const request = { query: "index=security failed login", limit: 25 };
    const approval = store.create({
      toolName: "splunk_search",
      request,
      risk: simulateSplunkSearchPolicy(request),
    });

    const approved = store.decide({
      approvalId: approval.approvalId,
      decision: "approved",
      reviewer: "analyst",
      comment: "bounded follow-up",
    });

    expect(approved).toMatchObject({ status: "approved", reviewer: "analyst", comment: "bounded follow-up" });
    expect(store.requireApproved({ approvalId: approval.approvalId, toolName: "splunk_search", request }).approvalId)
      .toBe(approval.approvalId);
    expect(() => store.requireApproved({
      approvalId: approval.approvalId,
      toolName: "splunk_search",
      request: { query: "index=* error", limit: 25 },
    })).toThrow("does not match");
  });

  it("resolves queue mode only when explicitly enabled", () => {
    delete process.env["SWEE_SHIELD_APPROVAL_MODE"];
    expect(resolveApprovalMode()).toBe("off");
    process.env["SWEE_SHIELD_APPROVAL_MODE"] = "queue";
    expect(resolveApprovalMode()).toBe("queue");
  });
});
