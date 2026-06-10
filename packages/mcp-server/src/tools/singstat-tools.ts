import { validateInput, SingStatSearchSchema, SingStatTableSchema, SingStatTimeseriesSchema, SingStatCompareSchema, SingStatBrowseSchema, formatResponse, resolveOutputFormat } from "@swee-sg/shared";
import type { ToolResult } from "@swee-sg/shared";
import { searchDatasets, getTableData, getTimeSeries } from "../apis/singstat/client.js";
import { compareIndicators } from "../apis/singstat/compare.js";
import { buildArtifactResult, shouldUseArtifact } from "./artifacts.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleSingStatSearch = async (
  params: Readonly<{ keyword: string; limit?: number | undefined }>,
): Promise<ToolResult> => {
  const results = await searchDatasets(params.keyword, params.limit);
  const text = formatResponse(results as unknown as Record<string, unknown>[], "markdown");
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: results,
    },
  };
};

export const handleSingStatTable = async (
  params: Readonly<{
    tableId: string;
    timeFilter?: string | undefined;
    variables?: readonly string[] | undefined;
    format?: "json" | "markdown" | "csv" | "geojson" | undefined;
  }>,
): Promise<ToolResult> => {
  const opts: Record<string, unknown> = {};
  if (params.timeFilter !== undefined) {
    opts["timeFilter"] = params.timeFilter;
  }
  if (params.variables !== undefined) {
    opts["variables"] = params.variables;
  }

  const data = await getTableData(params.tableId, opts as { timeFilter?: string; variables?: readonly string[] });
  const fmt = resolveOutputFormat(params.format);
  const text = formatResponse(data.rows as unknown as Record<string, unknown>[], fmt);

  if (shouldUseArtifact(text, data.rows.length)) {
    return buildArtifactResult({
      toolName: "sg_singstat_table",
      input: {
        tableId: params.tableId,
        ...(params.timeFilter === undefined ? {} : { timeFilter: params.timeFilter }),
        ...(params.variables === undefined ? {} : { variables: params.variables }),
        format: fmt,
      },
      kind: "table",
      title: `SingStat table ${params.tableId}`,
      description: "Large SingStat table result promoted to a transient artifact resource.",
      fullText: `## ${data.metadata.title}\n\n${text}`,
      payload: {
        metadata: data.metadata,
        records: data.rows,
      },
      preview: {
        metadata: data.metadata,
        records: data.rows.slice(0, 10),
        returned: data.rows.length,
      },
      structuredContentBase: {
        metadata: data.metadata,
      },
    });
  }

  return {
    content: [{ type: "text", text: `## ${data.metadata.title}\n\n${text}` }],
    structuredContent: {
      metadata: data.metadata,
      records: data.rows,
    },
  };
};

export const handleSingStatTimeseries = async (
  params: Readonly<{
    tableId: string;
    indicator: string;
    startYear: number;
    endYear: number;
    format?: "json" | "markdown" | "csv" | "geojson" | undefined;
  }>,
): Promise<ToolResult> => {
  const results = await getTimeSeries(params.tableId, params.indicator, params.startYear, params.endYear);
  const fmt = resolveOutputFormat(params.format);
  const text = formatResponse(results as unknown as Record<string, unknown>[], fmt);

  if (shouldUseArtifact(text, results.length)) {
    return buildArtifactResult({
      toolName: "sg_singstat_timeseries",
      input: {
        tableId: params.tableId,
        indicator: params.indicator,
        startYear: params.startYear,
        endYear: params.endYear,
        format: fmt,
      },
      kind: "timeseries",
      title: `SingStat time series ${params.tableId}:${params.indicator}`,
      description: "Large SingStat time-series result promoted to a transient artifact resource.",
      fullText: text,
      payload: {
        tableId: params.tableId,
        indicator: params.indicator,
        startYear: params.startYear,
        endYear: params.endYear,
        records: results,
      },
      preview: {
        tableId: params.tableId,
        indicator: params.indicator,
        records: results.slice(0, 10),
        returned: results.length,
      },
      structuredContentBase: {
        tableId: params.tableId,
        indicator: params.indicator,
      },
    });
  }

  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: results,
    },
  };
};

export const handleSingStatBrowse = async (
  params: Readonly<{ category?: string | undefined }>,
): Promise<ToolResult> => {
  if (params.category === undefined) {
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
    return {
      content: [{ type: "text", text: "## SingStat Categories\n\n" + text + "\n\nUse `sg_singstat_browse` with a category name to see its datasets." }],
      structuredContent: {
        records: categories,
      },
    };
  }

  const results = await searchDatasets(params.category, 20);
  const grouped = results.reduce<Record<string, typeof results>>((acc, dataset) => {
    const topic = dataset.topic;
    if (acc[topic] === undefined) {
      acc[topic] = [];
    }
    acc[topic].push(dataset);
    return acc;
  }, {});

  const lines: string[] = [`## Datasets in "${params.category}"\n`];
  for (const [topic, datasets] of Object.entries(grouped)) {
    lines.push(`### ${topic}`);
    for (const ds of datasets) {
      lines.push(`- **${ds.id}**: ${ds.title} (${ds.frequency})`);
    }
    lines.push("");
  }

  return {
    content: [{ type: "text", text: lines.join("\n") }],
    structuredContent: {
      category: params.category,
      records: results,
    },
  };
};

export const singstatToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_singstat_search",
    description: "Search SingStat Table Builder for datasets matching a keyword. Returns dataset IDs, titles, and update frequency.",
    surface: "canonical",
    inputSchema: SingStatSearchSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      return handleSingStatSearch(validateInput(SingStatSearchSchema, input));
    },
  },

  {
    name: "sg_singstat_table",
    description: "Retrieve data from a specific SingStat table. Use sg_singstat_search first to find table IDs.",
    surface: "canonical",
    inputSchema: SingStatTableSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      return handleSingStatTable(validateInput(SingStatTableSchema, input));
    },
  },

  {
    name: "sg_singstat_timeseries",
    description: "Get time series data for a specific indicator from a SingStat table. Returns values for each period in the specified year range.",
    surface: "canonical",
    inputSchema: SingStatTimeseriesSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      return handleSingStatTimeseries(validateInput(SingStatTimeseriesSchema, input));
    },
  },

  {
    name: "sg_singstat_compare",
    description: "Compare multiple SingStat indicators side by side. Useful for correlating economic, demographic, or trade data.",
    surface: "canonical",
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

      if (shouldUseArtifact(text, rows.length)) {
        return buildArtifactResult({
          toolName: "sg_singstat_compare",
          input: {
            queries,
            startYear,
            endYear,
            format: fmt,
          },
          kind: "compare",
          title: "SingStat indicator comparison",
          description: "Large SingStat comparison result promoted to a transient artifact resource.",
          fullText: text,
          payload: {
            series: result.series,
            periods: result.periods,
            records: rows,
          },
          preview: {
            series: result.series.map((series) => ({ label: series.label })),
            periods: result.periods.slice(0, 10),
            records: rows.slice(0, 10),
          },
          structuredContentBase: {
            series: result.series,
            periods: result.periods,
          },
        });
      }

      return {
        content: [{ type: "text", text }],
        structuredContent: {
          records: rows,
        },
      };
    },
  },

  {
    name: "sg_singstat_browse",
    description: "Browse SingStat dataset categories. Call without arguments to see top-level categories, or provide a category to see its datasets.",
    surface: "canonical",
    inputSchema: SingStatBrowseSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      return handleSingStatBrowse(validateInput(SingStatBrowseSchema, input));
    },
  },
];
