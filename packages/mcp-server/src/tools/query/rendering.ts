import { formatResponse } from "@swee-sg/shared";
import type {
  NextCheck,
  OutputFormat,
  QueryBlocker,
  QueryExecutedStep,
  QueryPlannedStep,
  QueryResultSummary,
  ToolErrorPayload,
  ToolResult,
} from "@swee-sg/shared";
import type { QueryPlan, QueryStep } from "../../router/planner.js";

export type ExecutedQueryStep = QueryExecutedStep;

export type QueryFormatSupport =
  | { readonly supported: true }
  | { readonly supported: false; readonly reason: string; readonly suggestion: string };

export type WorkflowOpsMetadata = {
  readonly resultSummary?: QueryResultSummary;
  readonly nextActions?: readonly NextCheck[];
  readonly continuationHints?: readonly string[];
};

const FORMAT_CAPABLE_TOOLS = new Set([
  "sg_singstat_search",
  "sg_singstat_table",
  "sg_singstat_timeseries",
  "sg_singstat_browse",
  "sg_mas_exchange_rates",
  "sg_mas_interest_rates",
  "sg_mas_financial_stats",
  "sg_onemap_geocode",
  "sg_onemap_reverse_geocode",
  "sg_onemap_route",
  "sg_onemap_population",
  "sg_onemap_convert_coords",
  "sg_ura_property_transactions",
  "sg_ura_planning_area",
  "sg_ura_dev_charges",
  "sg_datagov_search",
  "sg_datagov_get",
  "sg_datagov_resources",
  "sg_datagov_rows",
  "sg_datagov_browse",
  "sg_lta_bus_arrivals",
  "sg_lta_train_alerts",
  "sg_lta_traffic_incidents",
  "sg_nea_forecast_2hr",
  "sg_nea_air_quality",
  "sg_nea_rainfall",
  "sg_hdb_resale_prices",
  "sg_hdb_rental_prices",
  "sg_cea_salespersons",
  "sg_bca_licensed_builders",
  "sg_bca_registered_contractors",
  "sg_boa_architects",
  "sg_boa_architecture_firms",
  "sg_acra_entities",
  "sg_gebiz_tenders",
  "sg_hawker_centres",
  "sg_moe_schools",
  "sg_moh_facilities",
  "sg_hsa_licensed_pharmacies",
  "sg_hsa_health_product_licensees",
  "sg_sfa_establishments",
  "sg_gov_feed_catalog",
  "sg_gov_feed_items",
  "sg_nparks_parks",
  "sg_pub_water_levels",
  "sg_mom_labour_stats",
  "sg_stb_visitor_stats",
  "sg_hlb_hotels",
  "sg_pa_community_outlets",
  "sg_pa_resident_network_centres",
  "sg_sportsg_facilities",
  "sg_ecda_childcare_centres",
  "sg_msf_family_services",
  "sg_msf_student_care_services",
  "sg_msf_social_service_offices",
  "sg_business_dossier",
  "sg_property_brief",
  "sg_macro_brief",
  "sg_transport_brief",
  "sg_environment_brief",
]);

const MARKDOWN_JSON_ONLY_TOOLS = new Set([
  "sg_business_dossier",
  "sg_property_brief",
  "sg_macro_brief",
  "sg_transport_brief",
  "sg_environment_brief",
  "sg_datagov_resources",
  "sg_datagov_rows",
]);

const DIRECT_TEXT_FORMAT_TOOLS = new Set([
  "sg_business_dossier",
  "sg_property_brief",
  "sg_macro_brief",
  "sg_transport_brief",
  "sg_environment_brief",
]);

export const getTextContent = (result: ToolResult): string => {
  return result.content
    .filter((item) => item.type === "text")
    .map((item) => item.text)
    .join("\n\n");
};

export const getResultErrorPayload = (result: ToolResult, tool: string): ToolErrorPayload => {
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
    category: "workflow_execution",
    severity: "medium",
    message: getTextContent(result) || `${tool} returned an error result.`,
    suggestedAction: `Call ${tool} directly to inspect and correct the failing input.`,
  };
};

export const isRecord = (value: unknown): value is Readonly<Record<string, unknown>> => {
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

export const getSingleStepFormatSupport = (
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

export const getWorkflowFormatSupport = (
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

  if (plan.workflow !== "direct_tool" || plan.steps.length !== 1) {
    return {
      supported: false,
      reason: `sg_query only supports markdown or json for named workflows; ${format} is available only for single-step direct executions.`,
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

export const withRequestedFormat = (
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

export const toSerializableSteps = (steps: readonly QueryStep[]): readonly QueryPlannedStep[] => {
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

export const extractWorkflowOpsMetadata = (
  steps: readonly ExecutedQueryStep[],
): WorkflowOpsMetadata => {
  const finalStep = steps[steps.length - 1];
  if (finalStep === undefined || finalStep.status !== "completed" || !isRecord(finalStep.structuredOutput)) {
    return {};
  }

  const record = finalStep.structuredOutput["record"];
  if (!isRecord(record)) {
    return {};
  }

  const records = record["records"];
  if (!isRecord(records)) {
    return {};
  }

  const opsStatus = isRecord(records["status"])
    ? records["status"]
    : isRecord(records["opsStatus"])
      ? records["opsStatus"]
      : undefined;
  const nextChecks = Array.isArray(records["followups"])
    ? records["followups"]
    : Array.isArray(records["nextChecks"])
      ? records["nextChecks"]
      : undefined;
  const resultSummary =
    opsStatus !== undefined
    && typeof opsStatus["level"] === "string"
    && typeof opsStatus["headline"] === "string"
      ? {
          level: opsStatus["level"],
          headline: opsStatus["headline"],
        }
      : undefined;
  const nextActions = Array.isArray(nextChecks)
    ? nextChecks.filter((item): item is NextCheck =>
      isRecord(item)
      && typeof item["tool"] === "string"
      && typeof item["reason"] === "string"
      && isRecord(item["input"]))
    : undefined;

  return {
    ...(resultSummary === undefined ? {} : { resultSummary }),
    ...(nextActions === undefined || nextActions.length === 0 ? {} : { nextActions }),
  };
};

const appendOpsMarkdownSections = (
  body: string,
  opsMetadata: WorkflowOpsMetadata,
): string => {
  const sections = [body];

  if (opsMetadata.resultSummary !== undefined) {
    sections.push("");
    sections.push(`Ops result: ${opsMetadata.resultSummary.level} - ${opsMetadata.resultSummary.headline}`);
  }

  if (opsMetadata.nextActions !== undefined && opsMetadata.nextActions.length > 0) {
    sections.push("");
    sections.push("### Next Actions");
    for (const action of opsMetadata.nextActions) {
      const tool = typeof action["tool"] === "string" ? action["tool"] : "unknown_tool";
      const reason = typeof action["reason"] === "string" ? action["reason"] : "";
      const input = isRecord(action["input"]) ? action["input"] : {};
      sections.push(`- \`${tool}\` ${reason} Input: \`${JSON.stringify(input)}\``);
    }
  }

  return sections.join("\n");
};

export const renderSingleStepWithOps = (
  step: ExecutedQueryStep,
  format: OutputFormat,
  opsMetadata: WorkflowOpsMetadata,
): string | null => {
  const baseText = renderSingleStepText(step, format);

  if (opsMetadata.resultSummary === undefined && opsMetadata.nextActions === undefined) {
    return baseText;
  }

  if (format === "markdown") {
    return appendOpsMarkdownSections(baseText ?? "", opsMetadata);
  }

  if (format === "json") {
    const data = getRenderableStructuredData(step);
    if (!isRecord(data)) {
      return baseText;
    }

    return formatResponse(
      {
        ...data,
        ...(opsMetadata.resultSummary === undefined ? {} : { resultSummary: opsMetadata.resultSummary }),
        ...(opsMetadata.nextActions === undefined ? {} : { nextActions: opsMetadata.nextActions }),
      },
      "json",
    );
  }

  return baseText;
};

export const formatQueryIssue = (
  status: "blocked" | "unsupported",
  reason: string,
  suggestion: string,
  format: OutputFormat,
  blockers: readonly QueryBlocker[] = [],
  unsupportedContext?: Readonly<{
    readonly nearestRecipe?: { readonly id: string; readonly name: string; readonly prompt: string } | undefined;
    readonly directToolHints?: readonly string[];
  }>,
): string => {
  if (format === "markdown") {
    const lines = [
      status === "blocked"
        ? "**sg_query needs one more required input before it can continue.**"
        : "**sg_query could not build a supported workflow.**",
      reason,
    ];

    if (status === "blocked" && blockers.length > 0) {
      lines.push("Missing inputs:");
      for (const blocker of blockers) {
        lines.push(
          `- \`${blocker.field}\`: ${blocker.reason} Try \`${blocker.directTool} ${JSON.stringify(blocker.exampleInput)}\` or prompt: "${blocker.suggestedPrompt}"`,
        );
      }
    }

    if (status === "unsupported" && unsupportedContext?.nearestRecipe !== undefined) {
      lines.push(
        `Closest supported recipe: \`${unsupportedContext.nearestRecipe.id}\` (${unsupportedContext.nearestRecipe.name}). Try prompt: "${unsupportedContext.nearestRecipe.prompt}".`,
      );
    }

    if (status === "unsupported" && unsupportedContext?.directToolHints !== undefined && unsupportedContext.directToolHints.length > 0) {
      lines.push(
        `Direct sg_* tools that cover this area: ${unsupportedContext.directToolHints.map((tool) => `\`${tool}\``).join(", ")}.`,
      );
    }

    lines.push(`Try this instead: ${suggestion}`);
    return lines.join("\n\n");
  }

  return formatResponse(
    {
      status,
      reason,
      suggestion,
      ...(status === "blocked" && blockers.length > 0 ? { blockers } : {}),
      ...(status === "unsupported" && unsupportedContext?.nearestRecipe !== undefined ? { nearestRecipe: unsupportedContext.nearestRecipe } : {}),
      ...(status === "unsupported" && unsupportedContext?.directToolHints !== undefined && unsupportedContext.directToolHints.length > 0 ? { directToolHints: unsupportedContext.directToolHints } : {}),
    },
    "json",
  );
};

export const formatPlanText = (plan: Extract<QueryPlan, { supported: true }>, format: OutputFormat): string => {
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

export const formatExecutionText = (
  plan: Extract<QueryPlan, { supported: true }>,
  steps: readonly ExecutedQueryStep[],
  status: "completed" | "failed",
  format: OutputFormat,
  opsMetadata: WorkflowOpsMetadata,
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
        ...(opsMetadata.resultSummary === undefined ? {} : { resultSummary: opsMetadata.resultSummary }),
        ...(opsMetadata.nextActions === undefined ? {} : { nextActions: opsMetadata.nextActions }),
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

  if (opsMetadata.resultSummary !== undefined) {
    lines.push(`Ops result: ${opsMetadata.resultSummary.level} - ${opsMetadata.resultSummary.headline}`);
    lines.push("");
  }

  if (opsMetadata.nextActions !== undefined && opsMetadata.nextActions.length > 0) {
    lines.push("### Next Actions");
    for (const action of opsMetadata.nextActions) {
      const tool = typeof action["tool"] === "string" ? action["tool"] : "unknown_tool";
      const reason = typeof action["reason"] === "string" ? action["reason"] : "";
      const input = isRecord(action["input"]) ? action["input"] : {};
      lines.push(`- \`${tool}\` ${reason} Input: \`${JSON.stringify(input)}\``);
    }
    lines.push("");
  }

  return lines.join("\n");
};
