import { QuerySchema, resolveOutputFormat, validateInput } from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { toToolErrorPayload } from "../middleware/error-handler.js";
import { planQuery } from "../router/planner.js";
import type { QueryExecutionContext, QueryPlan, QueryStep } from "../router/planner.js";
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
      const singstatEntrypoints = kpis !== undefined && isRecord(kpis["singstatEntrypoints"])
        ? kpis["singstatEntrypoints"]
        : undefined;

      for (const key of ["gdpTableId", "cpiTableId"]) {
        const tableId = singstatEntrypoints?.[key];
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
      executedSteps.push({
        id: step.id,
        purpose: step.purpose,
        tool: step.tool,
        status: "failed",
        input: step.input,
        ...(step.dependsOn === undefined ? {} : { dependsOn: step.dependsOn }),
        error: toToolErrorPayload(error, step.tool),
      });
      return { status: "failed", steps: executedSteps };
    }

    try {
      const result = await executeQueryStep(step.tool, resolvedInput);
      if (result.isError === true) {
        executedSteps.push({
          id: step.id,
          purpose: step.purpose,
          tool: step.tool,
          status: "failed",
          input: resolvedInput,
          ...(step.dependsOn === undefined ? {} : { dependsOn: step.dependsOn }),
          outputText: getTextContent(result),
          ...(result.structuredContent === undefined ? {} : { structuredOutput: result.structuredContent }),
          error: getResultErrorPayload(result, step.tool),
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
      executedSteps.push({
        id: step.id,
        purpose: step.purpose,
        tool: step.tool,
        status: "failed",
        input: resolvedInput,
        ...(step.dependsOn === undefined ? {} : { dependsOn: step.dependsOn }),
        error: toToolErrorPayload(error, step.tool),
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
      const { query, format, mode = "execute" } = validateInput(QuerySchema, input);
      const resolvedFormat = resolveOutputFormat(format);
      const plan = planQuery(query);

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
            },
          };
        }

        return {
          content: [{ type: "text", text: formatQueryIssue("unsupported", plan.reason, plan.suggestion, resolvedFormat) }],
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
      const routingExplanation = buildRoutingExplanation(plan);
      const continuationHints = execution.status === "completed"
        ? buildContinuationHints(plan, execution.steps)
        : [];
      const opsMetadata: WorkflowOpsMetadata = execution.status === "completed"
        ? { ...extractWorkflowOpsMetadata(execution.steps), continuationHints }
        : {};

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
          ...(opsMetadata.resultSummary === undefined ? {} : { resultSummary: opsMetadata.resultSummary }),
          ...(opsMetadata.nextActions === undefined ? {} : { nextActions: opsMetadata.nextActions }),
          routingExplanation,
          ...(continuationHints.length > 0 ? { continuationHints } : {}),
          ...(execution.status === "failed"
            ? { failedStep: execution.steps.find((step) => step.status === "failed") ?? null }
            : {}),
        },
      };
    },
  },
];
