import { formatResponse, QuerySchema, resolveOutputFormat, validateInput } from "@sg-apis/shared";
import type { OutputFormat, ToolErrorPayload, ToolResult } from "@sg-apis/shared";
import { planQuery } from "../router/planner.js";
import type { QueryExecutionContext, QueryPlan, QueryStep } from "../router/planner.js";
import { toToolErrorPayload } from "../middleware/error-handler.js";
import { handleAcraEntities } from "./acra-tools.js";
import {
  handleBcaLicensedBuilders,
  handleBcaRegisteredContractors,
} from "./bca-tools.js";
import {
  handleBusinessDossier,
  handleEnvironmentBrief,
  handleMacroBrief,
  handlePropertyBrief,
  handleTransportBrief,
} from "./brief-tools.js";
import { handleCeaSalespersons } from "./cea-tools.js";
import {
  handleDatagovBrowse,
  handleDatagovGet,
  handleDatagovResources,
  handleDatagovRows,
  handleDatagovSearch,
} from "./datagov-tools.js";
import { handleHdbRentalPrices, handleHdbResalePrices } from "./hdb-tools.js";
import { handleLtaBusArrivals, handleLtaTrafficIncidents, handleLtaTrainAlerts } from "./lta-tools.js";
import {
  handleMasExchangeRates,
  handleMasFinancialStats,
  handleMasInterestRates,
} from "./mas-tools.js";
import { handleNeaAirQuality, handleNeaForecast2Hr, handleNeaRainfall } from "./nea-tools.js";
import { handleOneMapGeocode, handleOneMapPopulation, handleOneMapRoute } from "./onemap-tools.js";
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

type QueryFormatSupport =
  | { readonly supported: true }
  | { readonly supported: false; readonly reason: string; readonly suggestion: string };

const TOOL_EXECUTORS: Readonly<Record<string, ToolExecutor>> = {
  sg_acra_entities: async (params) =>
    handleAcraEntities(params as Parameters<typeof handleAcraEntities>[0]),
  sg_bca_licensed_builders: async (params) =>
    handleBcaLicensedBuilders(params as Parameters<typeof handleBcaLicensedBuilders>[0]),
  sg_bca_registered_contractors: async (params) =>
    handleBcaRegisteredContractors(params as Parameters<typeof handleBcaRegisteredContractors>[0]),
  sg_cea_salespersons: async (params) =>
    handleCeaSalespersons(params as Parameters<typeof handleCeaSalespersons>[0]),
  sg_business_dossier: async (params) =>
    handleBusinessDossier(params as Parameters<typeof handleBusinessDossier>[0]),
  sg_property_brief: async (params) =>
    handlePropertyBrief(params as Parameters<typeof handlePropertyBrief>[0]),
  sg_macro_brief: async (params) =>
    handleMacroBrief(params as Parameters<typeof handleMacroBrief>[0]),
  sg_transport_brief: async (params) =>
    handleTransportBrief(params as Parameters<typeof handleTransportBrief>[0]),
  sg_environment_brief: async (params) =>
    handleEnvironmentBrief(params as Parameters<typeof handleEnvironmentBrief>[0]),
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
  sg_onemap_route: async (params) =>
    handleOneMapRoute(params as Parameters<typeof handleOneMapRoute>[0]),
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
  sg_datagov_resources: async (params) =>
    handleDatagovResources(params as Parameters<typeof handleDatagovResources>[0]),
  sg_datagov_rows: async (params) =>
    handleDatagovRows(params as Parameters<typeof handleDatagovRows>[0]),
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
  "sg_business_dossier",
  "sg_property_brief",
  "sg_macro_brief",
  "sg_transport_brief",
  "sg_environment_brief",
  "sg_acra_entities",
  "sg_bca_licensed_builders",
  "sg_bca_registered_contractors",
  "sg_cea_salespersons",
  "sg_mas_exchange_rates",
  "sg_mas_interest_rates",
  "sg_mas_financial_stats",
  "sg_onemap_population",
  "sg_ura_property_transactions",
  "sg_datagov_get",
  "sg_datagov_resources",
  "sg_datagov_rows",
  "sg_lta_bus_arrivals",
  "sg_lta_train_alerts",
  "sg_lta_traffic_incidents",
  "sg_nea_forecast_2hr",
  "sg_nea_air_quality",
  "sg_nea_rainfall",
  "sg_hdb_resale_prices",
  "sg_hdb_rental_prices",
]);

const MARKDOWN_JSON_ONLY_TOOLS = new Set([
  "sg_business_dossier",
  "sg_property_brief",
  "sg_macro_brief",
  "sg_transport_brief",
  "sg_environment_brief",
  "sg_datagov_resources",
]);

const DIRECT_TEXT_FORMAT_TOOLS = new Set([
  "sg_business_dossier",
  "sg_property_brief",
  "sg_macro_brief",
  "sg_transport_brief",
  "sg_environment_brief",
  "sg_datagov_resources",
  "sg_datagov_rows",
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

const isRecord = (value: unknown): value is Readonly<Record<string, unknown>> => {
  return typeof value === "object" && value !== null && !Array.isArray(value);
};

const getRenderableStructuredData = (
  step: ExecutedQueryStep,
): unknown | undefined => {
  const structured = step.structuredOutput;
  if (structured === undefined) {
    return undefined;
  }
  if (structured["records"] !== undefined) {
    return structured["records"];
  }
  if (structured["record"] !== undefined) {
    return structured["record"];
  }
  return structured;
};

const toGeoFeatures = (value: unknown): readonly Readonly<Record<string, unknown>>[] | null => {
  const rows = Array.isArray(value) ? value : [value];
  const features = rows.map((row) => {
    if (!isRecord(row)) {
      return null;
    }
    const lat = row["lat"];
    const lng = row["lng"];
    if (typeof lat !== "number" || typeof lng !== "number") {
      return null;
    }

    const properties = Object.fromEntries(
      Object.entries(row).filter(([key]) => key !== "lat" && key !== "lng"),
    );
    return {
      type: "Feature",
      geometry: {
        type: "Point",
        coordinates: [lng, lat],
      },
      properties,
    };
  });

  if (features.some((feature) => feature === null)) {
    return null;
  }

  return features as readonly Readonly<Record<string, unknown>>[];
};

const getSingleStepFormatSupport = (
  step: ExecutedQueryStep,
  format: OutputFormat,
): QueryFormatSupport => {
  if (MARKDOWN_JSON_ONLY_TOOLS.has(step.tool) && format !== "markdown" && format !== "json") {
    return {
      supported: false,
      reason: `${step.tool} only supports markdown or json output through sg_query.`,
      suggestion: `Use markdown or json for ${step.tool}, or call the lower-level direct tools for row or geospatial exports.`,
    };
  }

  if (format === "markdown") {
    return { supported: true };
  }

  const data = getRenderableStructuredData(step);
  if (data === undefined) {
    return {
      supported: false,
      reason: `${step.tool} does not expose structured output for ${format} rendering through sg_query.`,
      suggestion: `Call ${step.tool} directly in its default markdown format, or request json if the tool adds structured output later.`,
    };
  }

  if (format === "json") {
    return { supported: true };
  }

  if (format === "csv") {
    return Array.isArray(data) || isRecord(data)
      ? { supported: true }
      : {
          supported: false,
          reason: `${step.tool} cannot be flattened into CSV safely for sg_query.`,
          suggestion: `Use json for ${step.tool}, or call the direct tool in markdown.`,
        };
  }

  return toGeoFeatures(data) !== null
    ? { supported: true }
    : {
        supported: false,
        reason: `${step.tool} did not return coordinate rows that can be converted into GeoJSON.`,
        suggestion: `Use json for ${step.tool}, or call a geospatial direct tool that returns latitude and longitude.`,
      };
};

const getWorkflowFormatSupport = (
  mode: "plan" | "execute",
  plan: Extract<QueryPlan, { supported: true }>,
  format: OutputFormat,
): QueryFormatSupport => {
  if (format === "markdown" || format === "json") {
    return { supported: true };
  }

  if (mode === "plan") {
    return {
      supported: false,
      reason: `sg_query plan mode only supports markdown or json output, not ${format}.`,
      suggestion: "Use mode=plan with markdown or json, then execute the chosen direct tools with csv or geojson if needed.",
    };
  }

  if (plan.steps.length !== 1) {
    return {
      supported: false,
      reason: `sg_query only supports ${format} for single-step direct executions, not multi-step workflows.`,
      suggestion: "Use json or markdown for the workflow, or call the direct tool you need with csv or geojson.",
    };
  }

  return { supported: true };
};

const renderSingleStepText = (
  step: ExecutedQueryStep,
  format: OutputFormat,
): string | null => {
  if (DIRECT_TEXT_FORMAT_TOOLS.has(step.tool) && step.outputText !== undefined) {
    return step.outputText;
  }

  if (format === "markdown") {
    return step.outputText ?? "";
  }

  const data = getRenderableStructuredData(step);
  if (data === undefined) {
    return null;
  }

  if (format === "json") {
    return formatResponse(data, "json");
  }

  if (format === "csv") {
    const rows = Array.isArray(data) ? data : isRecord(data) ? [data] : null;
    return rows === null ? null : formatResponse(rows as Record<string, unknown>[], "csv");
  }

  const features = toGeoFeatures(data);
  return features === null ? null : formatResponse(features as never, "geojson");
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

      const formatSupport = getWorkflowFormatSupport(mode, plan, resolvedFormat);
      if (!formatSupport.supported) {
        return {
          isError: true,
          content: [{ type: "text", text: formatUnsupportedQuery(formatSupport.reason, formatSupport.suggestion, resolvedFormat) }],
          structuredContent: {
            status: "unsupported",
            mode,
            workflow: plan.workflow,
            reason: formatSupport.reason,
            suggestion: formatSupport.suggestion,
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
      if (execution.status === "completed" && plan.steps.length === 1) {
        const step = execution.steps[0];
        if (step !== undefined) {
          const singleStepFormatSupport = getSingleStepFormatSupport(step, resolvedFormat);
          if (!singleStepFormatSupport.supported) {
            return {
              isError: true,
              content: [{
                type: "text",
                text: formatUnsupportedQuery(
                  singleStepFormatSupport.reason,
                  singleStepFormatSupport.suggestion,
                  resolvedFormat,
                ),
              }],
              structuredContent: {
                status: "unsupported",
                mode,
                workflow: plan.workflow,
                reason: singleStepFormatSupport.reason,
                suggestion: singleStepFormatSupport.suggestion,
              },
            };
          }
        }
      }

      const executionText =
        execution.status === "completed" && plan.steps.length === 1
          ? renderSingleStepText(execution.steps[0]!, resolvedFormat) ?? formatExecutionText(plan, execution.steps, execution.status, resolvedFormat)
          : formatExecutionText(plan, execution.steps, execution.status, resolvedFormat);
      return {
        isError: execution.status === "failed",
        content: [{ type: "text", text: executionText }],
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
