import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { validateInput, QuerySchema, ApiError, formatResponse, resolveOutputFormat } from "@sg-apis/shared";
import type { ToolResult } from "@sg-apis/shared";
import { planQuery } from "../router/planner.js";
import { registerTool } from "./registry.js";
import { handleDatagovSearch } from "./datagov-tools.js";
import {
  handleMasExchangeRates,
  handleMasFinancialStats,
  handleMasInterestRates,
} from "./mas-tools.js";
import { handleOneMapGeocode, handleOneMapPopulation } from "./onemap-tools.js";
import { handleSingStatSearch } from "./singstat-tools.js";
import { handleUraPlanningArea, handleUraPropertyTransactions } from "./ura-tools.js";

type ToolExecutor = (params: Readonly<Record<string, unknown>>) => Promise<ToolResult>;

const TOOL_EXECUTORS: Readonly<Record<string, ToolExecutor>> = {
  sg_singstat_search: async (params) =>
    handleSingStatSearch(params as Parameters<typeof handleSingStatSearch>[0]),
  sg_mas_exchange_rates: async (params) =>
    handleMasExchangeRates(params as Parameters<typeof handleMasExchangeRates>[0]),
  sg_mas_interest_rates: async (params) =>
    handleMasInterestRates(params as Parameters<typeof handleMasInterestRates>[0]),
  sg_mas_financial_stats: async (params) =>
    handleMasFinancialStats(params as Parameters<typeof handleMasFinancialStats>[0]),
  sg_onemap_geocode: async (params) =>
    handleOneMapGeocode(params as Parameters<typeof handleOneMapGeocode>[0]),
  sg_onemap_population: async (params) =>
    handleOneMapPopulation(params as Parameters<typeof handleOneMapPopulation>[0]),
  sg_ura_property_transactions: async (params) =>
    handleUraPropertyTransactions(params as Parameters<typeof handleUraPropertyTransactions>[0]),
  sg_ura_planning_area: async (params) =>
    handleUraPlanningArea(params as Parameters<typeof handleUraPlanningArea>[0]),
  sg_datagov_search: async (params) =>
    handleDatagovSearch(params as Parameters<typeof handleDatagovSearch>[0]),
};

export const executeQueryStep = async (
  toolName: string,
  input: Readonly<Record<string, unknown>>,
): Promise<ToolResult> => {
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
        const toolInput =
          format === undefined
            ? plan.step.input
            : { ...plan.step.input, format };
        return await executeQueryStep(plan.step.tool, toolInput as Record<string, unknown>);
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
