import { ApiError } from "@sg-apis/shared";
import { DEFAULT_CIVIC_RADIUS_KM } from "../apis/civic/utils.js";
import { classifyIntent, resolveToolInput } from "./classifier.js";
import { PLANNING_AREAS, toTitleCase } from "./domain-constants.js";
import {
  buildBlockedPlan,
  buildDirectToolBlockedPlan,
  createBlocker,
  type QueryExecutionContext,
  type QueryPlan,
} from "./planner-core.js";
import { buildBusinessRegistryPlan } from "./plans/business.js";

export type { QueryExecutionContext, QueryPlan, QueryStep } from "./planner-core.js";

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

const getGeocodeRecord = (
  context: QueryExecutionContext,
  stepId: string,
  expectedPostalCode?: string,
): Readonly<Record<string, unknown>> => {
  const records = getStepRecords(context, stepId);
  if (records.length === 0) {
    throw dependencyError(
      "The workflow could not resolve a geocode match from the previous step.",
      "Call sg_onemap_geocode directly with a more explicit Singapore address or postal code.",
    );
  }

  if (expectedPostalCode === undefined) {
    return records[0]!;
  }

  const record = records.find((candidate) => candidate["postal"] === expectedPostalCode);
  if (record === undefined) {
    throw dependencyError(
      `Workflow step ${stepId} did not return an exact postal-code match for ${expectedPostalCode}.`,
      "Call sg_onemap_geocode directly and choose the correct record, or provide explicit coordinates to sg_onemap_route.",
    );
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

const getLatLngFromGeocode = (
  context: QueryExecutionContext,
  stepId: string,
  expectedPostalCode?: string,
): { lat: number; lng: number } => {
  const record = getGeocodeRecord(context, stepId, expectedPostalCode);
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

const CIVIC_PLANNING_AREA_RADIUS_KM = 5;

const toCivicSearchInput = (
  tool: string,
  params: Readonly<Record<string, unknown>>,
  location: Readonly<Record<string, unknown>>,
): Readonly<Record<string, unknown>> => {
  const common = {
    ...(params["name"] !== undefined ? { name: params["name"] } : {}),
    ...location,
  };

  switch (tool) {
    case "sg_pa_community_outlets":
      return {
        ...common,
        ...(params["type"] !== undefined ? { type: params["type"] } : {}),
      };
    case "sg_sportsg_facilities":
      return {
        ...common,
        ...(params["facilityType"] !== undefined ? { facilityType: params["facilityType"] } : {}),
      };
    case "sg_ecda_childcare_centres":
      return {
        ...common,
        ...(params["centreType"] !== undefined ? { centreType: params["centreType"] } : {}),
        ...(params["operatorType"] !== undefined ? { operatorType: params["operatorType"] } : {}),
        ...(params["hasVacancy"] !== undefined ? { hasVacancy: params["hasVacancy"] } : {}),
      };
    case "sg_msf_student_care_services":
      return {
        ...common,
        ...(params["auditStatus"] !== undefined ? { auditStatus: params["auditStatus"] } : {}),
        ...(params["scfaOnly"] !== undefined ? { scfaOnly: params["scfaOnly"] } : {}),
      };
    default:
      return common;
  }
};

const buildCivicDiscoveryPlan = (
  tool: string | undefined,
  params: Readonly<Record<string, unknown>>,
): QueryPlan => {
  if (tool === undefined) {
    return buildBlockedPlan(
      {
        workflow: "civic_discovery",
        intent: "civic",
        confidence: 0.7,
        apis: [],
        steps: [],
      },
      [
        createBlocker(
          "directory",
          "Specify which civic directory you want to search before sg_query can build a bounded civic workflow.",
          "sg://recipes",
          {},
          "Find a family service centre near 560230",
        ),
      ],
      "sg_query could not determine which civic directory to search.",
      "Specify whether you want family services, student care, social service offices, community outlets, residents' network centres, SportSG facilities, or childcare centres.",
    );
  }

  const name = typeof params["name"] === "string" ? params["name"] : undefined;
  const postalCode = typeof params["postalCode"] === "string" ? params["postalCode"] : undefined;
  const planningArea = typeof params["planningArea"] === "string" ? params["planningArea"] : undefined;
  const rawAddress = typeof params["address"] === "string" ? params["address"] : undefined;
  const address = rawAddress !== undefined
    && planningArea !== undefined
    && rawAddress.trim().toLowerCase() === planningArea.trim().toLowerCase()
    ? undefined
    : rawAddress;
  const lat = typeof params["lat"] === "number" ? params["lat"] : undefined;
  const lng = typeof params["lng"] === "number" ? params["lng"] : undefined;

  if (lat !== undefined && lng !== undefined) {
    return {
      supported: true,
      workflow: "civic_discovery",
      intent: "civic",
      confidence: 0.88,
      apis: [tool.replace(/^sg_/, "").split("_")[0]!],
      steps: [
        {
          id: "civic_search",
          purpose: "Search the civic directory near the supplied coordinates.",
          tool,
          input: toCivicSearchInput(tool, params, {
            lat,
            lng,
            radiusKm: DEFAULT_CIVIC_RADIUS_KM,
          }),
        },
      ],
    };
  }

  const locationHint = postalCode ?? address ?? planningArea;
  const locationHintLower = locationHint?.toLowerCase().trim();
  const nonResolvableHint = locationHintLower !== undefined
    && ["me", "here", "near me", "this address", "nearby"].includes(locationHintLower);

  if (locationHint !== undefined && !nonResolvableHint) {
    const radiusKm = planningArea !== undefined && postalCode === undefined && address === undefined
      ? CIVIC_PLANNING_AREA_RADIUS_KM
      : DEFAULT_CIVIC_RADIUS_KM;
    return {
      supported: true,
      workflow: "civic_discovery",
      intent: "civic",
      confidence: 0.88,
      apis: ["onemap", tool.replace(/^sg_/, "").split("_")[0]!],
      steps: [
        {
          id: "civic_geocode",
          purpose: "Resolve the civic location hint to coordinates.",
          tool: "sg_onemap_geocode",
          input: { searchVal: locationHint },
        },
        {
          id: "civic_search",
          purpose: "Search the civic directory near the resolved location.",
          tool,
          input: toCivicSearchInput(tool, params, {
            lat: "<from civic_geocode.records[0].lat>",
            lng: "<from civic_geocode.records[0].lng>",
            radiusKm,
          }),
          dependsOn: ["civic_geocode"],
          resolveInput: (context) => {
            const resolved = getLatLngFromGeocode(context, "civic_geocode", postalCode);
            return toCivicSearchInput(tool, params, {
              lat: resolved.lat,
              lng: resolved.lng,
              radiusKm,
            });
          },
        },
      ],
    };
  }

  if (name !== undefined) {
    return {
      supported: true,
      workflow: "civic_discovery",
      intent: "civic",
      confidence: 0.84,
      apis: [tool.replace(/^sg_/, "").split("_")[0]!],
      steps: [
        {
          id: "civic_search",
          purpose: "Search the civic directory by exact facility name.",
          tool,
          input: toCivicSearchInput(tool, params, {}),
        },
      ],
    };
  }

  return buildBlockedPlan(
    {
      workflow: "civic_discovery",
      intent: "civic",
      confidence: 0.76,
      apis: [tool.replace(/^sg_/, "").split("_")[0]!],
      steps: [
        {
          id: "civic_search",
          purpose: "Search the civic directory once the missing location or exact name is supplied.",
          tool,
          input: toCivicSearchInput(tool, params, {}),
        },
      ],
    },
    [
      createBlocker(
        "postalCode",
        "Provide a Singapore postal code to run a bounded proximity search.",
        "sg_onemap_geocode",
        { searchVal: "560230" },
        "Find a family service centre near 560230",
      ),
      createBlocker(
        "address",
        "Provide a Singapore address to run a bounded proximity search.",
        "sg_onemap_geocode",
        { searchVal: "1 Raffles Place" },
        "Find a social service office near 1 Raffles Place",
      ),
      createBlocker(
        "name",
        "Provide an exact quoted facility name to run a direct civic lookup.",
        tool,
        { name: "Social Service Office @ Queenstown" },
        "Find a social service office named \"Social Service Office @ Queenstown\"",
      ),
    ],
    "sg_query recognized a civic-discovery request, but it still needs a Singapore postal code, planning area, address, coordinates, or an explicit facility name.",
    "Try prompts like \"Find a family service centre near 560230\" or \"Find a social service office named \\\"Social Service Office @ Queenstown\\\"\".",
  );
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

  return buildBlockedPlan(
    {
      workflow: "demographic_profile",
      intent: "demographic",
      confidence: 0.72,
      apis: ["onemap", "ura"],
      steps: [
        {
          id: "demographic_age",
          purpose: "Fetch age-group demographics once the missing location is supplied.",
          tool: "sg_onemap_population",
          input: {
            planningArea: "<required>",
            dataType: "getPopulationAgeGroup",
          },
        },
        {
          id: "demographic_income",
          purpose: "Fetch household income distribution once the missing location is supplied.",
          tool: "sg_onemap_population",
          input: {
            planningArea: "<required>",
            dataType: "getHouseholdMonthlyIncomeWork",
          },
        },
      ],
    },
    [
      createBlocker(
        "planningArea",
        "Provide a planning area to request demographic data directly.",
        "sg_onemap_population",
        { planningArea: "Tampines", dataType: "getPopulationAgeGroup" },
        "Demographic profile for Tampines",
      ),
      createBlocker(
        "postalCode",
        "Provide a Singapore postal code so sg_query can resolve the planning area first.",
        "sg_onemap_geocode",
        { searchVal: "168742" },
        "Demographic profile for postal code 168742",
      ),
    ],
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

  return buildBlockedPlan(
    {
      workflow: "property_brief",
      intent: "property",
      confidence: 0.76,
      apis: includeHdb ? ["onemap", "ura", "hdb"] : ["onemap", "ura"],
      steps: [
        {
          id: "property_brief",
          purpose: "Build a location and property brief once the missing area hint is supplied.",
          tool: "sg_property_brief",
          input: {
            propertyType,
            ...(includeHdb ? {} : { includeEnvironment: false }),
          },
        },
      ],
    },
    [
      createBlocker(
        "planningArea",
        "Provide a planning area to build the property brief directly.",
        "sg_property_brief",
        { planningArea: "Bedok", propertyType },
        "Property due diligence for Bedok HDB resale",
      ),
      createBlocker(
        "postalCode",
        "Provide a Singapore postal code so sg_query can resolve the area first.",
        "sg_property_brief",
        { postalCode: "460123", propertyType },
        "Property due diligence for postal code 460123",
      ),
    ],
    "sg_query needs a planning area or Singapore postal code to run property or regulatory diligence.",
    "Provide a planning area like Bedok, or give a postal code and let sg_query resolve the area first.",
  );
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

const buildRoutePlan = (
  params: Readonly<Record<string, unknown>>,
): QueryPlan => {
  const routeType = (typeof params["routeType"] === "string" ? params["routeType"] : "pt") as "walk" | "drive" | "pt" | "cycle";
  const startLat = typeof params["startLat"] === "number" ? params["startLat"] : undefined;
  const startLng = typeof params["startLng"] === "number" ? params["startLng"] : undefined;
  const endLat = typeof params["endLat"] === "number" ? params["endLat"] : undefined;
  const endLng = typeof params["endLng"] === "number" ? params["endLng"] : undefined;
  const originPostalCode =
    typeof params["originPostalCode"] === "string" ? params["originPostalCode"] : undefined;
  const destinationPostalCode =
    typeof params["destinationPostalCode"] === "string" ? params["destinationPostalCode"] : undefined;

  if (
    startLat !== undefined
    && startLng !== undefined
    && endLat !== undefined
    && endLng !== undefined
  ) {
    return {
      supported: true,
      workflow: "route_plan",
      intent: "geospatial",
      confidence: 0.9,
      apis: ["onemap"],
      steps: [
        {
          id: "route_plan",
          purpose: "Build directions between the supplied coordinate pairs.",
          tool: "sg_onemap_route",
          input: {
            startLat,
            startLng,
            endLat,
            endLng,
            routeType,
          },
        },
      ],
    };
  }

  if (originPostalCode !== undefined && destinationPostalCode !== undefined) {
    return {
      supported: true,
      workflow: "route_plan",
      intent: "geospatial",
      confidence: 0.88,
      apis: ["onemap"],
      steps: [
        {
          id: "route_origin_geocode",
          purpose: "Resolve the origin postal code to coordinates.",
          tool: "sg_onemap_geocode",
          input: { searchVal: originPostalCode },
        },
        {
          id: "route_destination_geocode",
          purpose: "Resolve the destination postal code to coordinates.",
          tool: "sg_onemap_geocode",
          input: { searchVal: destinationPostalCode },
        },
        {
          id: "route_plan",
          purpose: "Build directions between the resolved origin and destination.",
          tool: "sg_onemap_route",
          input: {
            startLat: "<from route_origin_geocode.records[0].lat>",
            startLng: "<from route_origin_geocode.records[0].lng>",
            endLat: "<from route_destination_geocode.records[0].lat>",
            endLng: "<from route_destination_geocode.records[0].lng>",
            routeType,
          },
          dependsOn: ["route_origin_geocode", "route_destination_geocode"],
          resolveInput: (context) => {
            const origin = getLatLngFromGeocode(context, "route_origin_geocode", originPostalCode);
            const destination = getLatLngFromGeocode(context, "route_destination_geocode", destinationPostalCode);
            return {
              startLat: origin.lat,
              startLng: origin.lng,
              endLat: destination.lat,
              endLng: destination.lng,
              routeType,
            };
          },
        },
      ],
    };
  }

  return buildBlockedPlan(
    {
      workflow: "route_plan",
      intent: "geospatial",
      confidence: 0.72,
      apis: ["onemap"],
      steps: [
        {
          id: "route_origin_geocode",
          purpose: "Resolve the origin postal code or address to coordinates.",
          tool: "sg_onemap_geocode",
          input: { searchVal: "<required origin>" },
        },
        {
          id: "route_destination_geocode",
          purpose: "Resolve the destination postal code or address to coordinates.",
          tool: "sg_onemap_geocode",
          input: { searchVal: "<required destination>" },
        },
        {
          id: "route_plan",
          purpose: "Build directions between the resolved origin and destination.",
          tool: "sg_onemap_route",
          input: {
            startLat: "<required>",
            startLng: "<required>",
            endLat: "<required>",
            endLng: "<required>",
            routeType,
          },
        },
      ],
    },
    [
      createBlocker(
        "originPostalCode",
        "Provide a Singapore postal code or explicit coordinates for the route origin.",
        "sg_onemap_geocode",
        { searchVal: "049178" },
        "Walk from 049178 to 048616",
      ),
      createBlocker(
        "destinationPostalCode",
        "Provide a Singapore postal code or explicit coordinates for the route destination.",
        "sg_onemap_geocode",
        { searchVal: "048616" },
        "Walk from 049178 to 048616",
      ),
    ],
    "sg_query needs either two coordinate pairs or two Singapore postal codes to plan a route.",
    "Ask for directions between two postal codes like 018989 and 048616, or call sg_onemap_route directly with startLat/startLng/endLat/endLng.",
  );
};

const buildDirectToolPlan = (query: string): QueryPlan => {
  const intent = classifyIntent(query);
  if (intent.tool === undefined) {
    return buildDatasetDiscoveryPlan(query);
  }

  const resolved = resolveToolInput(intent, query);

  if (resolved.tool === "sg_lta_bus_arrivals" && resolved.input["busStopCode"] === undefined) {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "busStopCode",
          "Provide a 5-digit Singapore bus stop code for live arrival timings.",
          "sg_lta_bus_arrivals",
          { busStopCode: "83139", serviceNo: "851" },
          "Bus arrivals at stop 83139",
        ),
      ],
      "sg_query needs a 5-digit Singapore bus stop code for bus-arrival lookups.",
      "Call sg_lta_bus_arrivals directly with busStopCode and optionally serviceNo.",
    );
  }

  if (resolved.tool === "sg_onemap_population" && resolved.input["planningArea"] === "") {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "planningArea",
          "Provide a planning area to request demographic data directly.",
          "sg_onemap_population",
          { planningArea: "Tampines", dataType: "getPopulationAgeGroup" },
          "Population profile for Tampines",
        ),
      ],
      "sg_query needs a planning area name before it can request demographic data directly.",
      "Provide a planning area, or ask for a demographic profile with a postal code instead.",
    );
  }

  if (
    resolved.tool === "sg_onemap_reverse_geocode"
    && (resolved.input["lat"] === undefined || resolved.input["lng"] === undefined)
  ) {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "lat",
          "Provide a latitude value for reverse geocoding.",
          "sg_onemap_reverse_geocode",
          { lat: 1.284, lng: 103.851 },
          "Reverse geocode 1.2840, 103.8510",
        ),
        createBlocker(
          "lng",
          "Provide a longitude value for reverse geocoding.",
          "sg_onemap_reverse_geocode",
          { lat: 1.284, lng: 103.851 },
          "Reverse geocode 1.2840, 103.8510",
        ),
      ],
      "sg_query needs one latitude and longitude pair for reverse geocoding.",
      "Ask for the address at coordinates like 1.2840, 103.8510, or call sg_onemap_reverse_geocode directly.",
    );
  }

  if (
    resolved.tool === "sg_onemap_route"
    && (
      resolved.input["startLat"] === undefined
      || resolved.input["startLng"] === undefined
      || resolved.input["endLat"] === undefined
      || resolved.input["endLng"] === undefined
    )
  ) {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "startLat",
          "Provide the route origin latitude.",
          "sg_onemap_route",
          { startLat: 1.2864, startLng: 103.8537, endLat: 1.284, endLng: 103.851, routeType: "walk" },
          "Walk from 049178 to 048616",
        ),
        createBlocker(
          "startLng",
          "Provide the route origin longitude.",
          "sg_onemap_route",
          { startLat: 1.2864, startLng: 103.8537, endLat: 1.284, endLng: 103.851, routeType: "walk" },
          "Walk from 049178 to 048616",
        ),
        createBlocker(
          "endLat",
          "Provide the route destination latitude.",
          "sg_onemap_route",
          { startLat: 1.2864, startLng: 103.8537, endLat: 1.284, endLng: 103.851, routeType: "walk" },
          "Walk from 049178 to 048616",
        ),
        createBlocker(
          "endLng",
          "Provide the route destination longitude.",
          "sg_onemap_route",
          { startLat: 1.2864, startLng: 103.8537, endLat: 1.284, endLng: 103.851, routeType: "walk" },
          "Walk from 049178 to 048616",
        ),
      ],
      "sg_query needs both a start and end location before it can call sg_onemap_route directly.",
      "Provide two coordinate pairs, or ask for directions between two Singapore postal codes so sg_query can geocode them first.",
    );
  }

  if (
    resolved.tool === "sg_onemap_convert_coords"
    && (
      resolved.input["from"] === undefined
      || resolved.input["x"] === undefined
      || resolved.input["y"] === undefined
    )
  ) {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "from",
          "Provide the source coordinate system so the converter knows what to transform from.",
          "sg_onemap_convert_coords",
          { from: "SVY21", x: 28001, y: 38744 },
          "Convert SVY21 28001 38744 to WGS84",
        ),
        createBlocker(
          "x",
          "Provide the first coordinate value for conversion.",
          "sg_onemap_convert_coords",
          { from: "SVY21", x: 28001, y: 38744 },
          "Convert SVY21 28001 38744 to WGS84",
        ),
        createBlocker(
          "y",
          "Provide the second coordinate value for conversion.",
          "sg_onemap_convert_coords",
          { from: "SVY21", x: 28001, y: 38744 },
          "Convert SVY21 28001 38744 to WGS84",
        ),
      ],
      "sg_query needs a source coordinate system plus one coordinate pair for conversion.",
      "Ask to convert SVY21 28001 38744 to WGS84, or convert WGS84 1.2840, 103.8510 to SVY21.",
    );
  }

  if (
    resolved.tool === "sg_ura_planning_area"
    && resolved.input["planningArea"] === undefined
    && (resolved.input["lat"] === undefined || resolved.input["lng"] === undefined)
  ) {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "planningArea",
          "Provide a planning area for a direct zoning lookup.",
          "sg_ura_planning_area",
          { planningArea: "Bedok" },
          "Show the master plan zoning for Bedok",
        ),
        createBlocker(
          "lat",
          "Provide latitude and longitude for a coordinate-based zoning lookup.",
          "sg_ura_planning_area",
          { lat: 1.3521, lng: 103.8198 },
          "Show the master plan zoning at 1.3521, 103.8198",
        ),
      ],
      "sg_query needs a planning area name or coordinates for a URA zoning lookup.",
      "Call sg_ura_planning_area directly with planningArea, or provide latitude and longitude.",
    );
  }

  if (resolved.tool === "sg_cea_salespersons" && Object.keys(resolved.input).length === 0) {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "registrationNo",
          "Provide a salesperson registration number for an exact CEA lookup.",
          "sg_cea_salespersons",
          { registrationNo: "R123456A" },
          "Show CEA record for registration number R123456A",
        ),
        createBlocker(
          "estateAgentName",
          "Provide an estate agent name for a directory lookup.",
          "sg_cea_salespersons",
          { estateAgentName: "ERA REALTY NETWORK PTE LTD" },
          "Show CEA record for ERA REALTY NETWORK PTE LTD",
        ),
      ],
      "sg_query needs a salesperson, registration number, estate agent, or estate-agent licence number for CEA lookups.",
      "Provide a salesperson or estate-agent identifier, or call sg_cea_salespersons directly.",
    );
  }

  if (resolved.tool === "sg_bca_licensed_builders" && Object.keys(resolved.input).length === 0) {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "companyName",
          "Provide a company name for the licensed-builder lookup.",
          "sg_bca_licensed_builders",
          { companyName: "ABC CONSTRUCTION PTE LTD" },
          "Show BCA licensed builder record for ABC CONSTRUCTION PTE LTD",
        ),
        createBlocker(
          "uenNo",
          "Provide a UEN for the licensed-builder lookup.",
          "sg_bca_licensed_builders",
          { uenNo: "201912345K" },
          "Show BCA licensed builder record for UEN 201912345K",
        ),
      ],
      "sg_query needs a company, UEN, or builder class identifier for BCA licensed-builder lookups.",
      "Provide a company name, UEN, or builder class code, or call sg_bca_licensed_builders directly.",
    );
  }

  if (resolved.tool === "sg_bca_registered_contractors" && Object.keys(resolved.input).length === 0) {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "companyName",
          "Provide a company name for the registered-contractor lookup.",
          "sg_bca_registered_contractors",
          { companyName: "ABC CONSTRUCTION PTE LTD" },
          "Show BCA registered contractor record for ABC CONSTRUCTION PTE LTD",
        ),
        createBlocker(
          "workhead",
          "Provide a workhead when you want to filter the contractor register more tightly.",
          "sg_bca_registered_contractors",
          { workhead: "CW01", grade: "C3" },
          "Show BCA registered contractors for workhead CW01 grade C3",
        ),
      ],
      "sg_query needs a company, UEN, workhead, or grade for BCA registered-contractor lookups.",
      "Provide a company name, UEN, workhead, or grade, or call sg_bca_registered_contractors directly.",
    );
  }

  if (resolved.tool === "sg_acra_entities" && Object.keys(resolved.input).length === 0) {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "entityName",
          "Provide a company or entity name for the ACRA lookup.",
          "sg_acra_entities",
          { entityName: "ABC CONSTRUCTION PTE LTD" },
          "Show ACRA record for ABC CONSTRUCTION PTE LTD",
        ),
        createBlocker(
          "uen",
          "Provide a UEN for an exact ACRA lookup.",
          "sg_acra_entities",
          { uen: "201912345K" },
          "Show ACRA record for UEN 201912345K",
        ),
      ],
      "sg_query needs an entity name or UEN for ACRA lookups.",
      "Provide an explicit company name or UEN, or call sg_acra_entities directly.",
    );
  }

  if (resolved.tool === "sg_boa_architects" && Object.keys(resolved.input).length === 0) {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "name",
          "Provide an architect name for a BOA architect lookup.",
          "sg_boa_architects",
          { name: "ALICE TAN" },
          "Show BOA architect record for ALICE TAN",
        ),
        createBlocker(
          "registrationNo",
          "Provide a BOA registration number for an exact lookup.",
          "sg_boa_architects",
          { registrationNo: "A1234" },
          "Show BOA architect record for registration number A1234",
        ),
      ],
      "sg_query needs an architect name, registration number, or architecture firm name for BOA architect lookups.",
      "Provide an explicit architect identifier, or call sg_boa_architects directly.",
    );
  }

  if (resolved.tool === "sg_boa_architecture_firms" && Object.keys(resolved.input).length === 0) {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "firmName",
          "Provide an architecture firm name for a BOA firm lookup.",
          "sg_boa_architecture_firms",
          { firmName: "DESIGN LAB PTE LTD" },
          "Show BOA architecture firm record for DESIGN LAB PTE LTD",
        ),
      ],
      "sg_query needs a firm name, email, or phone number for BOA architecture-firm lookups.",
      "Provide an explicit firm identifier, or call sg_boa_architecture_firms directly.",
    );
  }

  if (resolved.tool === "sg_hsa_licensed_pharmacies" && Object.keys(resolved.input).length === 0) {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "pharmacyName",
          "Provide a pharmacy name for an HSA pharmacy lookup.",
          "sg_hsa_licensed_pharmacies",
          { pharmacyName: "A.M. Pharmacy Pte Ltd" },
          "Show HSA licensed pharmacy record for A.M. Pharmacy Pte Ltd",
        ),
        createBlocker(
          "postalCode",
          "Provide a postal code to narrow the HSA pharmacy lookup.",
          "sg_hsa_licensed_pharmacies",
          { postalCode: "238841" },
          "Show HSA licensed pharmacy at postal code 238841",
        ),
      ],
      "sg_query needs a pharmacy name, pharmacist, address, or postal code for HSA pharmacy lookups.",
      "Provide a pharmacy identifier, or call sg_hsa_licensed_pharmacies directly.",
    );
  }

  if (resolved.tool === "sg_hsa_health_product_licensees" && Object.keys(resolved.input).length === 0) {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "companyName",
          "Provide a company name for an HSA health-product licensee lookup.",
          "sg_hsa_health_product_licensees",
          { companyName: "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD." },
          "Show HSA health-product licence rows for ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.",
        ),
      ],
      "sg_query needs a company or licence filter for HSA health-product licensee lookups.",
      "Provide a company or licence filter, or call sg_hsa_health_product_licensees directly.",
    );
  }

  if (
    resolved.tool === "sg_hlb_hotels"
    && resolved.input["name"] === undefined
    && resolved.input["postalCode"] === undefined
    && resolved.input["keeperName"] === undefined
    && (resolved.input["lat"] === undefined || resolved.input["lng"] === undefined)
  ) {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "name",
          "Provide a hotel name for an HLB hotel lookup.",
          "sg_hlb_hotels",
          { name: "RAFFLES HOTEL SINGAPORE" },
          "Show HLB hotel record for RAFFLES HOTEL SINGAPORE",
        ),
        createBlocker(
          "keeperName",
          "Provide a keeper or operator name for an HLB hotel lookup.",
          "sg_hlb_hotels",
          { keeperName: "RAFFLES HOTEL SINGAPORE" },
          "Show HLB hotel records kept by RAFFLES HOTEL SINGAPORE",
        ),
      ],
      "sg_query needs a hotel name, keeper name, postal code, or coordinates for HLB hotel lookups.",
      "Provide a hotel identifier, or call sg_hlb_hotels directly.",
    );
  }

  if (resolved.tool === "sg_datagov_resources" && resolved.input["datasetId"] === undefined) {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "datasetId",
          "Provide a data.gov.sg datasetId before inspecting resource metadata.",
          "sg_datagov_resources",
          { datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc" },
          "Inspect resources for dataset d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
        ),
      ],
      "sg_query needs a data.gov.sg datasetId like d_8b84c4ee58e3cfc0ece0d773c8ca6abc to inspect resource metadata.",
      "Call sg_datagov_resources directly with datasetId, or use sg_datagov_search first to discover a dataset ID.",
    );
  }

  if (resolved.tool === "sg_datagov_rows" && resolved.input["datasetId"] === undefined) {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "datasetId",
          "Provide a data.gov.sg datasetId before reading bounded rows.",
          "sg_datagov_rows",
          { datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc", limit: 5 },
          "Read rows from dataset d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
        ),
      ],
      "sg_query needs a data.gov.sg datasetId like d_8b84c4ee58e3cfc0ece0d773c8ca6abc to read bounded rows.",
      "Call sg_datagov_rows directly with datasetId or resourceId, or inspect sg_datagov_resources first.",
    );
  }

  if (resolved.tool === "sg_singstat_table" && resolved.input["tableId"] === undefined) {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "tableId",
          "Provide a SingStat table ID before reading a table directly.",
          "sg_singstat_table",
          { tableId: "M015631" },
          "Show SingStat table M015631",
        ),
      ],
      "sg_query needs a SingStat table ID like M015631 before it can read a table directly.",
      "Ask sg_singstat_search for matching datasets first, then call sg_singstat_table with the tableId you want.",
    );
  }

  if (
    resolved.tool === "sg_singstat_timeseries"
    && (
      resolved.input["tableId"] === undefined
      || resolved.input["indicator"] === undefined
      || resolved.input["startYear"] === undefined
      || resolved.input["endYear"] === undefined
    )
  ) {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "tableId",
          "Provide a SingStat table ID for the time-series read.",
          "sg_singstat_timeseries",
          { tableId: "M015631", indicator: "GDP at current market prices", startYear: 2020, endYear: 2025 },
          "Time series for table M015631 indicator \"GDP at current market prices\" from 2020 to 2025",
        ),
        createBlocker(
          "indicator",
          "Provide the indicator name to read from the table.",
          "sg_singstat_timeseries",
          { tableId: "M015631", indicator: "GDP at current market prices", startYear: 2020, endYear: 2025 },
          "Time series for table M015631 indicator \"GDP at current market prices\" from 2020 to 2025",
        ),
        createBlocker(
          "startYear",
          "Provide the start year for the time-series range.",
          "sg_singstat_timeseries",
          { tableId: "M015631", indicator: "GDP at current market prices", startYear: 2020, endYear: 2025 },
          "Time series for table M015631 indicator \"GDP at current market prices\" from 2020 to 2025",
        ),
        createBlocker(
          "endYear",
          "Provide the end year for the time-series range.",
          "sg_singstat_timeseries",
          { tableId: "M015631", indicator: "GDP at current market prices", startYear: 2020, endYear: 2025 },
          "Time series for table M015631 indicator \"GDP at current market prices\" from 2020 to 2025",
        ),
      ],
      "sg_query needs tableId, indicator, startYear, and endYear for SingStat time-series reads.",
      "Ask for a quoted indicator and a year range, for example: time series for table M015631 indicator \"GDP at current market prices\" from 2020 to 2025.",
    );
  }

  if (
    resolved.tool === "sg_transit_reliability"
    && (resolved.input["originStopId"] === undefined || resolved.input["destinationStopId"] === undefined)
  ) {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "originStopId",
          "Provide an origin 5-digit bus stop code for reliability estimation.",
          "sg_transit_reliability",
          { originStopId: "83139", destinationStopId: "76059", horizonMinutes: 45 },
          "Transit reliability from stop 83139 to stop 76059",
        ),
        createBlocker(
          "destinationStopId",
          "Provide a destination 5-digit bus stop code for reliability estimation.",
          "sg_transit_reliability",
          { originStopId: "83139", destinationStopId: "76059", horizonMinutes: 45 },
          "Transit reliability from stop 83139 to stop 76059",
        ),
      ],
      "sg_query needs both originStopId and destinationStopId for transit reliability reads.",
      "Call sg_transit_reliability directly with two stop codes, or start with sg_transit_ops_brief for a network-level view.",
    );
  }

  if (
    resolved.tool === "sg_transit_transfer_risk"
    && (
      resolved.input["fromServiceNo"] === undefined
      || resolved.input["toServiceNo"] === undefined
      || resolved.input["transferStopId"] === undefined
    )
  ) {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "fromServiceNo",
          "Provide the incoming bus service number for transfer-risk estimation.",
          "sg_transit_transfer_risk",
          { fromServiceNo: "851", toServiceNo: "72", transferStopId: "83139" },
          "Transfer risk from service 851 to 72 at stop 83139",
        ),
        createBlocker(
          "toServiceNo",
          "Provide the outbound bus service number for transfer-risk estimation.",
          "sg_transit_transfer_risk",
          { fromServiceNo: "851", toServiceNo: "72", transferStopId: "83139" },
          "Transfer risk from service 851 to 72 at stop 83139",
        ),
        createBlocker(
          "transferStopId",
          "Provide the 5-digit transfer stop code for transfer-risk estimation.",
          "sg_transit_transfer_risk",
          { fromServiceNo: "851", toServiceNo: "72", transferStopId: "83139" },
          "Transfer risk from service 851 to 72 at stop 83139",
        ),
      ],
      "sg_query needs fromServiceNo, toServiceNo, and transferStopId for transfer-risk reads.",
      "Call sg_transit_transfer_risk directly with both services and a transfer stop code, or use sg_transit_ops_brief for a broader snapshot.",
    );
  }

  if (resolved.tool === "sg_transit_objective_plan" && resolved.input["objective"] === undefined) {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "objective",
          "Provide one objective: minimize_delay, maximize_accessibility, minimize_transfer_risk, or balanced.",
          "sg_transit_objective_plan",
          { objective: "balanced" },
          "Transit objective plan with objective balanced",
        ),
      ],
      "sg_query needs an objective before it can generate a transit objective plan.",
      "Call sg_transit_objective_plan with objective set to minimize_delay, maximize_accessibility, minimize_transfer_risk, or balanced.",
    );
  }

  if (
    resolved.tool === "sg_transit_counterfactual_simulate"
    && (resolved.input["baseRequest"] === undefined || resolved.input["scenarios"] === undefined)
  ) {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "baseRequest",
          "Provide the baseline objective-plan request to simulate against.",
          "sg_transit_counterfactual_simulate",
          { baseRequest: { objective: "balanced", stopIds: ["83139", "76059"] }, scenarios: [{ id: "scenario-1", requestPatch: { objective: "minimize_delay" } }] },
          "Run a transit counterfactual simulation from a balanced baseline",
        ),
        createBlocker(
          "scenarios",
          "Provide one or more scenario patches to compare with the baseline request.",
          "sg_transit_counterfactual_simulate",
          { baseRequest: { objective: "balanced", stopIds: ["83139", "76059"] }, scenarios: [{ id: "scenario-1", requestPatch: { objective: "minimize_delay" } }] },
          "Run a transit counterfactual simulation from a balanced baseline",
        ),
      ],
      "sg_query needs baseRequest and scenarios for transit counterfactual simulation.",
      "Call sg_transit_counterfactual_simulate with a baseline request and at least one scenario patch.",
    );
  }

  if (resolved.tool === "sg_transit_policy_replay" && resolved.input["traceId"] === undefined) {
    return buildDirectToolBlockedPlan(
      "direct_tool",
      intent.intent,
      intent.confidence,
      intent.apis,
      resolved.tool,
      resolved.input,
      [
        createBlocker(
          "traceId",
          "Provide a traceId from sg_transit_policy_audit before replaying a policy trace.",
          "sg_transit_policy_replay",
          { traceId: "9cb737f3-d1b4-4b4e-9ec1-2f36e1f67f19" },
          "Replay transit policy trace 9cb737f3-d1b4-4b4e-9ec1-2f36e1f67f19",
        ),
      ],
      "sg_query needs a traceId for transit policy replay.",
      "Run sg_transit_policy_audit first to list trace IDs, then call sg_transit_policy_replay with one traceId.",
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

const extractAllPlanningAreas = (text: string): string[] => {
  const lower = text.toLowerCase();
  return PLANNING_AREAS.filter((area) => lower.includes(area)).map(toTitleCase);
};

type ComparisonMapping = { tool: string; paramKey: string };
const COMPARISON_TOOL_MAP: readonly { pattern: RegExp; mapping: ComparisonMapping }[] = [
  { pattern: /\bhdb|resale/i, mapping: { tool: "sg_hdb_resale_prices", paramKey: "town" } },
  { pattern: /\bproperty|housing|condo|private/i, mapping: { tool: "sg_property_brief", paramKey: "planningArea" } },
  { pattern: /\bcivic|facilities|community|nearby/i, mapping: { tool: "sg_civic_brief", paramKey: "address" } },
  { pattern: /\btransport|bus|mrt|train/i, mapping: { tool: "sg_transport_brief", paramKey: "busStopCode" } },
  { pattern: /\benvironment|weather|air|forecast/i, mapping: { tool: "sg_environment_brief", paramKey: "area" } },
];

const buildComparisonPlan = (query: string): QueryPlan | null => {
  const parts = query.split(/\s+(?:vs\.?|versus|compared?\s+to)\s+/i);
  if (parts.length !== 2) return null;
  const areas = extractAllPlanningAreas(query);
  if (areas.length !== 2) return null; // only support location-based comparison for now
  const matched = COMPARISON_TOOL_MAP.find((m) => m.pattern.test(query));
  const { tool, paramKey } = matched?.mapping ?? { tool: "sg_property_brief", paramKey: "planningArea" }; // default to property
  return {
    supported: true,
    workflow: "comparison",
    intent: "comparison",
    confidence: 0.85,
    apis: [],
    steps: [
      { id: "compare_a", purpose: `Fetch data for ${areas[0]}`, tool, input: { [paramKey]: areas[0], format: "json" } },
      { id: "compare_b", purpose: `Fetch data for ${areas[1]}`, tool, input: { [paramKey]: areas[1], format: "json" } },
    ],
  };
};

export const planQuery = (query: string): QueryPlan => {
  const lower = query.toLowerCase();
  const intent = classifyIntent(query);
  const isComparison = /compare|vs\.?|versus|between\s+.+\s+and\s+.+/i.test(lower);

  if (isComparison) {
    const comparisonPlan = buildComparisonPlan(lower);
    if (comparisonPlan !== null) return comparisonPlan;
  }

  switch (intent.workflow) {
    case "civic_discovery":
      return buildCivicDiscoveryPlan(intent.tool, intent.extractedParams);
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
    case "architecture_firm_diligence":
      return buildBusinessRegistryPlan(intent.extractedParams, {
        workflow: "architecture_firm_diligence",
        confidence: intent.confidence,
        defaultModules: ["acra"],
      });
    case "healthcare_supplier_diligence":
      return buildBusinessRegistryPlan(intent.extractedParams, {
        workflow: "healthcare_supplier_diligence",
        confidence: intent.confidence,
        defaultModules: ["acra"],
      });
    case "hotel_operator_lookup":
      return buildBusinessRegistryPlan(intent.extractedParams, {
        workflow: "hotel_operator_lookup",
        confidence: intent.confidence,
      });
    case "sector_scoped_business_diligence":
      return buildBusinessRegistryPlan(intent.extractedParams, {
        workflow: "sector_scoped_business_diligence",
        confidence: intent.confidence,
      });
    case "dataset_discovery":
      return buildDatasetDiscoveryPlan(query);
    case "demographic_profile":
      return buildDemographicProfilePlan(intent.extractedParams);
    case "transport_brief":
      return buildTransportBriefPlan(intent.extractedParams);
    case "environment_brief":
      return buildEnvironmentBriefPlan(intent.extractedParams);
    case "route_plan":
      return buildRoutePlan(intent.extractedParams);
    default:
      return buildDirectToolPlan(query);
  }
};
