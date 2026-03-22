import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { validateInput, QuerySchema, ApiError, resolveOutputFormat } from "@sg-apis/shared";
import type { ToolResult } from "@sg-apis/shared";
import { classifyIntent } from "../router/classifier.js";
import { planQuery } from "../router/planner.js";
import { aggregateResults, formatAggregated } from "../router/aggregator.js";
import type { StepResult } from "../router/aggregator.js";
import { ConversationContext } from "../router/context.js";
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

const context = new ConversationContext();

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
    const records = await masQuery(MasDataset.EXCHANGE_RATES, { limit: 10 });
    const normalized = records.map(normalizeMasRecord);
    if (params["currency"] !== undefined) {
      const key = `${(params["currency"] as string).toLowerCase()}_sgd`;
      return normalized.map((r) => ({ date: r.date, [key]: r[key] ?? "N/A" }));
    }
    return normalized;
  },
  sg_mas_interest_rates: async () => {
    const records = await masQuery(MasDataset.INTEREST_RATES_SORA, { limit: 10 });
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

export const registerQueryTool = (server: McpServer): void => {
  registerTool(server, {
    name: "sg_query",
    description:
      "Natural language query interface for Singapore government data. Automatically determines which APIs to query and how to combine results.",
    inputSchema: QuerySchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { query, format } = validateInput(QuerySchema, input);
      const fmt = resolveOutputFormat(format);

      const intent = classifyIntent(query);
      const plan = planQuery(query);

      // Execute plan steps — run parallel steps concurrently
      const stepPromises = plan.steps.map(async (step): Promise<StepResult> => {
        try {
          const data = await executeTool(step.tool, step.input as Record<string, unknown>);
          return { tool: step.tool, data, cached: false };
        } catch (error) {
          return {
            tool: step.tool,
            data: null,
            cached: false,
            error: new ApiError({
              apiName: step.tool,
              statusCode: 500,
              message: error instanceof Error ? error.message : String(error),
              retryable: false,
            }),
          };
        }
      });

      const results = plan.parallel
        ? await Promise.all(stepPromises)
        : await (async () => {
            const sequential: StepResult[] = [];
            for (const p of stepPromises) {
              sequential.push(await p);
            }
            return sequential;
          })();

      const aggregated = aggregateResults(results);
      context.update(query, plan, intent.extractedParams);

      const text = formatAggregated(aggregated, fmt);
      return { content: [{ type: "text", text }] };
    },
  });
};
