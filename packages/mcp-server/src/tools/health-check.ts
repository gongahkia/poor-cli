import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { formatResponse, Keystore } from "@sg-apis/shared";
import type { ToolResult, HealthStatus } from "@sg-apis/shared";
import { registerTool } from "./registry.js";

export const registerHealthCheckTool = (server: McpServer): void => {
  registerTool(server, {
    name: "sg_health_check",
    description: "Check connectivity and API key status for all Singapore government APIs.",
    inputSchema: {},
    handler: async (_input: unknown): Promise<ToolResult> => {
      const keystore = new Keystore();
      const apis = [
        { name: "SingStat", url: "https://tablebuilder.singstat.gov.sg/api/table/resourceId?keyword=test&searchOption=all&limit=1", needsKey: false },
        { name: "MAS", url: "https://eservices.mas.gov.sg/api/action/datastore/search.json?resource_id=95932927-c8bc-4e7a-b484-68a66a24edfe&limit=1", needsKey: false },
        { name: "OneMap", url: "https://www.onemap.gov.sg/api/common/elastic/search?searchVal=Singapore&returnGeom=Y&getAddrDetails=Y&pageNum=1", needsKey: true },
        { name: "URA", url: "https://www.ura.gov.sg/uraDataService/insertNewToken.action", needsKey: true },
        { name: "data.gov.sg", url: "https://api-production.data.gov.sg/v2/public/api/datasets?page=0&resultSize=1", needsKey: false },
      ];

      const results = await Promise.allSettled(
        apis.map(async (api): Promise<HealthStatus> => {
          const keyConfigured = !api.needsKey || keystore.getKey(api.name.toLowerCase()) !== null;
          const start = Date.now();
          try {
            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), 5000);
            const response = await fetch(api.url, { signal: controller.signal });
            clearTimeout(timeout);
            return { api: api.name, keyConfigured, reachable: response.ok, latencyMs: Date.now() - start };
          } catch (error) {
            return { api: api.name, keyConfigured, reachable: false, latencyMs: Date.now() - start, error: error instanceof Error ? error.message : String(error) };
          }
        }),
      );

      const statuses = results.map((r) => r.status === "fulfilled" ? r.value : { api: "Unknown", keyConfigured: false, reachable: false, latencyMs: 0, error: "Check failed" });
      keystore.close();
      const text = formatResponse(statuses as unknown as Record<string, unknown>[], "markdown");
      return { content: [{ type: "text", text }] };
    },
  });
};
