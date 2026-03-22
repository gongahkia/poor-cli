import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { validateInput, QuerySchema, ApiError, formatResponse, resolveOutputFormat } from "@sg-apis/shared";
import type { ToolResult } from "@sg-apis/shared";
import { planQuery } from "../router/planner.js";
import { registerTool } from "./registry.js";

// API execution imports
import { searchDatasets as singstatSearch, getTableData, getTimeSeries } from "../apis/singstat/client.js";
import { query as masQuery } from "../apis/mas/client.js";
import { MasDataset } from "@sg-apis/shared";
import { normalizeMasRecord } from "../apis/mas/normalizer.js";
import { geocode, getPopulationData } from "../apis/onemap/client.js";
import { getPropertyTransactions } from "../apis/ura/client.js";
import { normalizeTransactions } from "../apis/ura/normalizer.js";
import { searchDatasets as datagovSearch } from "../apis/datagov/client.js";
import { lookupPlanningArea } from "./ura-tools.js";

type ToolExecutor = (params: Readonly<Record<string, unknown>>) => Promise<unknown>;

const TOOL_EXECUTORS: Readonly<Record<string, ToolExecutor>> = {
  sg_singstat_search: async (params) => {
    return singstatSearch((params["keyword"] as string) ?? "Singapore", params["limit"] as number);
  },
  sg_singstat_table: async (params) => {
    return getTableData(params["tableId"] as string);
  },
  sg_singstat_timeseries: async (params) => {
    return getTimeSeries(
      params["tableId"] as string,
      params["indicator"] as string,
      params["startYear"] as number,
      params["endYear"] as number,
    );
  },
  sg_mas_exchange_rates: async (params) => {
    const filters: Record<string, string> = {};
    if (typeof params["date"] === "string") filters["end_of_day"] = params["date"];
    const queryParams: { limit: number; filters?: Readonly<Record<string, string>> } = { limit: 100 };
    if (Object.keys(filters).length > 0) queryParams.filters = filters;
    const records = await masQuery(MasDataset.EXCHANGE_RATES, queryParams);
    const normalized = records.map(normalizeMasRecord);
    if (params["currency"] !== undefined) {
      const currency = (params["currency"] as string).toLowerCase();
      const key = `${currency}_sgd`;
      return normalized.map((r) => ({
        date: r.date,
        [key]: r[key] ?? r[`${currency}_sgd_100`] ?? "N/A",
      }));
    }
    return normalized;
  },
  sg_mas_interest_rates: async (params) => {
    const filters: Record<string, string> = {};
    if (typeof params["date"] === "string") filters["end_of_day"] = params["date"];
    const queryParams: { limit: number; filters?: Readonly<Record<string, string>> } = { limit: 100 };
    if (Object.keys(filters).length > 0) queryParams.filters = filters;
    const records = await masQuery(MasDataset.INTEREST_RATES_SORA, queryParams);
    return records.map(normalizeMasRecord);
  },
  sg_mas_financial_stats: async (params) => {
    const filters: Record<string, string> = {};
    if (typeof params["date"] === "string") filters["end_of_day"] = params["date"];
    const queryParams: { limit: number; filters?: Readonly<Record<string, string>> } = { limit: 100 };
    if (Object.keys(filters).length > 0) queryParams.filters = filters;
    const records = await masQuery(MasDataset.BANKING_STATS, queryParams);
    return records.map(normalizeMasRecord);
  },
  sg_onemap_geocode: async (params) => {
    return geocode((params["searchVal"] as string) ?? "");
  },
  sg_onemap_population: async (params) => {
    return getPopulationData((params["planningArea"] as string) ?? "");
  },
  sg_ura_property_transactions: async (params) => {
    const raw = await getPropertyTransactions(
      params["propertyType"] as string | undefined,
      params["area"] as string | undefined,
    );
    return normalizeTransactions(raw);
  },
  sg_ura_planning_area: async (params) => {
    return lookupPlanningArea({
      lat: params["lat"] as number | undefined,
      lng: params["lng"] as number | undefined,
      planningArea: params["planningArea"] as string | undefined,
    });
  },
  sg_datagov_search: async (params) => {
    return datagovSearch((params["keyword"] as string) ?? "Singapore");
  },
};

const executeTool = async (toolName: string, input: Readonly<Record<string, unknown>>): Promise<unknown> => {
  const executor = TOOL_EXECUTORS[toolName];
  if (executor === undefined) {
    throw new Error(`No executor for tool: ${toolName}`);
  }
  return executor(input);
};

const formatUnsupportedQuery = (
  reason: string,
  suggestion: string,
  format: ReturnType<typeof resolveOutputFormat>,
): string => {
  if (format === "json") {
    return formatResponse({ status: "unsupported", reason, suggestion }, format);
  }

  return [
    "**sg_query is experimental.**",
    reason,
    `Try this instead: ${suggestion}`,
  ].join("\n\n");
};

const formatQueryData = (
  toolName: string,
  data: unknown,
  format: ReturnType<typeof resolveOutputFormat>,
): string => {
  if (
    toolName === "sg_onemap_population"
    && data !== null
    && typeof data === "object"
    && "planningArea" in data
    && "year" in data
    && "data" in data
  ) {
    const payload = data as { planningArea: string; year: string; data: Record<string, unknown>[] };
    const body = formatResponse(payload.data, format);
    if (format === "json") {
      return formatResponse(payload, format);
    }
    return `**Source:** ${toolName}\n\n## ${payload.planningArea} (${payload.year})\n\n${body}`;
  }

  const body = formatResponse(data, format);
  if (format === "json") {
    return formatResponse({ source: toolName, data }, format);
  }
  return `**Source:** ${toolName}\n\n${body}`;
};

export const registerQueryTool = (server: McpServer): void => {
  registerTool(server, {
    name: "sg_query",
    description:
      "Experimental natural language router for Singapore data. Routes supported single-step requests to one direct tool and returns a limitation message for compound requests.",
    inputSchema: QuerySchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { query, format } = validateInput(QuerySchema, input);
      const fmt = resolveOutputFormat(format);
      const plan = planQuery(query);

      if (!plan.supported) {
        return {
          content: [{ type: "text", text: formatUnsupportedQuery(plan.reason, plan.suggestion, fmt) }],
        };
      }

      try {
        const data = await executeTool(plan.step.tool, plan.step.input as Record<string, unknown>);
        return {
          content: [{ type: "text", text: formatQueryData(plan.step.tool, data, fmt) }],
        };
      } catch (error) {
        throw new ApiError({
          apiName: plan.step.tool,
          statusCode: 500,
          message: error instanceof Error ? error.message : String(error),
          retryable: false,
        });
      }
    },
  });
};
