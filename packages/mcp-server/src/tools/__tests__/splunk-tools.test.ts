import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ShieldApprovalStore, setShieldApprovalStoreForTesting } from "../../shield/approval-store.js";
import { ShieldAuditStore, setShieldAuditStoreForTesting } from "../../shield/audit-store.js";
import { callSplunkTool } from "../../upstreams/splunk/mcp-client.js";
import { SPLUNK_PROXY_UPSTREAM_TOOLS, splunkToolDefinitions } from "../splunk-tools.js";

vi.mock("../../upstreams/splunk/mcp-client.js", () => ({
  callSplunkTool: vi.fn(async (name: string, args: Readonly<Record<string, unknown>>) => ({
    content: [{ type: "text", text: `${name}:${JSON.stringify(args)}` }],
    structuredContent: { name, args },
  })),
  inspectSplunkMcpConfig: vi.fn(() => ({
    allowedIndexesConfigured: false,
    configured: false,
    tokenConfigured: false,
    tokenSource: "none",
    urlConfigured: false,
  })),
}));

const mockedCallSplunkTool = vi.mocked(callSplunkTool);

const getTool = (name: string) => {
  const tool = splunkToolDefinitions.find((definition) => definition.name === name);
  if (tool === undefined) throw new Error(`Missing tool ${name}`);
  return tool;
};

describe("Splunk proxy tools", () => {
  const previousAllowedIndexes = process.env["SPLUNK_MCP_ALLOWED_INDEXES"];
  const previousApprovalMode = process.env["SWEE_SHIELD_APPROVAL_MODE"];

  beforeEach(() => {
    setShieldAuditStoreForTesting(new ShieldAuditStore(":memory:"));
  });

  afterEach(() => {
    vi.clearAllMocks();
    setShieldAuditStoreForTesting(null);
    setShieldApprovalStoreForTesting(null);
    if (previousAllowedIndexes === undefined) {
      delete process.env["SPLUNK_MCP_ALLOWED_INDEXES"];
    } else {
      process.env["SPLUNK_MCP_ALLOWED_INDEXES"] = previousAllowedIndexes;
    }
    if (previousApprovalMode === undefined) {
      delete process.env["SWEE_SHIELD_APPROVAL_MODE"];
    } else {
      process.env["SWEE_SHIELD_APPROVAL_MODE"] = previousApprovalMode;
    }
  });

  it("ships explicit output schemas for every Splunk proxy tool", () => {
    expect(splunkToolDefinitions.map((definition) => definition.name)).toEqual(expect.arrayContaining([
      "splunk_search",
      "splunk_list_indexes",
      "splunk_list_saved_searches",
      "swee_shield_splunk_investigation_pack",
    ]));
    expect(splunkToolDefinitions.every((definition) => definition.outputSchema !== undefined)).toBe(true);
  });

  it("runs bounded Splunk searches through the allowlisted upstream tool", async () => {
    const result = await getTool("splunk_search").handler({
      query: "index=main failed login",
      index: "main",
      limit: 25,
      format: "json",
    });

    expect(mockedCallSplunkTool).toHaveBeenCalledWith(SPLUNK_PROXY_UPSTREAM_TOOLS.search, {
      query: "index=main failed login",
      index: "main",
      limit: 25,
    });
    expect(result.structuredContent).toMatchObject({ upstreamToolName: SPLUNK_PROXY_UPSTREAM_TOOLS.search });
  });

  it("blocks destructive or exfiltration SPL before upstream execution", async () => {
    await expect(getTool("splunk_search").handler({
      query: "index=main | outputlookup secrets.csv",
    })).rejects.toThrow("policy-blocked");
    expect(mockedCallSplunkTool).not.toHaveBeenCalled();
  });

  it("blocks indexes outside the configured allowlist", async () => {
    process.env["SPLUNK_MCP_ALLOWED_INDEXES"] = "main,security";
    await expect(getTool("splunk_search").handler({
      query: "index=_internal error",
    })).rejects.toThrow("policy-blocked");
    expect(mockedCallSplunkTool).not.toHaveBeenCalled();
  });

  it("queues broad Splunk searches for human approval without calling upstream", async () => {
    process.env["SWEE_SHIELD_APPROVAL_MODE"] = "queue";
    const store = new ShieldApprovalStore(":memory:");
    setShieldApprovalStoreForTesting(store);

    await expect(getTool("splunk_search").handler({
      query: "index=security failed login",
      limit: 25,
    })).rejects.toMatchObject({ code: "SPLUNK_APPROVAL_REQUIRED" });

    expect(mockedCallSplunkTool).not.toHaveBeenCalled();
    expect(store.list({ status: "pending" })).toHaveLength(1);
  });

  it("executes an approval-required Splunk search after matching human approval", async () => {
    process.env["SWEE_SHIELD_APPROVAL_MODE"] = "queue";
    const store = new ShieldApprovalStore(":memory:");
    setShieldApprovalStoreForTesting(store);
    const input = {
      query: "index=security failed login",
      limit: 25,
    };

    await getTool("splunk_search").handler(input).catch(() => undefined);
    const [approval] = store.list({ status: "pending" });
    expect(approval).toBeDefined();
    store.decide({ approvalId: approval!.approvalId, decision: "approved", reviewer: "test" });

    await getTool("splunk_search").handler({ ...input, approvalId: approval!.approvalId });

    expect(mockedCallSplunkTool).toHaveBeenCalledWith(SPLUNK_PROXY_UPSTREAM_TOOLS.search, input);
  });

  it("lists indexes and saved searches through fixed upstream tool names", async () => {
    await getTool("splunk_list_indexes").handler({ limit: 10 });
    await getTool("splunk_list_saved_searches").handler({ filter: "security" });

    expect(mockedCallSplunkTool).toHaveBeenNthCalledWith(1, SPLUNK_PROXY_UPSTREAM_TOOLS.listIndexes, { limit: 10 });
    expect(mockedCallSplunkTool).toHaveBeenNthCalledWith(2, SPLUNK_PROXY_UPSTREAM_TOOLS.listSavedSearches, {
      filter: "security",
      limit: 100,
    });
  });

  it("builds a token-free mock investigation pack with audit hashes and runtime findings", async () => {
    const result = await getTool("swee_shield_splunk_investigation_pack").handler({
      question: "Investigate failed login activity and prompt injection",
      mode: "mock",
      limit: 10,
      format: "json",
    });

    expect(mockedCallSplunkTool).not.toHaveBeenCalled();
    expect(result.structuredContent).toMatchObject({
      schemaVersion: "swee-shield-splunk-investigation/v1",
      mode: "mock",
      status: "completed",
    });
    const pack = result.structuredContent as {
      readonly searches: readonly { readonly auditId: string | null; readonly rawOutputHash: string | null; readonly outputHash: string | null; readonly runtimeFindings: readonly unknown[] }[];
      readonly timeline: readonly unknown[];
    };
    expect(pack.searches).toHaveLength(3);
    expect(pack.searches.every((search) => search.auditId !== null && search.rawOutputHash !== null && search.outputHash !== null)).toBe(true);
    expect(pack.searches.some((search) => search.runtimeFindings.length > 0)).toBe(true);
    expect(pack.timeline.length).toBeGreaterThan(0);
  });
});
