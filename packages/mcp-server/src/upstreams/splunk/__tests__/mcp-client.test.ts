import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { z } from "zod";
import { afterEach, describe, expect, it } from "vitest";
import {
  callSplunkTool,
  listSplunkTools,
  resolveSplunkMcpConfig,
  type SplunkMcpTransportFactory,
} from "../mcp-client.js";

const servers: McpServer[] = [];

afterEach(async () => {
  while (servers.length > 0) {
    await servers.pop()?.close().catch(() => undefined);
  }
});

const createMockTransportFactory = async (headers: string[]): Promise<SplunkMcpTransportFactory> => {
  const server = new McpServer({ name: "mock-splunk", version: "1.0.0" });
  server.registerTool("splunk_search", {
    description: "mock search",
    inputSchema: { query: z.string() },
  }, async (params) => ({
    content: [{ type: "text", text: `searched ${params.query}` }],
    structuredContent: { rows: [{ query: params.query }] },
  }));
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await server.connect(serverTransport);
  servers.push(server);
  return (config) => {
    headers.push(config.authorizationHeader);
    return clientTransport;
  };
};

describe("Splunk MCP client", () => {
  it("resolves env config before keystore fallback", () => {
    expect(resolveSplunkMcpConfig({
      env: {
        SPLUNK_MCP_URL: "https://splunk.example/services/mcp",
        SPLUNK_MCP_TOKEN: "env-token",
      },
      keystore: { getKey: () => "keystore-token" },
      timeoutMs: 1234,
    })).toEqual({
      url: "https://splunk.example/services/mcp",
      token: "env-token",
      timeoutMs: 1234,
    });
  });

  it("falls back to the splunk_mcp keystore key", () => {
    expect(resolveSplunkMcpConfig({
      env: {
        SPLUNK_MCP_URL: "https://splunk.example/services/mcp",
      },
      keystore: { getKey: (apiName) => apiName === "splunk_mcp" ? "stored-token" : null },
      timeoutMs: 1234,
    }).token).toBe("stored-token");
  });

  it("lists and calls tools over an injected MCP transport with bearer auth", async () => {
    const headers: string[] = [];
    const config = {
      url: "http://mock.local/mcp",
      token: "test-token",
      timeoutMs: 5000,
    };

    const tools = await listSplunkTools({ config, transportFactory: await createMockTransportFactory(headers) });
    expect(tools.tools.map((tool) => tool.name)).toContain("splunk_search");

    const result = await callSplunkTool("splunk_search", { query: "index=main" }, {
      config,
      transportFactory: await createMockTransportFactory(headers),
    });
    const content = (result as { readonly content?: unknown }).content;
    expect(Array.isArray(content) ? content[0] : null).toMatchObject({ type: "text", text: "searched index=main" });
    expect(headers).toEqual(["Bearer test-token", "Bearer test-token"]);
  });
});
