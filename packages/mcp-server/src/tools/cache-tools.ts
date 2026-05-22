import { validateInput, CacheClearSchema, formatResponse } from "@swee-sg/shared";
import type { ToolResult } from "@swee-sg/shared";
import { getCache } from "../middleware/cache-middleware.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const cacheToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_cache_stats",
    description: "Show cache statistics including hit rate, entry count, and disk usage.",
    surface: "operational",
    inputSchema: {},
    handler: async (_input: unknown): Promise<ToolResult> => {
      const stats = getCache().stats();
      const hitRate = stats.hits + stats.misses > 0 ? ((stats.hits / (stats.hits + stats.misses)) * 100).toFixed(1) : "0";
      const record = { ...stats, hitRate: `${hitRate}%` };
      const text = formatResponse(record as unknown as Record<string, unknown>, "markdown");
      return {
        content: [{ type: "text", text }],
        structuredContent: {
          record,
        },
      };
    },
  },

  {
    name: "sg_cache_clear",
    description: "Clear cached data. Specify an API name to clear only that API's cache, or omit to clear all.",
    surface: "operational",
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
  },
];
