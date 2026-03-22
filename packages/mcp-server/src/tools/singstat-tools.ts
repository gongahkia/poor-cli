import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { validateInput, SingStatSearchSchema, SingStatTableSchema, SingStatTimeseriesSchema, SingStatCompareSchema, SingStatBrowseSchema, formatResponse } from "@sg-apis/shared";
import type { ToolResult, OutputFormat } from "@sg-apis/shared";
import { searchDatasets, getTableData, getTimeSeries } from "../apis/singstat/client.js";
import { compareIndicators } from "../apis/singstat/compare.js";
import { registerTool } from "./registry.js";

export const registerSingStatTools = (server: McpServer): void => {
  registerTool(server, {
    name: "sg_singstat_search",
    description: "Search SingStat Table Builder for datasets matching a keyword. Returns dataset IDs, titles, and update frequency.",
    inputSchema: SingStatSearchSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { keyword, limit } = validateInput(SingStatSearchSchema, input);
      const results = await searchDatasets(keyword, limit);
      const text = formatResponse(results as unknown as Record<string, unknown>[], "markdown");
      return { content: [{ type: "text", text }] };
    },
  });

  registerTool(server, {
    name: "sg_singstat_table",
    description: "Retrieve data from a specific SingStat table. Use sg_singstat_search first to find table IDs.",
    inputSchema: SingStatTableSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { tableId, timeFilter, variables, format } = validateInput(SingStatTableSchema, input);
      const opts: Record<string, unknown> = {};
      if (timeFilter !== undefined) opts["timeFilter"] = timeFilter;
      if (variables !== undefined) opts["variables"] = variables;
      const data = await getTableData(tableId, opts as { timeFilter?: string; variables?: readonly string[] });
      const fmt = (format ?? "markdown") as OutputFormat;
      const text = formatResponse(data.rows as unknown as Record<string, unknown>[], fmt);
      return { content: [{ type: "text", text: `## ${data.metadata.title}\n\n${text}` }] };
    },
  });

  registerTool(server, {
    name: "sg_singstat_timeseries",
    description: "Get time series data for a specific indicator from a SingStat table. Returns values for each period in the specified year range.",
    inputSchema: SingStatTimeseriesSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { tableId, indicator, startYear, endYear, format } = validateInput(SingStatTimeseriesSchema, input);
      const results = await getTimeSeries(tableId, indicator, startYear, endYear);
      const fmt = (format ?? "markdown") as OutputFormat;
      const text = formatResponse(results as unknown as Record<string, unknown>[], fmt);
      return { content: [{ type: "text", text }] };
    },
  });

  registerTool(server, {
    name: "sg_singstat_compare",
    description: "Compare multiple SingStat indicators side by side. Useful for correlating economic, demographic, or trade data.",
    inputSchema: SingStatCompareSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { queries, startYear, endYear, format } = validateInput(SingStatCompareSchema, input);
      const result = await compareIndicators(queries, startYear, endYear);
      const fmt = (format ?? "markdown") as OutputFormat;
      const rows = result.periods.map((period, i) => {
        const row: Record<string, unknown> = { period };
        for (const s of result.series) {
          row[s.label] = s.values[i];
        }
        return row;
      });
      const text = formatResponse(rows, fmt);
      return { content: [{ type: "text", text }] };
    },
  });

  registerTool(server, {
    name: "sg_singstat_browse",
    description: "Browse SingStat dataset categories. Call without arguments to see top-level categories, or provide a category to see its datasets.",
    inputSchema: SingStatBrowseSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { category } = validateInput(SingStatBrowseSchema, input);
      const keyword = category ?? "economy";
      const results = await searchDatasets(keyword, 20);
      const text = formatResponse(results as unknown as Record<string, unknown>[], "markdown");
      return { content: [{ type: "text", text }] };
    },
  });
};
