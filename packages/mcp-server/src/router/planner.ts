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
  workflow: "macro_brief",
  intent: "macro",
  confidence: 0.92,
  apis: ["singstat", "mas"],
  steps: [
    {
      id: "macro_brief",
      purpose: "Build a compact Singapore macro starter brief.",
      tool: "sg_macro_brief",
      input: { currency: currency ?? "USD" },
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
  const propertyType =
    /commercial/i.test(query) ? "commercial" : /industrial/i.test(query) ? "industrial" : "residential";

  if (typeof planningArea === "string" && planningArea.trim() !== "") {
    return {
      supported: true,
      workflow: "property_brief",
      intent: "property",
      confidence: 0.9,
      apis: includeHdb ? ["onemap", "ura", "hdb"] : ["ura"],
      steps: [
        {
          id: "property_brief",
          purpose: "Build a location and property brief for the target area.",
          tool: "sg_property_brief",
          input: {
            planningArea,
            propertyType,
            ...(includeHdb ? {} : { includeEnvironment: false }),
          },
        },
      ],
    };
  }

  if (typeof postalCode === "string" && postalCode.trim() !== "") {
    return {
      supported: true,
      workflow: "property_brief",
      intent: "property",
      confidence: 0.88,
      apis: includeHdb ? ["onemap", "ura", "hdb"] : ["onemap", "ura"],
      steps: [
        {
          id: "property_brief",
          purpose: "Build a location and property brief from the postal code.",
          tool: "sg_property_brief",
          input: {
            postalCode,
            propertyType,
            ...(includeHdb ? {} : { includeEnvironment: false }),
          },
        },
      ],
    };
  }

  return buildUnsupportedPlan(
    "sg_query needs a planning area or Singapore postal code to run property or regulatory diligence.",
    "Provide a planning area like Bedok, or give a postal code and let sg_query resolve the area first.",
  );
};

const buildBusinessRegistryPlan = (
  params: Readonly<Record<string, unknown>>,
): QueryPlan => {
  const entityName = typeof params["entityName"] === "string" ? params["entityName"] : undefined;
  const companyName = typeof params["companyName"] === "string" ? params["companyName"] : entityName;
  const estateAgentName = typeof params["estateAgentName"] === "string" ? params["estateAgentName"] : undefined;
  const acraName = estateAgentName ?? companyName;
  const uen = typeof params["uen"] === "string" ? params["uen"] : undefined;
  const salespersonName = typeof params["salespersonName"] === "string" ? params["salespersonName"] : undefined;
  const registrationNo = typeof params["registrationNo"] === "string" ? params["registrationNo"] : undefined;
  const estateAgentLicenseNo =
    typeof params["estateAgentLicenseNo"] === "string" ? params["estateAgentLicenseNo"] : undefined;
  const workhead = typeof params["workhead"] === "string" ? params["workhead"] : undefined;
  const grade = typeof params["grade"] === "string" ? params["grade"] : undefined;
  const classCode = typeof params["classCode"] === "string" ? params["classCode"] : undefined;

  const steps: QueryStep[] = [];

  if (
    salespersonName !== undefined
    || registrationNo !== undefined
    || estateAgentName !== undefined
    || estateAgentLicenseNo !== undefined
  ) {
    steps.push({
      id: "registry_cea",
      purpose: "Inspect CEA salesperson and estate-agent registration details.",
      tool: "sg_cea_salespersons",
      input: {
        ...(salespersonName === undefined ? {} : { salespersonName }),
        ...(registrationNo === undefined ? {} : { registrationNo }),
        ...(estateAgentName === undefined ? {} : { estateAgentName }),
        ...(estateAgentLicenseNo === undefined ? {} : { estateAgentLicenseNo }),
      },
    });
  }

  if (acraName !== undefined || uen !== undefined) {
    steps.push({
      id: "registry_acra",
      purpose: "Inspect ACRA corporate-entity registration details.",
      tool: "sg_acra_entities",
      input: {
        ...(acraName === undefined ? {} : { entityName: acraName }),
        ...(uen === undefined ? {} : { uen }),
      },
    });
  }

  if (companyName !== undefined || uen !== undefined || classCode !== undefined) {
    steps.push({
      id: "registry_bca_builders",
      purpose: "Check whether the entity appears on the BCA licensed-builders register.",
      tool: "sg_bca_licensed_builders",
      input: {
        ...(companyName === undefined ? {} : { companyName }),
        ...(uen === undefined ? {} : { uenNo: uen }),
        ...(classCode === undefined ? {} : { classCode }),
      },
    });
  }

  if (companyName !== undefined || uen !== undefined || workhead !== undefined || grade !== undefined) {
    steps.push({
      id: "registry_bca_contractors",
      purpose: "Check whether the entity appears on the BCA registered-contractors register.",
      tool: "sg_bca_registered_contractors",
      input: {
        ...(companyName === undefined ? {} : { companyName }),
        ...(uen === undefined ? {} : { uenNo: uen }),
        ...(workhead === undefined ? {} : { workhead }),
        ...(grade === undefined ? {} : { grade }),
      },
    });
  }

  if (steps.length === 0) {
    return buildUnsupportedPlan(
      "sg_query needs a company name, entity name, UEN, salesperson, or estate-agent identifier to run registry diligence.",
      "Provide an explicit company or salesperson identifier, or call the direct ACRA, CEA, or BCA tool yourself.",
    );
  }

  return {
    supported: true,
    workflow: "business_dossier",
    intent: "business",
    confidence: 0.9,
    apis: Array.from(new Set(steps.map((step) => step.tool.split("_")[1]!))),
    steps: [
      {
        id: "business_dossier",
        purpose: "Build a cross-registry business dossier.",
        tool: "sg_business_dossier",
        input: {
          ...(acraName === undefined ? {} : { entityName: acraName }),
          ...(uen === undefined ? {} : { uen }),
          ...(salespersonName === undefined ? {} : { salespersonName }),
          ...(registrationNo === undefined ? {} : { registrationNo }),
          ...(estateAgentName === undefined ? {} : { estateAgentName }),
          ...(estateAgentLicenseNo === undefined ? {} : { estateAgentLicenseNo }),
          ...(classCode === undefined ? {} : { classCode }),
          ...(workhead === undefined ? {} : { workhead }),
          ...(grade === undefined ? {} : { grade }),
        },
      },
    ],
  };
};

const buildTransportBriefPlan = (
  params: Readonly<Record<string, unknown>>,
): QueryPlan => {
  const busStopCode = typeof params["busStopCode"] === "string" ? params["busStopCode"] : undefined;
  const serviceNo = typeof params["serviceNo"] === "string" ? params["serviceNo"] : undefined;

  return {
    supported: true,
    workflow: "transport_brief",
    intent: "transport",
    confidence: 0.9,
    apis: ["lta"],
    steps: [
      {
        id: "transport_brief",
        purpose: "Build a live transport operations brief.",
        tool: "sg_transport_brief",
        input: {
          ...(busStopCode === undefined ? {} : { busStopCode }),
          ...(serviceNo === undefined ? {} : { serviceNo }),
        },
      },
    ],
  };
};

const buildEnvironmentBriefPlan = (
  params: Readonly<Record<string, unknown>>,
): QueryPlan => {
  const area = typeof params["planningArea"] === "string" ? params["planningArea"] : undefined;
  const region = typeof params["region"] === "string" ? params["region"] : undefined;
  const stationId = typeof params["stationId"] === "string" ? params["stationId"] : undefined;
  const date = typeof params["date"] === "string" ? params["date"] : undefined;

  return {
    supported: true,
    workflow: "environment_brief",
    intent: "environment",
    confidence: 0.89,
    apis: ["nea"],
    steps: [
      {
        id: "environment_brief",
        purpose: "Build a live environment monitoring brief.",
        tool: "sg_environment_brief",
        input: {
          ...(area === undefined ? {} : { area }),
          ...(region === undefined ? {} : { region }),
          ...(stationId === undefined ? {} : { stationId }),
          ...(date === undefined ? {} : { date }),
        },
      },
    ],
  };
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

  if (resolved.tool === "sg_cea_salespersons" && Object.keys(resolved.input).length === 0) {
    return buildUnsupportedPlan(
      "sg_query needs a salesperson, registration number, estate agent, or estate-agent licence number for CEA lookups.",
      "Provide a salesperson or estate-agent identifier, or call sg_cea_salespersons directly.",
    );
  }

  if (resolved.tool === "sg_bca_licensed_builders" && Object.keys(resolved.input).length === 0) {
    return buildUnsupportedPlan(
      "sg_query needs a company, UEN, or builder class identifier for BCA licensed-builder lookups.",
      "Provide a company name, UEN, or builder class code, or call sg_bca_licensed_builders directly.",
    );
  }

  if (resolved.tool === "sg_bca_registered_contractors" && Object.keys(resolved.input).length === 0) {
    return buildUnsupportedPlan(
      "sg_query needs a company, UEN, workhead, or grade for BCA registered-contractor lookups.",
      "Provide a company name, UEN, workhead, or grade, or call sg_bca_registered_contractors directly.",
    );
  }

  if (resolved.tool === "sg_acra_entities" && Object.keys(resolved.input).length === 0) {
    return buildUnsupportedPlan(
      "sg_query needs an entity name or UEN for ACRA lookups.",
      "Provide an explicit company name or UEN, or call sg_acra_entities directly.",
    );
  }

  if (resolved.tool === "sg_datagov_resources" && resolved.input["datasetId"] === undefined) {
    return buildUnsupportedPlan(
      "sg_query needs a data.gov.sg datasetId like d_8b84c4ee58e3cfc0ece0d773c8ca6abc to inspect resource metadata.",
      "Call sg_datagov_resources directly with datasetId, or use sg_datagov_search first to discover a dataset ID.",
    );
  }

  if (resolved.tool === "sg_datagov_rows" && resolved.input["datasetId"] === undefined) {
    return buildUnsupportedPlan(
      "sg_query needs a data.gov.sg datasetId like d_8b84c4ee58e3cfc0ece0d773c8ca6abc to read bounded rows.",
      "Call sg_datagov_rows directly with datasetId or resourceId, or inspect sg_datagov_resources first.",
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
    case "business_registry_diligence":
      return buildBusinessRegistryPlan(intent.extractedParams);
    case "dataset_discovery":
      return buildDatasetDiscoveryPlan(query);
    case "demographic_profile":
      return buildDemographicProfilePlan(intent.extractedParams);
    case "transport_brief":
      return buildTransportBriefPlan(intent.extractedParams);
    case "environment_brief":
      return buildEnvironmentBriefPlan(intent.extractedParams);
    default:
      return buildDirectToolPlan(query);
  }
};
