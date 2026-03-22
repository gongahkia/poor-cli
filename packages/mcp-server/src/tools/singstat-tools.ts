import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { validateInput, SingStatSearchSchema, SingStatTableSchema, SingStatTimeseriesSchema, SingStatCompareSchema, SingStatBrowseSchema, formatResponse, resolveOutputFormat } from "@sg-apis/shared";
import type { ToolResult } from "@sg-apis/shared";
import { searchDatasets, getTableData, getTimeSeries } from "../apis/singstat/client.js";
import { compareIndicators } from "../apis/singstat/compare.js";
import { registerTool } from "./registry.js";

export const handleSingStatSearch = async (
  params: Readonly<{ keyword: string; limit?: number | undefined }>,
): Promise<ToolResult> => {
  const results = await searchDatasets(params.keyword, params.limit);
  const text = formatResponse(results as unknown as Record<string, unknown>[], "markdown");
  return { content: [{ type: "text", text }] };
};

export const registerSingStatTools = (server: McpServer): void => {
  registerTool(server, {
    name: "sg_singstat_search",
    description: "Search SingStat Table Builder for datasets matching a keyword. Returns dataset IDs, titles, and update frequency.",
    inputSchema: SingStatSearchSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      return handleSingStatSearch(validateInput(SingStatSearchSchema, input));
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
      const fmt = resolveOutputFormat(format);
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
      const fmt = resolveOutputFormat(format);
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
      const fmt = resolveOutputFormat(format);
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

      if (category === undefined) {
        // Return top-level categories
        const categories = [
          { category: "Economy & Prices", description: "GDP, CPI, trade, prices, national accounts" },
          { category: "Population & Land Area", description: "Population size, demographics, land use" },
          { category: "Labour & Productivity", description: "Employment, wages, labour force, productivity" },
          { category: "Society", description: "Education, health, housing, social indicators" },
          { category: "Transport", description: "Vehicle registrations, traffic, public transport" },
          { category: "Services", description: "Retail, food, accommodation, tourism" },
          { category: "Manufacturing & Construction", description: "Industrial production, construction" },
          { category: "Finance & Insurance", description: "Banking, insurance, capital markets" },
          { category: "International Trade", description: "Imports, exports, trade partners" },
        ];
        const text = formatResponse(categories as unknown as Record<string, unknown>[], "markdown");
        return { content: [{ type: "text", text: "## SingStat Categories\n\n" + text + "\n\nUse `sg_singstat_browse` with a category name to see its datasets." }] };
      }

      // Search within the specified category
      const results = await searchDatasets(category, 20);
      const grouped = results.reduce<Record<string, typeof results>>((acc, dataset) => {
        const topic = dataset.topic;
        if (acc[topic] === undefined) acc[topic] = [];
        acc[topic].push(dataset);
        return acc;
      }, {});

      const lines: string[] = [`## Datasets in "${category}"\n`];
      for (const [topic, datasets] of Object.entries(grouped)) {
        lines.push(`### ${topic}`);
        for (const ds of datasets) {
          lines.push(`- **${ds.id}**: ${ds.title} (${ds.frequency})`);
        }
        lines.push("");
      }

      return { content: [{ type: "text", text: lines.join("\n") }] };
    },
  });
};
