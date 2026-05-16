import { randomUUID } from "node:crypto";
import { QuerySchema, resolveOutputFormat, validateInput } from "@dude/shared";
import type { ContextIds, OutputFormat, ToolResult } from "@dude/shared";
import { createLogger } from "@dude/shared";
import { toToolErrorPayload } from "../middleware/error-handler.js";
import { planQuery } from "../router/planner.js";
import type { QueryExecutionContext, QueryPlan, QueryStep } from "../router/planner.js";
import { buildArtifactResult, shouldUseArtifact } from "./artifacts.js";
import { buildMapPayloadFromStructuredContent, withMapUiMetadata } from "./map-payload.js";
import { RECIPE_FALLBACK_TOOLS } from "./recipe-fallbacks.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";
import { executeQueryTool } from "./query/executors.js";
import {
  extractWorkflowOpsMetadata,
  formatExecutionText,
  formatPlanText,
  formatQueryIssue,
  getResultErrorPayload,
  getSingleStepFormatSupport,
  getTextContent,
  getWorkflowFormatSupport,
  isRecord,
  renderSingleStepWithOps,
  toSerializableSteps,
  type ExecutedQueryStep,
  type WorkflowOpsMetadata,
  withRequestedFormat,
} from "./query/rendering.js";

const MAP_TOOL_META = withMapUiMetadata(undefined);
const logger = createLogger("query-tool");

const recipeIdFromName = (name: string): string =>
  name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");

const WORKFLOW_TO_RECIPE_NAME: Readonly<Record<string, string>> = {
  route_planning: "Postal Route",
  reverse_geocode: "Reverse Geocode",
  coordinate_conversion: "Coordinate Conversion",
  singstat_drilldown: "SingStat Drilldown",
  dataset_discovery: "Dataset Discovery Fallback",
  macro_brief: "Macro Snapshot",
  property_brief: "Property Due Diligence",
  transport_brief: "Transport Status",
  environment_brief: "Environment Snapshot",
  business_dossier: "Business Registry Diligence",
  civic_discovery: "Civic Discovery",
  hdb_resale: "HDB Resale Check",
  hdb_rental: "HDB Rental Check",
  ura_dev_charges: "URA Development Charges",
  datagov_browse: "Dataset Collection Browse",
};

const findRecipeIdForWorkflow = (workflow: string | undefined): string | undefined => {
  if (workflow === undefined) return undefined;
  const name = WORKFLOW_TO_RECIPE_NAME[workflow];
  return name === undefined ? undefined : recipeIdFromName(name);
};

// keyword-to-recipe mapping drives the unsupported->nearest-recipe suggestion.
// Names must match real entries in RECIPE_CATALOG so the slugified id
// resolves to a fallbackTools list. RECIPE_FALLBACK_TOOLS is the shared
// runtime lookup; the catalog-parity test asserts the two stay aligned.
const RECIPE_KEYWORD_HINTS: ReadonlyArray<{
  readonly keywords: readonly string[];
  readonly name: string;
  readonly prompt: string;
}> = [
  { keywords: ["route", "walk", "drive", "from", "to"], name: "Postal Route", prompt: "Walk from 049178 to 048616" },
  { keywords: ["reverse", "geocode", "coordinate"], name: "Reverse Geocode", prompt: "Reverse geocode 1.2840, 103.8510" },
  { keywords: ["convert", "svy21", "wgs84"], name: "Coordinate Conversion", prompt: "Convert SVY21 28001 38744 to WGS84" },
  { keywords: ["singstat", "gdp", "cpi", "time series"], name: "SingStat Drilldown", prompt: "Browse SingStat transport datasets" },
  { keywords: ["dataset", "data.gov", "browse"], name: "data.gov Collection Browse", prompt: "Browse data.gov.sg HDB datasets" },
  { keywords: ["bus", "stop"], name: "Bus Stop Status", prompt: "Bus arrivals at stop 83139" },
  { keywords: ["weather", "rain", "air quality", "psi", "forecast", "outdoor", "event"], name: "Outdoor Event Check", prompt: "Outdoor event check in Bedok" },
  { keywords: ["acra", "uen", "business", "dossier", "company"], name: "Business Due Diligence", prompt: "Business dossier for UEN 201912345K" },
  { keywords: ["community club", "passion wave", "rc"], name: "Community Club Near Postal Code", prompt: "Community club near 560123" },
  { keywords: ["rental"], name: "HDB Rental Check", prompt: "Bedok HDB rental" },
  { keywords: ["development charge", "ura charge"], name: "URA Development Charges", prompt: "URA development charges for Bedok" },
];

const findNearestRecipe = (
  query: string,
): { id: string; name: string; prompt: string; fallbackTools: readonly string[] } | undefined => {
  const lower = query.toLowerCase();
  let best: { score: number; hint: (typeof RECIPE_KEYWORD_HINTS)[number] } | undefined;
  for (const hint of RECIPE_KEYWORD_HINTS) {
    let score = 0;
    for (const keyword of hint.keywords) {
      if (lower.includes(keyword)) score += 1;
    }
    if (score > 0 && (best === undefined || score > best.score)) {
      best = { score, hint };
    }
  }
  if (best === undefined) return undefined;
  const id = recipeIdFromName(best.hint.name);
  return {
    id,
    name: best.hint.name,
    prompt: best.hint.prompt,
    fallbackTools: RECIPE_FALLBACK_TOOLS[id] ?? [],
  };
};

const buildRoutingExplanation = (
  plan: Readonly<{
    workflow: string;
    confidence: number;
    steps: readonly Pick<QueryStep, "tool">[];
  }>,
): string => {
  const tools = plan.steps.map((step) => step.tool).join(" → ");
  return `Routed to ${plan.workflow} (confidence ${plan.confidence.toFixed(2)}) via ${tools}. Drop to direct sg_* tools when you have exact identifiers.`;
};

const buildContinuationHints = (
  plan: Extract<QueryPlan, { supported: true }>,
  steps: readonly ExecutedQueryStep[],
): readonly string[] => {
  const hints: string[] = [];
  const lastStep = steps[steps.length - 1];
  if (lastStep === undefined) {
    return hints;
  }

  const structured = lastStep.structuredOutput;
  if (isRecord(structured)) {
    const artifact = isRecord(structured["record"]) ? structured["record"] : undefined;
    if (artifact !== undefined) {
      const nextChecks = artifact["nextChecks"];
      if (Array.isArray(nextChecks)) {
        for (const check of nextChecks) {
          if (!isRecord(check) || typeof check["tool"] !== "string") {
            continue;
          }
          const input = isRecord(check["input"]) ? check["input"] : {};
          hints.push(`Call ${check["tool"]} with ${JSON.stringify(input)} next.`);
        }
      }
    }

    const record = structured["record"] ?? structured["records"];
    if (isRecord(record)) {
      const kpis = isRecord(record["kpis"]) ? record["kpis"] : undefined;
      const singstatSeries = kpis !== undefined && isRecord(kpis["singstatSeries"])
        ? kpis["singstatSeries"]
        : undefined;

      for (const key of ["gdpTableId", "cpiYoYTableId", "cpiIndexTableId"]) {
        const tableId = singstatSeries?.[key];
        if (typeof tableId === "string" && tableId.trim() !== "") {
          hints.push(`Call sg_singstat_table with tableId "${tableId}" for detailed data.`);
        }
      }

      const locationResolution = isRecord(record["locationResolution"])
        ? record["locationResolution"]
        : undefined;
      const resolvedArea = locationResolution?.["resolvedPlanningArea"];
      if (typeof resolvedArea === "string" && resolvedArea.trim() !== "") {
        hints.push(`Call sg_ura_dev_charges with planningArea "${resolvedArea}" for development charge context.`);
      }

      const datasetId = record["datasetId"];
      if (typeof datasetId === "string" && datasetId.trim() !== "") {
        hints.push(`Call sg_datagov_resources with datasetId "${datasetId}" to inspect the current resource shape.`);
      }
    }
  }

  if (plan.workflow === "civic_discovery") {
    hints.push("Use exact quoted names when you want a direct civic-directory lookup instead of proximity search.");
  }

  if (plan.workflow === "transport_brief" || plan.workflow === "environment_brief") {
    hints.push("Use sg://benchmarks to set refresh cadence and alert expectations for live operational workflows.");
  }

  if (plan.workflow === "business_dossier" || plan.workflow === "property_brief") {
    hints.push("Use sg://playbooks when you need the next bounded workflow after the initial brief artifact.");
  }

  const dedupedHints = Array.from(new Set(hints)).slice(0, 4);
  return dedupedHints.length === 0
    ? ["Use sg://recipes or sg://playbooks to discover the next bounded workflow."]
    : dedupedHints;
};

const executePlan = async (
  plan: Extract<QueryPlan, { supported: true }>,
  format: OutputFormat,
  runLogger: ReturnType<typeof logger.child>,
  contextIds?: ContextIds,
): Promise<{
  readonly status: "completed" | "failed";
  readonly steps: readonly ExecutedQueryStep[];
}> => {
  const executedSteps: ExecutedQueryStep[] = [];
  const results = new Map<string, { input: Readonly<Record<string, unknown>>; output: ToolResult }>();

  for (const step of plan.steps) {
    runLogger.info("query step start", {
      stepId: step.id,
      tool: step.tool,
      workflow: plan.workflow,
      dependsOn: step.dependsOn ?? [],
    });
    const context: QueryExecutionContext = { results };

    let resolvedInput: Readonly<Record<string, unknown>>;
    try {
      const input = step.resolveInput === undefined ? step.input : await step.resolveInput(context);
      resolvedInput = withRequestedFormat(step, input, format);
    } catch (error) {
      runLogger.error("query step input resolution failed", {
        stepId: step.id,
        tool: step.tool,
        workflow: plan.workflow,
        error,
      });
        executedSteps.push({
          id: step.id,
          purpose: step.purpose,
          tool: step.tool,
          status: "failed",
          input: step.input,
          ...(step.dependsOn === undefined ? {} : { dependsOn: step.dependsOn }),
          error: toToolErrorPayload(
            error,
            step.tool,
            contextIds === undefined ? {} : { contextIds },
          ),
        });
        return { status: "failed", steps: executedSteps };
      }

    try {
      const result = await executeQueryStep(step.tool, resolvedInput);
      if (result.isError === true) {
        const payload = getResultErrorPayload(result, step.tool);
        runLogger.warn("query step returned tool error", {
          stepId: step.id,
          tool: step.tool,
          workflow: plan.workflow,
          code: payload.code,
          source: payload.source,
          retryable: payload.retryable,
          statusCode: payload.statusCode,
        });
        executedSteps.push({
          id: step.id,
          purpose: step.purpose,
          tool: step.tool,
          status: "failed",
          input: resolvedInput,
          ...(step.dependsOn === undefined ? {} : { dependsOn: step.dependsOn }),
          outputText: getTextContent(result),
          ...(result.structuredContent === undefined ? {} : { structuredOutput: result.structuredContent }),
          error: payload.contextIds === undefined && contextIds !== undefined
            ? { ...payload, contextIds }
            : payload,
        });
        return { status: "failed", steps: executedSteps };
      }

      results.set(step.id, { input: resolvedInput, output: result });
      runLogger.info("query step completed", {
        stepId: step.id,
        tool: step.tool,
        workflow: plan.workflow,
      });
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
      runLogger.error("query step execution failed", {
        stepId: step.id,
        tool: step.tool,
        workflow: plan.workflow,
        error,
      });
        executedSteps.push({
          id: step.id,
          purpose: step.purpose,
          tool: step.tool,
          status: "failed",
          input: resolvedInput,
          ...(step.dependsOn === undefined ? {} : { dependsOn: step.dependsOn }),
          error: toToolErrorPayload(
            error,
            step.tool,
            contextIds === undefined ? {} : { contextIds },
          ),
        });
        return { status: "failed", steps: executedSteps };
      }
  }

  return { status: "completed", steps: executedSteps };
};

const countStructuredRows = (value: unknown): number | undefined => {
  if (Array.isArray(value)) {
    return value.length;
  }
  if (isRecord(value)) {
    if (Array.isArray(value["records"])) {
      return value["records"].length;
    }
    if (isRecord(value["record"]) && Array.isArray(value["record"]["records"])) {
      return value["record"]["records"].length;
    }
  }
  return undefined;
};

const extractMapPayload = (
  steps: readonly ExecutedQueryStep[],
): Readonly<Record<string, unknown>> | undefined => {
  for (const step of [...steps].reverse()) {
    if (step.status !== "completed") {
      continue;
    }
    const payload = buildMapPayloadFromStructuredContent(step.tool, step.structuredOutput);
    if (payload !== null) {
      return payload as Readonly<Record<string, unknown>>;
    }
  }
  return undefined;
};

export const executeQueryStep = async (
  toolName: string,
  input: Readonly<Record<string, unknown>>,
): Promise<ToolResult> => {
  return executeQueryTool(toolName, input);
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
      const { query, format, mode = "execute", includeContextIds } = validateInput(QuerySchema, input);
      const traceId = randomUUID();
      const contextIds = includeContextIds === true
        ? {
            traceId,
            requestId: traceId,
          }
        : undefined;
      const queryLogger = logger.child({ traceId, workflowInterface: "sg_query" });
      const resolvedFormat = resolveOutputFormat(format);
      const preview = query.length > 160 ? `${query.slice(0, 160)}...` : query;
      queryLogger.info("received sg_query request", {
        mode,
        format: resolvedFormat,
        queryLength: query.length,
        queryPreview: preview,
      });
      const plan = planQuery(query);
      if (!plan.supported) {
        queryLogger.warn("query plan not executable", {
          blocked: plan.blocked === true,
          reason: plan.reason,
          suggestion: plan.suggestion,
          ...(plan.blocked === true ? { workflow: plan.workflow, blockers: plan.blockers.length } : {}),
        });
      } else {
        queryLogger.info("query plan resolved", {
          workflow: plan.workflow,
          intent: plan.intent,
          confidence: plan.confidence,
          stepCount: plan.steps.length,
        });
      }

      if (!plan.supported) {
        if (plan.blocked === true) {
          return {
            content: [{
              type: "text",
              text: formatQueryIssue("blocked", plan.reason, plan.suggestion, resolvedFormat, plan.blockers),
            }],
            structuredContent: {
              status: "blocked",
              mode,
              workflow: plan.workflow,
              intent: plan.intent,
              apis: plan.apis,
              confidence: plan.confidence,
              toolsUsed: plan.steps.map((step) => step.tool),
              steps: toSerializableSteps(plan.steps),
              blockers: plan.blockers,
              reason: plan.reason,
              suggestion: plan.suggestion,
              routingExplanation: buildRoutingExplanation(plan),
              ...(findRecipeIdForWorkflow(plan.workflow) === undefined
                ? {}
                : { recipeId: findRecipeIdForWorkflow(plan.workflow)! }),
              ...(contextIds === undefined ? {} : { contextIds }),
            },
          };
        }

        const nearestRecipe = findNearestRecipe(query);
        const directToolHints = nearestRecipe?.fallbackTools ?? [];
        const nearestRecipeForResponse = nearestRecipe === undefined
          ? undefined
          : { id: nearestRecipe.id, name: nearestRecipe.name, prompt: nearestRecipe.prompt };
        return {
          content: [{
            type: "text",
            text: formatQueryIssue(
              "unsupported",
              plan.reason,
              plan.suggestion,
              resolvedFormat,
              [],
              { nearestRecipe: nearestRecipeForResponse, directToolHints },
            ),
          }],
          structuredContent: {
            status: "unsupported",
            mode,
            reason: plan.reason,
            suggestion: plan.suggestion,
            ...(nearestRecipeForResponse === undefined ? {} : { nearestRecipe: nearestRecipeForResponse }),
            ...(directToolHints.length === 0 ? {} : { directToolHints }),
            ...(contextIds === undefined ? {} : { contextIds }),
          },
        };
      }

      const formatSupport = getWorkflowFormatSupport(mode, plan, resolvedFormat);
      if (!formatSupport.supported) {
        return {
          content: [{ type: "text", text: formatQueryIssue("unsupported", formatSupport.reason, formatSupport.suggestion, resolvedFormat) }],
          structuredContent: {
            status: "unsupported",
            mode,
            workflow: plan.workflow,
            intent: plan.intent,
            apis: plan.apis,
            confidence: plan.confidence,
            toolsUsed: plan.steps.map((step) => step.tool),
            steps: toSerializableSteps(plan.steps),
            reason: formatSupport.reason,
            suggestion: formatSupport.suggestion,
            ...(contextIds === undefined ? {} : { contextIds }),
          },
        };
      }

      if (mode === "plan") {
        queryLogger.info("query returned plan mode response", {
          workflow: plan.workflow,
          intent: plan.intent,
          stepCount: plan.steps.length,
        });
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
            ...(contextIds === undefined ? {} : { contextIds }),
          },
        };
      }

      const execution = await executePlan(plan, resolvedFormat, queryLogger, contextIds);
      const routingExplanation = buildRoutingExplanation(plan);
      const continuationHints = execution.status === "completed"
        ? buildContinuationHints(plan, execution.steps)
        : [];
      const opsMetadata: WorkflowOpsMetadata = execution.status === "completed"
        ? { ...extractWorkflowOpsMetadata(execution.steps), continuationHints }
        : {};
      queryLogger.info("query execution finished", {
        workflow: plan.workflow,
        status: execution.status,
        completedSteps: execution.steps.filter((step) => step.status === "completed").length,
        totalSteps: execution.steps.length,
      });

      if (execution.status === "completed" && plan.steps.length === 1) {
        const step = execution.steps[0];
        if (step !== undefined) {
          const singleStepFormatSupport = getSingleStepFormatSupport(step, resolvedFormat);
          if (!singleStepFormatSupport.supported) {
            return {
              content: [{
                type: "text",
                text: formatQueryIssue(
                  "unsupported",
                  singleStepFormatSupport.reason,
                  singleStepFormatSupport.suggestion,
                  resolvedFormat,
                ),
              }],
              structuredContent: {
                status: "unsupported",
                mode,
                workflow: plan.workflow,
                intent: plan.intent,
                apis: plan.apis,
                confidence: plan.confidence,
                toolsUsed: plan.steps.map((candidate) => candidate.tool),
                steps: toSerializableSteps(plan.steps),
                reason: singleStepFormatSupport.reason,
                suggestion: singleStepFormatSupport.suggestion,
                ...(contextIds === undefined ? {} : { contextIds }),
              },
            };
          }
        }
      }

      const executionText =
        execution.status === "completed" && plan.steps.length === 1
          ? renderSingleStepWithOps(execution.steps[0]!, resolvedFormat, opsMetadata)
            ?? formatExecutionText(plan, execution.steps, execution.status, resolvedFormat, opsMetadata)
          : formatExecutionText(plan, execution.steps, execution.status, resolvedFormat, opsMetadata);

      const mapPayload = execution.status === "completed"
        ? extractMapPayload(execution.steps)
        : undefined;
      const recipeId = findRecipeIdForWorkflow(plan.workflow);
      const structuredContent = {
        status: execution.status,
        mode,
        workflow: plan.workflow,
        intent: plan.intent,
        apis: plan.apis,
        confidence: plan.confidence,
        toolsUsed: plan.steps.map((step) => step.tool),
        steps: execution.steps,
        ...(opsMetadata.resultSummary === undefined ? {} : { resultSummary: opsMetadata.resultSummary }),
        ...(opsMetadata.nextActions === undefined ? {} : { nextActions: opsMetadata.nextActions }),
        routingExplanation,
        ...(recipeId === undefined ? {} : { recipeId }),
        ...(continuationHints.length > 0 ? { continuationHints } : {}),
        ...(execution.status === "failed"
          ? { failedStep: execution.steps.find((step) => step.status === "failed") ?? null }
          : {}),
        ...(mapPayload === undefined ? {} : { mapPayload }),
        ...(contextIds === undefined ? {} : { contextIds }),
      } as const;

      const finalStep = execution.steps[execution.steps.length - 1];
      const rowCount = countStructuredRows(finalStep?.structuredOutput);
      if (shouldUseArtifact(executionText, rowCount)) {
        return buildArtifactResult({
          toolName: "sg_query",
          input: {
            query,
            format: resolvedFormat,
            mode,
            ...(includeContextIds === true ? { includeContextIds: true } : {}),
          },
          kind: plan.workflow === "transport_brief" || plan.workflow === "environment_brief"
            ? "realtime-query"
            : "query",
          title: `sg_query result for ${plan.workflow}`,
          description: "Large sg_query response promoted to a transient artifact resource.",
          fullText: executionText,
          payload: {
            text: executionText,
            result: structuredContent,
          },
          preview: {
            workflow: plan.workflow,
            status: execution.status,
            steps: execution.steps.slice(0, 3),
            ...(mapPayload === undefined ? {} : { mapPayload }),
          },
          structuredContentBase: {
            status: execution.status,
            mode,
            workflow: plan.workflow,
            intent: plan.intent,
            apis: plan.apis,
            confidence: plan.confidence,
            toolsUsed: plan.steps.map((step) => step.tool),
            ...(opsMetadata.resultSummary === undefined ? {} : { resultSummary: opsMetadata.resultSummary }),
            ...(opsMetadata.nextActions === undefined ? {} : { nextActions: opsMetadata.nextActions }),
            routingExplanation,
            ...(continuationHints.length > 0 ? { continuationHints } : {}),
            ...(execution.status === "failed"
              ? { failedStep: execution.steps.find((step) => step.status === "failed") ?? null }
              : {}),
            ...(mapPayload === undefined ? {} : { mapPayload }),
            ...(contextIds === undefined ? {} : { contextIds }),
          },
          ...(plan.workflow === "transport_brief" || plan.workflow === "environment_brief"
            ? { realtime: true }
            : {}),
          ...(mapPayload === undefined ? {} : { _meta: MAP_TOOL_META }),
          isError: execution.status === "failed",
        });
      }

      return {
        isError: execution.status === "failed",
        content: [{ type: "text", text: executionText }],
        structuredContent,
        ...(mapPayload === undefined ? {} : { _meta: MAP_TOOL_META }),
      };
    },
  },
];
