import { ApiError } from "@sg-apis/shared";
import type { ToolResult } from "@sg-apis/shared";
import { classifyIntent, resolveToolInput } from "./classifier.js";

export type QueryExecutionContext = {
  readonly results: ReadonlyMap<
    string,
    {
      readonly input: Readonly<Record<string, unknown>>;
      readonly output: ToolResult;
    }
  >;
};

type QueryStepResolver = (
  context: QueryExecutionContext,
) => Promise<Readonly<Record<string, unknown>>> | Readonly<Record<string, unknown>>;

export type QueryStep = {
  readonly id: string;
  readonly purpose: string;
  readonly tool: string;
  readonly input: Readonly<Record<string, unknown>>;
  readonly dependsOn?: readonly string[];
  readonly resolveInput?: QueryStepResolver;
};

export type QueryPlan =
  | {
      readonly supported: true;
      readonly workflow: string;
      readonly intent: string;
      readonly confidence: number;
      readonly apis: readonly string[];
      readonly steps: readonly QueryStep[];
    }
  | {
      readonly supported: false;
      readonly reason: string;
      readonly suggestion: string;
    };

const buildUnsupportedPlan = (reason: string, suggestion: string): QueryPlan => ({
  supported: false,
  reason,
  suggestion,
});

const dependencyError = (message: string, suggestedAction: string): ApiError => {
  return new ApiError({
    apiName: "sg_query",
    source: "sg_query",
    statusCode: 422,
    code: "WORKFLOW_DEPENDENCY_ERROR",
    message,
    retryable: false,
    suggestedAction,
  });
};

const getStepRecords = (
  context: QueryExecutionContext,
  stepId: string,
): readonly Readonly<Record<string, unknown>>[] => {
  const result = context.results.get(stepId);
  if (result === undefined) {
    throw dependencyError(
      `Workflow dependency ${stepId} has not executed yet.`,
      "Retry sg_query or call the direct tool shown in the failed dependency step.",
    );
  }

  const records = result.output.structuredContent?.["records"];
  if (!Array.isArray(records)) {
    throw dependencyError(
      `Workflow step ${stepId} did not expose structured records.`,
      "Call the direct tool for this step to inspect its raw output.",
    );
  }
  return records as readonly Readonly<Record<string, unknown>>[];
};

const getFirstRecord = (
  context: QueryExecutionContext,
  stepId: string,
  emptyMessage: string,
  suggestedAction: string,
): Readonly<Record<string, unknown>> => {
  const record = getStepRecords(context, stepId)[0];
  if (record === undefined) {
    throw dependencyError(emptyMessage, suggestedAction);
  }
  return record;
};

const getPlanningAreaFromStep = (context: QueryExecutionContext, stepId: string): string => {
  const record = getFirstRecord(
    context,
    stepId,
    "The workflow could not resolve a planning area from the previous step.",
    "Call sg_ura_planning_area directly with an explicit planningArea or coordinates.",
  );
  const planningArea = record["planningArea"];
  if (typeof planningArea !== "string" || planningArea.trim() === "") {
    throw dependencyError(
      `Workflow step ${stepId} did not return a planningArea value.`,
      "Call sg_ura_planning_area directly with an explicit planningArea or coordinates.",
    );
  }
  return planningArea;
};

const getLatLngFromGeocode = (context: QueryExecutionContext, stepId: string): { lat: number; lng: number } => {
  const record = getFirstRecord(
    context,
    stepId,
    "The workflow could not resolve a geocode match from the previous step.",
    "Call sg_onemap_geocode directly with a more explicit Singapore address or postal code.",
  );
  const lat = record["lat"];
  const lng = record["lng"];
  if (typeof lat !== "number" || typeof lng !== "number") {
    throw dependencyError(
      `Workflow step ${stepId} did not return latitude and longitude.`,
      "Call sg_onemap_geocode directly and inspect the returned coordinates.",
    );
  }
  return { lat, lng };
};

const getDatasetIdFromSearch = (context: QueryExecutionContext, stepId: string): string => {
  const record = getFirstRecord(
    context,
    stepId,
    "The workflow could not find a matching data.gov.sg dataset.",
    "Broaden the dataset search terms or call sg_datagov_search directly.",
  );
  const datasetId = record["datasetId"];
  if (typeof datasetId !== "string" || datasetId.trim() === "") {
    throw dependencyError(
      `Workflow step ${stepId} did not return a datasetId.`,
      "Call sg_datagov_search directly and choose a datasetId manually.",
    );
  }
  return datasetId;
};

const sanitizeDatasetKeyword = (query: string): string => {
  const cleaned = query
    .replace(/\b(find|discover|browse|show|get)\b/gi, "")
    .replace(/\b(dataset|datasets|data\s*set|metadata)\b/gi, "")
    .trim();
  return cleaned.length > 0 ? cleaned : query;
};

const buildMacroSnapshotPlan = (
  currency: string | undefined,
): QueryPlan => ({
  supported: true,
  workflow: "macro_snapshot",
  intent: "macro",
  confidence: 0.92,
  apis: ["singstat", "mas"],
  steps: [
    {
      id: "macro_gdp",
      purpose: "Find the main GDP dataset entrypoint in SingStat.",
      tool: "sg_singstat_search",
      input: { keyword: "Singapore GDP" },
    },
    {
      id: "macro_cpi",
      purpose: "Find the main inflation or CPI dataset entrypoint in SingStat.",
      tool: "sg_singstat_search",
      input: { keyword: "Singapore CPI inflation" },
    },
    {
      id: "macro_fx",
      purpose: "Pull the current MAS SGD exchange-rate context.",
      tool: "sg_mas_exchange_rates",
      input: { currency: currency ?? "USD" },
    },
    {
      id: "macro_sora",
      purpose: "Pull the current MAS SORA reading.",
      tool: "sg_mas_interest_rates",
      input: {},
    },
  ],
});

const buildDatasetDiscoveryPlan = (query: string): QueryPlan => ({
  supported: true,
  workflow: "dataset_discovery",
  intent: "dataset",
  confidence: 0.82,
  apis: ["datagov"],
  steps: [
    {
      id: "dataset_search",
      purpose: "Search data.gov.sg for relevant datasets.",
      tool: "sg_datagov_search",
      input: { keyword: sanitizeDatasetKeyword(query) },
    },
    {
      id: "dataset_metadata",
      purpose: "Inspect metadata for the top dataset match.",
      tool: "sg_datagov_get",
      input: { datasetId: "<top-search-result.datasetId>" },
      dependsOn: ["dataset_search"],
      resolveInput: (context) => ({
        datasetId: getDatasetIdFromSearch(context, "dataset_search"),
      }),
    },
  ],
});

const buildDemographicProfilePlan = (
  params: Readonly<Record<string, unknown>>,
): QueryPlan => {
  const planningArea = params["planningArea"];
  const postalCode = params["postalCode"];

  if (typeof planningArea === "string" && planningArea.trim() !== "") {
    return {
      supported: true,
      workflow: "demographic_profile",
      intent: "demographic",
      confidence: 0.88,
      apis: ["onemap"],
      steps: [
        {
          id: "demographic_age",
          purpose: "Fetch age-group demographics for the planning area.",
          tool: "sg_onemap_population",
          input: {
            planningArea,
            dataType: "getPopulationAgeGroup",
          },
        },
        {
          id: "demographic_income",
          purpose: "Fetch household income distribution for the planning area.",
          tool: "sg_onemap_population",
          input: {
            planningArea,
            dataType: "getHouseholdMonthlyIncomeWork",
          },
        },
      ],
    };
  }

  if (typeof postalCode === "string" && postalCode.trim() !== "") {
    return {
      supported: true,
      workflow: "demographic_profile",
      intent: "demographic",
      confidence: 0.84,
      apis: ["onemap", "ura"],
      steps: [
        {
          id: "demographic_geocode",
          purpose: "Resolve the postal code to coordinates.",
          tool: "sg_onemap_geocode",
          input: {
            searchVal: postalCode,
          },
        },
        {
          id: "demographic_area",
          purpose: "Resolve the planning area from the coordinates.",
          tool: "sg_ura_planning_area",
          input: {
            lat: "<from demographic_geocode.records[0].lat>",
            lng: "<from demographic_geocode.records[0].lng>",
          },
          dependsOn: ["demographic_geocode"],
          resolveInput: (context) => {
            const { lat, lng } = getLatLngFromGeocode(context, "demographic_geocode");
            return { lat, lng };
          },
        },
        {
          id: "demographic_age",
          purpose: "Fetch age-group demographics for the resolved planning area.",
          tool: "sg_onemap_population",
          input: {
            planningArea: "<from demographic_area.records[0].planningArea>",
            dataType: "getPopulationAgeGroup",
          },
          dependsOn: ["demographic_area"],
          resolveInput: (context) => ({
            planningArea: getPlanningAreaFromStep(context, "demographic_area"),
            dataType: "getPopulationAgeGroup",
          }),
        },
        {
          id: "demographic_income",
          purpose: "Fetch household income distribution for the resolved planning area.",
          tool: "sg_onemap_population",
          input: {
            planningArea: "<from demographic_area.records[0].planningArea>",
            dataType: "getHouseholdMonthlyIncomeWork",
          },
          dependsOn: ["demographic_area"],
          resolveInput: (context) => ({
            planningArea: getPlanningAreaFromStep(context, "demographic_area"),
            dataType: "getHouseholdMonthlyIncomeWork",
          }),
        },
      ],
    };
  }

  return buildUnsupportedPlan(
    "sg_query needs a planning area or Singapore postal code to build a demographic profile.",
    "Call sg_onemap_population directly with planningArea, or provide a postal code so sg_query can resolve it.",
  );
};

const buildPropertyDueDiligencePlan = (
  query: string,
  params: Readonly<Record<string, unknown>>,
): QueryPlan => {
  const planningArea = params["planningArea"];
  const postalCode = params["postalCode"];
  const includeHdb = /hdb|flat|resale|rental/i.test(query.toLowerCase());
  const hdbTool = /rental/i.test(query.toLowerCase()) ? "sg_hdb_rental_prices" : "sg_hdb_resale_prices";
  const propertyType =
    /commercial/i.test(query) ? "commercial" : /industrial/i.test(query) ? "industrial" : "residential";

  if (typeof planningArea === "string" && planningArea.trim() !== "") {
    return {
      supported: true,
      workflow: "property_due_diligence",
      intent: "property",
      confidence: 0.9,
      apis: includeHdb ? ["onemap", "ura", "hdb"] : ["ura"],
      steps: [
        {
          id: "property_planning",
          purpose: "Inspect URA planning-area context for the target area.",
          tool: "sg_ura_planning_area",
          input: { planningArea },
        },
        {
          id: "property_transactions",
          purpose: "Inspect recent URA property transactions for the target area.",
          tool: "sg_ura_property_transactions",
          input: { area: planningArea, propertyType },
        },
        ...(includeHdb
          ? [{
              id: "property_hdb",
              purpose: "Inspect curated HDB housing prices for the target area.",
              tool: hdbTool,
              input: { town: planningArea },
            } satisfies QueryStep]
          : []),
      ],
    };
  }

  if (typeof postalCode === "string" && postalCode.trim() !== "") {
    return {
      supported: true,
      workflow: "property_due_diligence",
      intent: "property",
      confidence: 0.88,
      apis: includeHdb ? ["onemap", "ura", "hdb"] : ["onemap", "ura"],
      steps: [
        {
          id: "property_geocode",
          purpose: "Resolve the postal code to coordinates.",
          tool: "sg_onemap_geocode",
          input: { searchVal: postalCode },
        },
        {
          id: "property_planning",
          purpose: "Resolve the URA planning area for the location.",
          tool: "sg_ura_planning_area",
          input: {
            lat: "<from property_geocode.records[0].lat>",
            lng: "<from property_geocode.records[0].lng>",
          },
          dependsOn: ["property_geocode"],
          resolveInput: (context) => {
            const { lat, lng } = getLatLngFromGeocode(context, "property_geocode");
            return { lat, lng };
          },
        },
        {
          id: "property_transactions",
          purpose: "Inspect recent URA property transactions for the resolved area.",
          tool: "sg_ura_property_transactions",
          input: {
            area: "<from property_planning.records[0].planningArea>",
            propertyType,
          },
          dependsOn: ["property_planning"],
          resolveInput: (context) => ({
            area: getPlanningAreaFromStep(context, "property_planning"),
            propertyType,
          }),
        },
        ...(includeHdb
          ? [{
              id: "property_hdb",
              purpose: "Inspect curated HDB housing prices for the resolved area.",
              tool: hdbTool,
              input: {
                town: "<from property_planning.records[0].planningArea>",
              },
              dependsOn: ["property_planning"],
              resolveInput: (context) => ({
                town: getPlanningAreaFromStep(context, "property_planning"),
              }),
            } satisfies QueryStep]
          : []),
      ],
    };
  }

  return buildUnsupportedPlan(
    "sg_query needs a planning area or Singapore postal code to run property or regulatory diligence.",
    "Provide a planning area like Bedok, or give a postal code and let sg_query resolve the area first.",
  );
};

const buildDirectToolPlan = (query: string): QueryPlan => {
  const intent = classifyIntent(query);
  if (intent.tool === undefined) {
    return buildDatasetDiscoveryPlan(query);
  }

  const resolved = resolveToolInput(intent, query);

  if (resolved.tool === "sg_lta_bus_arrivals" && resolved.input["busStopCode"] === undefined) {
    return buildUnsupportedPlan(
      "sg_query needs a 5-digit Singapore bus stop code for bus-arrival lookups.",
      "Call sg_lta_bus_arrivals directly with busStopCode and optionally serviceNo.",
    );
  }

  if (resolved.tool === "sg_onemap_population" && resolved.input["planningArea"] === "") {
    return buildUnsupportedPlan(
      "sg_query needs a planning area name before it can request demographic data directly.",
      "Provide a planning area, or ask for a demographic profile with a postal code instead.",
    );
  }

  if (resolved.tool === "sg_ura_planning_area" && resolved.input["planningArea"] === undefined) {
    return buildUnsupportedPlan(
      "sg_query needs a planning area name for a direct URA planning-area lookup.",
      "Call sg_ura_planning_area directly with planningArea, or provide lat and lng yourself.",
    );
  }

  return {
    supported: true,
    workflow: "direct_tool",
    intent: intent.intent,
    confidence: intent.confidence,
    apis: intent.apis,
    steps: [
      {
        id: "direct_tool",
        purpose: `Execute ${resolved.tool}.`,
        tool: resolved.tool,
        input: resolved.input,
      },
    ],
  };
};

export const planQuery = (query: string): QueryPlan => {
  const lower = query.toLowerCase();
  const intent = classifyIntent(query);
  const isComparison = /compare|vs\.?|versus|between\s+.+\s+and\s+.+/i.test(lower);

  if (isComparison) {
    return buildUnsupportedPlan(
      "sg_query does not run comparison workflows automatically.",
      "Call the relevant direct tool separately for each item you want to compare.",
    );
  }

  switch (intent.workflow) {
    case "macro_snapshot":
      return buildMacroSnapshotPlan(
        typeof intent.extractedParams["currency"] === "string"
          ? intent.extractedParams["currency"]
          : undefined,
      );
    case "property_due_diligence":
      return buildPropertyDueDiligencePlan(query, intent.extractedParams);
    case "dataset_discovery":
      return buildDatasetDiscoveryPlan(query);
    case "demographic_profile":
      return buildDemographicProfilePlan(intent.extractedParams);
    default:
      return buildDirectToolPlan(query);
  }
};
