import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { validateInput, CacheClearSchema, formatResponse } from "@sg-apis/shared";
import type { ToolResult } from "@sg-apis/shared";
import { getCache } from "../middleware/cache-middleware.js";
import { registerTool } from "./registry.js";

export const registerCacheTools = (server: McpServer): void => {
  registerTool(server, {
    name: "sg_cache_stats",
    description: "Show cache statistics including hit rate, entry count, and disk usage.",
    inputSchema: {},
    handler: async (_input: unknown): Promise<ToolResult> => {
      const stats = getCache().stats();
      const hitRate = stats.hits + stats.misses > 0 ? ((stats.hits / (stats.hits + stats.misses)) * 100).toFixed(1) : "0";
      const text = formatResponse({ ...stats, hitRate: `${hitRate}%` } as unknown as Record<string, unknown>, "markdown");
      return { content: [{ type: "text", text }] };
    },
  });

  registerTool(server, {
    name: "sg_cache_clear",
    description: "Clear cached data. Specify an API name to clear only that API's cache, or omit to clear all.",
    inputSchema: CacheClearSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { api } = validateInput(CacheClearSchema, input);
      const cache = getCache();
      if (api !== undefined) {
        const deleted = cache.invalidate(`${api}:%`);
        return { content: [{ type: "text", text: `Cleared ${deleted} cached entries for ${api}.` }] };
      }
      cache.clear();
      return { content: [{ type: "text", text: "All cache cleared." }] };
    },
  });
};
