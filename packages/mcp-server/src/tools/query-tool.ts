import { formatResponse, QuerySchema, resolveOutputFormat, validateInput } from "@sg-apis/shared";
import type { OutputFormat, ToolErrorPayload, ToolResult } from "@sg-apis/shared";
import { planQuery } from "../router/planner.js";
import type { QueryExecutionContext, QueryPlan, QueryStep } from "../router/planner.js";
import { toToolErrorPayload } from "../middleware/error-handler.js";
import { handleDatagovBrowse, handleDatagovGet, handleDatagovSearch } from "./datagov-tools.js";
import { handleHdbRentalPrices, handleHdbResalePrices } from "./hdb-tools.js";
import { handleLtaBusArrivals, handleLtaTrafficIncidents, handleLtaTrainAlerts } from "./lta-tools.js";
import {
  handleMasExchangeRates,
  handleMasFinancialStats,
  handleMasInterestRates,
} from "./mas-tools.js";
import { handleNeaAirQuality, handleNeaForecast2Hr, handleNeaRainfall } from "./nea-tools.js";
import { handleOneMapGeocode, handleOneMapPopulation } from "./onemap-tools.js";
import { handleSingStatSearch } from "./singstat-tools.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";
import { handleUraPlanningArea, handleUraPropertyTransactions } from "./ura-tools.js";

type ToolExecutor = (params: Readonly<Record<string, unknown>>) => Promise<ToolResult>;

type QueryStepStatus = "planned" | "completed" | "failed";

type ExecutedQueryStep = {
  readonly id: string;
  readonly purpose: string;
  readonly tool: string;
  readonly status: QueryStepStatus;
  readonly input: Readonly<Record<string, unknown>>;
  readonly dependsOn?: readonly string[];
  readonly outputText?: string;
  readonly structuredOutput?: Readonly<Record<string, unknown>>;
  readonly error?: ToolErrorPayload;
};

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
  sg_datagov_get: async (params) =>
    handleDatagovGet(params as Parameters<typeof handleDatagovGet>[0]),
  sg_datagov_browse: async (params) =>
    handleDatagovBrowse(params as Parameters<typeof handleDatagovBrowse>[0]),
  sg_lta_bus_arrivals: async (params) =>
    handleLtaBusArrivals(params as Parameters<typeof handleLtaBusArrivals>[0]),
  sg_lta_train_alerts: async (params) =>
    handleLtaTrainAlerts(params as Parameters<typeof handleLtaTrainAlerts>[0]),
  sg_lta_traffic_incidents: async (params) =>
    handleLtaTrafficIncidents(params as Parameters<typeof handleLtaTrafficIncidents>[0]),
  sg_nea_forecast_2hr: async (params) =>
    handleNeaForecast2Hr(params as Parameters<typeof handleNeaForecast2Hr>[0]),
  sg_nea_air_quality: async (params) =>
    handleNeaAirQuality(params as Parameters<typeof handleNeaAirQuality>[0]),
  sg_nea_rainfall: async (params) =>
    handleNeaRainfall(params as Parameters<typeof handleNeaRainfall>[0]),
  sg_hdb_resale_prices: async (params) =>
    handleHdbResalePrices(params as Parameters<typeof handleHdbResalePrices>[0]),
  sg_hdb_rental_prices: async (params) =>
    handleHdbRentalPrices(params as Parameters<typeof handleHdbRentalPrices>[0]),
};

const FORMAT_CAPABLE_TOOLS = new Set([
  "sg_mas_exchange_rates",
  "sg_mas_interest_rates",
  "sg_mas_financial_stats",
  "sg_onemap_population",
  "sg_ura_property_transactions",
  "sg_datagov_get",
  "sg_lta_bus_arrivals",
  "sg_lta_train_alerts",
  "sg_lta_traffic_incidents",
  "sg_nea_forecast_2hr",
  "sg_nea_air_quality",
  "sg_nea_rainfall",
  "sg_hdb_resale_prices",
  "sg_hdb_rental_prices",
]);

const getTextContent = (result: ToolResult): string => {
  return result.content
    .filter((item) => item.type === "text")
    .map((item) => item.text)
    .join("\n\n");
};

const getResultErrorPayload = (result: ToolResult, tool: string): ToolErrorPayload => {
  const payload = result.structuredContent?.["error"];
  if (
    typeof payload === "object"
    && payload !== null
    && typeof (payload as Record<string, unknown>)["code"] === "string"
  ) {
    return payload as ToolErrorPayload;
  }

  return {
    source: tool,
    tool,
    code: "TOOL_RESULT_ERROR",
    retryable: false,
    message: getTextContent(result) || `${tool} returned an error result.`,
    suggestedAction: `Call ${tool} directly to inspect and correct the failing input.`,
  };
};

const withRequestedFormat = (
  step: QueryStep,
  input: Readonly<Record<string, unknown>>,
  format: OutputFormat,
): Readonly<Record<string, unknown>> => {
  if (!FORMAT_CAPABLE_TOOLS.has(step.tool) || input["format"] !== undefined) {
    return input;
  }
  return {
    ...input,
    format,
  };
};

const toSerializableSteps = (steps: readonly QueryStep[]): readonly Readonly<Record<string, unknown>>[] => {
  return steps.map((step) => ({
    id: step.id,
    purpose: step.purpose,
    tool: step.tool,
    input: step.input,
    ...(step.dependsOn === undefined ? {} : { dependsOn: step.dependsOn }),
  }));
};

const toDirectSuggestion = (step: Pick<QueryStep, "tool"> & { readonly input: Readonly<Record<string, unknown>> }): string => {
  return `${step.tool} ${JSON.stringify(step.input)}`;
};

const formatUnsupportedQuery = (
  reason: string,
  suggestion: string,
  format: OutputFormat,
): string => {
  if (format === "markdown") {
    return [
      "**sg_query could not build a supported workflow.**",
      reason,
      `Try this instead: ${suggestion}`,
    ].join("\n\n");
  }

  return formatResponse(
    {
      status: "unsupported",
      reason,
      suggestion,
    },
    "json",
  );
};

const formatPlanText = (plan: Extract<QueryPlan, { supported: true }>, format: OutputFormat): string => {
  if (format !== "markdown") {
    return formatResponse(
      {
        status: "planned",
        workflow: plan.workflow,
        intent: plan.intent,
        apis: plan.apis,
        confidence: plan.confidence,
        steps: toSerializableSteps(plan.steps),
      },
      "json",
    );
  }

  const lines = [
    `## sg_query plan: ${plan.workflow}`,
    `Intent: ${plan.intent}`,
    `APIs: ${plan.apis.join(", ")}`,
    `Confidence: ${plan.confidence.toFixed(2)}`,
    "",
  ];

  for (const [index, step] of plan.steps.entries()) {
    lines.push(`${index + 1}. ${step.purpose}`);
    lines.push(`Tool: ${step.tool}`);
    lines.push(`Input: \`${JSON.stringify(step.input)}\``);
    if (step.dependsOn !== undefined) {
      lines.push(`Depends on: ${step.dependsOn.join(", ")}`);
    }
    lines.push("");
  }

  return lines.join("\n");
};

const formatExecutionText = (
  plan: Extract<QueryPlan, { supported: true }>,
  steps: readonly ExecutedQueryStep[],
  status: "completed" | "failed",
  format: OutputFormat,
): string => {
  if (plan.steps.length === 1 && status === "completed" && format !== "markdown") {
    const completed = steps[0];
    return completed?.outputText ?? "";
  }

  if (format !== "markdown") {
    return formatResponse(
      {
        status,
        workflow: plan.workflow,
        intent: plan.intent,
        apis: plan.apis,
        confidence: plan.confidence,
        steps,
      },
      "json",
    );
  }

  const lines = [
    `## sg_query: ${plan.workflow}`,
    `Status: ${status}`,
    `Intent: ${plan.intent}`,
    `APIs: ${plan.apis.join(", ")}`,
    "",
  ];

  for (const [index, step] of steps.entries()) {
    lines.push(`### Step ${index + 1}: ${step.purpose}`);
    lines.push(`Tool: ${step.tool}`);
    lines.push(`Status: ${step.status}`);
    lines.push(`Input: \`${JSON.stringify(step.input)}\``);
    if (step.dependsOn !== undefined) {
      lines.push(`Depends on: ${step.dependsOn.join(", ")}`);
    }
    if (step.error !== undefined) {
      lines.push(`Error: ${step.error.message}`);
      if (step.error.suggestedAction !== undefined) {
        lines.push(`Suggested action: ${step.error.suggestedAction}`);
      }
      lines.push(`Direct fallback: ${toDirectSuggestion(step)}`);
    } else if (step.outputText !== undefined) {
      lines.push("");
      lines.push(step.outputText);
    }
    lines.push("");
  }

  return lines.join("\n");
};

const executePlan = async (
  plan: Extract<QueryPlan, { supported: true }>,
  format: OutputFormat,
): Promise<{
  readonly status: "completed" | "failed";
  readonly steps: readonly ExecutedQueryStep[];
}> => {
  const executedSteps: ExecutedQueryStep[] = [];
  const results = new Map<string, { input: Readonly<Record<string, unknown>>; output: ToolResult }>();

  for (const step of plan.steps) {
    const context: QueryExecutionContext = { results };

    let resolvedInput: Readonly<Record<string, unknown>>;
    try {
      const input = step.resolveInput === undefined ? step.input : await step.resolveInput(context);
      resolvedInput = withRequestedFormat(step, input, format);
    } catch (error) {
      const payload = toToolErrorPayload(error, step.tool);
      executedSteps.push({
        id: step.id,
        purpose: step.purpose,
        tool: step.tool,
        status: "failed",
        input: step.input,
        ...(step.dependsOn === undefined ? {} : { dependsOn: step.dependsOn }),
        error: payload,
      });
      return { status: "failed", steps: executedSteps };
    }

    try {
      const result = await executeQueryStep(step.tool, resolvedInput);
      if (result.isError === true) {
        const payload = getResultErrorPayload(result, step.tool);
        executedSteps.push({
          id: step.id,
          purpose: step.purpose,
          tool: step.tool,
          status: "failed",
          input: resolvedInput,
          ...(step.dependsOn === undefined ? {} : { dependsOn: step.dependsOn }),
          outputText: getTextContent(result),
          ...(result.structuredContent === undefined ? {} : { structuredOutput: result.structuredContent }),
          error: payload,
        });
        return { status: "failed", steps: executedSteps };
      }

      results.set(step.id, { input: resolvedInput, output: result });
      executedSteps.push({
        id: step.id,
        purpose: step.purpose,
        tool: step.tool,
        status: "completed",
        input: resolvedInput,
        ...(step.dependsOn === undefined ? {} : { dependsOn: step.dependsOn }),
        outputText: getTextContent(result),
        ...(result.structuredContent === undefined ? {} : { structuredOutput: result.structuredContent }),
      });
    } catch (error) {
      const payload = toToolErrorPayload(error, step.tool);
      executedSteps.push({
        id: step.id,
        purpose: step.purpose,
        tool: step.tool,
        status: "failed",
        input: resolvedInput,
        ...(step.dependsOn === undefined ? {} : { dependsOn: step.dependsOn }),
        error: payload,
      });
      return { status: "failed", steps: executedSteps };
    }
  }

  return { status: "completed", steps: executedSteps };
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

export const queryToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_query",
    description:
      "Preferred natural-language interface for Singapore data. Plans or executes bounded workflows over the direct sg_* tools and returns transparent step metadata.",
    surface: "canonical",
    preferred: true,
    positioning: "Preferred OSS-facing interface for bounded workflow planning and execution.",
    scopeNotes: [
      "Preferred OSS-facing interface.",
      "Executes bounded deterministic workflows only.",
      "Direct sg_* tools remain the stable low-level contract.",
    ],
    inputSchema: QuerySchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { query, format, mode = "execute" } = validateInput(QuerySchema, input);
      const resolvedFormat = resolveOutputFormat(format);
      const plan = planQuery(query);

      if (!plan.supported) {
        return {
          isError: true,
          content: [{ type: "text", text: formatUnsupportedQuery(plan.reason, plan.suggestion, resolvedFormat) }],
          structuredContent: {
            status: "unsupported",
            mode,
            reason: plan.reason,
            suggestion: plan.suggestion,
          },
        };
      }

      if (mode === "plan") {
        return {
          content: [{ type: "text", text: formatPlanText(plan, resolvedFormat) }],
          structuredContent: {
            status: "planned",
            mode,
            workflow: plan.workflow,
            intent: plan.intent,
            apis: plan.apis,
            confidence: plan.confidence,
            toolsUsed: plan.steps.map((step) => step.tool),
            steps: toSerializableSteps(plan.steps),
          },
        };
      }

      const execution = await executePlan(plan, resolvedFormat);
      return {
        isError: execution.status === "failed",
        content: [{ type: "text", text: formatExecutionText(plan, execution.steps, execution.status, resolvedFormat) }],
        structuredContent: {
          status: execution.status,
          mode,
          workflow: plan.workflow,
          intent: plan.intent,
          apis: plan.apis,
          confidence: plan.confidence,
          toolsUsed: plan.steps.map((step) => step.tool),
          steps: execution.steps,
          ...(execution.status === "failed"
            ? { failedStep: execution.steps.find((step) => step.status === "failed") ?? null }
            : {}),
        },
      };
    },
  },
];
