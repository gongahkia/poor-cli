import { afterEach, describe, expect, it, vi } from "vitest";
import { callSplunkTool } from "../../upstreams/splunk/mcp-client.js";
import { SPLUNK_PROXY_UPSTREAM_TOOLS, splunkToolDefinitions } from "../splunk-tools.js";

vi.mock("../../upstreams/splunk/mcp-client.js", () => ({
  callSplunkTool: vi.fn(async (name: string, args: Readonly<Record<string, unknown>>) => ({
    content: [{ type: "text", text: `${name}:${JSON.stringify(args)}` }],
    structuredContent: { name, args },
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

  afterEach(() => {
    vi.clearAllMocks();
    if (previousAllowedIndexes === undefined) {
      delete process.env["SPLUNK_MCP_ALLOWED_INDEXES"];
    } else {
      process.env["SPLUNK_MCP_ALLOWED_INDEXES"] = previousAllowedIndexes;
    }
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
    })).rejects.toThrow("blocked by the Swee Shield proxy");
    expect(mockedCallSplunkTool).not.toHaveBeenCalled();
  });

  it("blocks indexes outside the configured allowlist", async () => {
    process.env["SPLUNK_MCP_ALLOWED_INDEXES"] = "main,security";
    await expect(getTool("splunk_search").handler({
      query: "index=_internal error",
    })).rejects.toThrow("not allowlisted");
    expect(mockedCallSplunkTool).not.toHaveBeenCalled();
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
});
