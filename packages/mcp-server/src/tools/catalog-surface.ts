import {
  API_CATALOG,
  PLAYBOOK_CATALOG,
  RECIPE_CATALOG,
  WORKFLOW_CATALOG,
  type ApiCatalogEntry,
  type PlaybookCatalogEntry,
  type RecipeCatalogEntry,
  type WorkflowCatalogEntry,
} from "./catalog.js";
import type { RegisteredToolDefinition, ToolCatalogEntry } from "./tool-definition.js";
import { toToolCatalogEntry } from "./tool-definition.js";
import {
  COORDINATE_SYSTEMS,
  OUTPUT_FORMATS,
  PLANNING_AREAS,
  REGIONS,
  ROUTE_MODES,
  toTitleCase,
} from "../router/domain-constants.js";

export type PromptArgumentValue = string | number | undefined;
export type PromptArgumentValues = Readonly<Record<string, PromptArgumentValue>>;
export type PromptCompletionSource =
  | "planningArea"
  | "region"
  | "routeMode"
  | "outputFormat"
  | "coordinateSystem"
  | "communityOutletType"
  | "developmentChargeSector"
  | "pulseFocus";

export type PromptArgumentDefinition = {
  readonly name: string;
  readonly description: string;
  readonly kind: "string" | "number" | "enum";
  readonly required?: boolean;
  readonly enumValues?: readonly string[];
  readonly completionSource?: PromptCompletionSource;
};

export type PromptMetadata = {
  readonly args: readonly PromptArgumentDefinition[];
  readonly buildStarterPrompt: (args: PromptArgumentValues) => string;
  readonly buildPreferredEntrypointInput?: (args: PromptArgumentValues) => Readonly<Record<string, unknown>>;
};

export type NormalizedApiCatalogEntry = ApiCatalogEntry & { readonly id: string };
export type NormalizedWorkflowCatalogEntry = WorkflowCatalogEntry & { readonly id: string };
export type NormalizedRecipeCatalogEntry = RecipeCatalogEntry & {
  readonly id: string;
  readonly promptMetadata?: PromptMetadata;
};
export type NormalizedPlaybookCatalogEntry = PlaybookCatalogEntry & {
  readonly id: string;
  readonly promptMetadata?: PromptMetadata;
};

const slugify = (value: string): string => {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
};

const withCatalogIds = <T extends { readonly id?: string; readonly name: string }>(entries: readonly T[]): readonly (Omit<T, "id"> & { readonly id: string })[] => {
  return entries.map((entry) => ({
    ...entry,
    id: entry.id ?? slugify(entry.name),
  }));
};

const listToSentence = (values: readonly string[]): string => {
  if (values.length === 0) {
    return "";
  }
  if (values.length === 1) {
    return values[0]!;
  }
  if (values.length === 2) {
    return `${values[0]} and ${values[1]}`;
  }
  return `${values.slice(0, -1).join(", ")}, and ${values[values.length - 1]}`;
};

const renderOptionalOutputFormatHint = (args: PromptArgumentValues): string => {
  const format = typeof args["outputFormat"] === "string" ? args["outputFormat"] : null;
  return format === null ? "" : ` Return the final answer in ${format}.`;
};

const renderOptionalRegion = (args: PromptArgumentValues): string => {
  const region = typeof args["region"] === "string" ? args["region"] : null;
  return region === null ? "" : ` for Singapore's ${region} region`;
};

const renderBusinessLookupTarget = (args: PromptArgumentValues): string => {
  const uen = typeof args["uen"] === "string" ? args["uen"] : null;
  if (uen !== null && uen.trim() !== "") {
    return `UEN ${uen}`;
  }

  const registrationNo = typeof args["registrationNo"] === "string" ? args["registrationNo"] : null;
  if (registrationNo !== null && registrationNo.trim() !== "") {
    return `registration number ${registrationNo}`;
  }

  const entityName = typeof args["entityName"] === "string" ? args["entityName"] : null;
  return entityName === null ? "the target entity" : entityName;
};

const renderOptionalOutputFormatSentence = (args: PromptArgumentValues): string => {
  const hint = renderOptionalOutputFormatHint(args);
  return hint === "" ? "" : hint.trimStart();
};

const planningAreaEnum = PLANNING_AREAS.map((value) => toTitleCase(value));
const regionEnum = REGIONS.map((value) => toTitleCase(value));
const routeModeEnum = [...ROUTE_MODES];
const outputFormatEnum = [...OUTPUT_FORMATS];
const coordinateSystemEnum = [...COORDINATE_SYSTEMS];
const communityOutletTypeEnum = ["community_club", "passion_wave"] as const;
const developmentChargeSectorEnum = ["A", "B1", "B2", "C"] as const;

const RECIPE_PROMPT_METADATA: Readonly<Record<string, PromptMetadata>> = {
  postal_route: {
    args: [
      { name: "originPostalCode", description: "Origin postal code.", kind: "string", required: true },
      { name: "destinationPostalCode", description: "Destination postal code.", kind: "string", required: true },
      {
        name: "routeMode",
        description: `Travel mode. One of ${listToSentence(routeModeEnum)}.`,
        kind: "enum",
        required: true,
        enumValues: routeModeEnum,
        completionSource: "routeMode",
      },
    ],
    buildStarterPrompt: (args) => {
      return `${String(args["routeMode"]).toUpperCase() === "PT" ? "Take public transport" : `${toTitleCase(String(args["routeMode"]))}`} from ${args["originPostalCode"]} to ${args["destinationPostalCode"]}`;
    },
  },
  reverse_geocode: {
    args: [
      { name: "lat", description: "Latitude in WGS84.", kind: "number", required: true },
      { name: "lng", description: "Longitude in WGS84.", kind: "number", required: true },
    ],
    buildStarterPrompt: (args) => `Reverse geocode ${args["lat"]}, ${args["lng"]}`,
  },
  coordinate_conversion: {
    args: [
      {
        name: "from",
        description: `Source coordinate system. One of ${listToSentence(coordinateSystemEnum)}.`,
        kind: "enum",
        required: true,
        enumValues: coordinateSystemEnum,
        completionSource: "coordinateSystem",
      },
      { name: "x", description: "First coordinate component.", kind: "number", required: true },
      { name: "y", description: "Second coordinate component.", kind: "number", required: true },
    ],
    buildStarterPrompt: (args) => {
      const from = String(args["from"]);
      const target = from === "SVY21" ? "WGS84" : "SVY21";
      return `Convert ${from} ${args["x"]} ${args["y"]} to ${target}`;
    },
  },
  singstat_drilldown: {
    args: [
      { name: "category", description: "Optional SingStat browse category such as Transport or Economy.", kind: "string" },
      { name: "keyword", description: "Optional keyword when browsing by theme is insufficient.", kind: "string" },
      { name: "tableId", description: "Known SingStat table ID for direct drilldown.", kind: "string" },
      { name: "indicator", description: "Optional indicator name for time-series reads.", kind: "string" },
      { name: "startYear", description: "Optional start year for time-series reads.", kind: "number" },
      { name: "endYear", description: "Optional end year for time-series reads.", kind: "number" },
      {
        name: "outputFormat",
        description: `Preferred output format. One of ${listToSentence(outputFormatEnum)}.`,
        kind: "enum",
        enumValues: outputFormatEnum,
        completionSource: "outputFormat",
      },
    ],
    buildStarterPrompt: (args) => {
      const tableId = typeof args["tableId"] === "string" ? args["tableId"] : null;
      const indicator = typeof args["indicator"] === "string" ? args["indicator"] : null;
      if (tableId !== null && indicator !== null) {
        const yearWindow = typeof args["startYear"] === "number" || typeof args["endYear"] === "number"
          ? ` from ${args["startYear"] ?? "the earliest year"} to ${args["endYear"] ?? "the latest year"}`
          : "";
        return `Read SingStat table ${tableId} for indicator ${indicator}${yearWindow}.${renderOptionalOutputFormatHint(args)}`.trim();
      }
      if (tableId !== null) {
        return `Read SingStat table ${tableId}.${renderOptionalOutputFormatHint(args)}`.trim();
      }
      const category = typeof args["category"] === "string" ? args["category"] : null;
      const keyword = typeof args["keyword"] === "string" ? args["keyword"] : null;
      const target = category ?? keyword ?? "SingStat datasets";
      return `Browse SingStat ${target}.${renderOptionalOutputFormatHint(args)}`.trim();
    },
  },
  data_gov_collection_browse: {
    args: [
      { name: "collection", description: "Optional collection theme or title.", kind: "string" },
      { name: "keyword", description: "Optional keyword to continue into dataset search.", kind: "string" },
      { name: "datasetId", description: "Optional dataset ID for direct resource inspection.", kind: "string" },
      {
        name: "outputFormat",
        description: `Preferred output format. One of ${listToSentence(outputFormatEnum)}.`,
        kind: "enum",
        enumValues: outputFormatEnum,
        completionSource: "outputFormat",
      },
    ],
    buildStarterPrompt: (args) => {
      const datasetId = typeof args["datasetId"] === "string" ? args["datasetId"] : null;
      if (datasetId !== null) {
        return `Inspect data.gov.sg resources for dataset ${datasetId}.${renderOptionalOutputFormatHint(args)}`.trim();
      }
      const collection = typeof args["collection"] === "string" ? args["collection"] : null;
      const keyword = typeof args["keyword"] === "string" ? args["keyword"] : null;
      const target = collection ?? keyword ?? "data.gov collections";
      return `Browse ${target} on data.gov.sg.${renderOptionalOutputFormatHint(args)}`.trim();
    },
  },
  ura_development_charges: {
    args: [
      { name: "useGroup", description: "Optional URA use group such as Residential or Commercial.", kind: "string" },
      {
        name: "sector",
        description: `Optional development charge sector. One of ${listToSentence([...developmentChargeSectorEnum])}.`,
        kind: "enum",
        enumValues: [...developmentChargeSectorEnum],
        completionSource: "developmentChargeSector",
      },
      { name: "planningArea", description: "Optional planning area when the prompt is anchored on a location.", kind: "enum", enumValues: planningAreaEnum, completionSource: "planningArea" },
    ],
    buildStarterPrompt: (args) => {
      const useGroup = typeof args["useGroup"] === "string" ? args["useGroup"] : "development charge rates";
      const sector = typeof args["sector"] === "string" ? ` sector ${args["sector"]}` : "";
      const planningArea = typeof args["planningArea"] === "string" ? ` around ${args["planningArea"]}` : "";
      return `Show URA ${useGroup}${sector}${planningArea}`.trim();
    },
  },
  hdb_rental_check: {
    args: [
      { name: "town", description: "HDB town such as Bedok or Tampines.", kind: "string", required: true },
      { name: "flatType", description: "Flat type such as 3 ROOM or 4 ROOM.", kind: "string", required: true },
      { name: "startMonth", description: "Optional start month in YYYY-MM format.", kind: "string" },
      { name: "endMonth", description: "Optional end month in YYYY-MM format.", kind: "string" },
      {
        name: "outputFormat",
        description: `Preferred output format. One of ${listToSentence(outputFormatEnum)}.`,
        kind: "enum",
        enumValues: outputFormatEnum,
        completionSource: "outputFormat",
      },
    ],
    buildStarterPrompt: (args) => {
      const window = typeof args["startMonth"] === "string" || typeof args["endMonth"] === "string"
        ? ` between ${args["startMonth"] ?? "the earliest month"} and ${args["endMonth"] ?? "the latest month"}`
        : "";
      return `Show HDB rental prices in ${args["town"]} for ${args["flatType"]} flats${window}.${renderOptionalOutputFormatHint(args)}`.trim();
    },
  },
  demographic_profile: {
    args: [
      {
        name: "planningArea",
        description: "Planning area to profile.",
        kind: "enum",
        enumValues: planningAreaEnum,
        completionSource: "planningArea",
      },
      { name: "postalCode", description: "Postal code to resolve into a planning area.", kind: "string" },
      {
        name: "outputFormat",
        description: `Preferred output format. One of ${listToSentence(outputFormatEnum)}.`,
        kind: "enum",
        enumValues: outputFormatEnum,
        completionSource: "outputFormat",
      },
    ],
    buildStarterPrompt: (args) => {
      const planningArea = typeof args["planningArea"] === "string" ? args["planningArea"] : null;
      const postalCode = typeof args["postalCode"] === "string" ? args["postalCode"] : null;
      const location = planningArea ?? (postalCode === null ? "the supplied location" : `postal code ${postalCode}`);
      return `Population profile for ${location}${renderOptionalOutputFormatHint(args)}`;
    },
  },
  bus_stop_status: {
    args: [
      { name: "busStopCode", description: "5-digit bus stop code.", kind: "string", required: true },
      { name: "serviceNo", description: "Optional bus service number filter.", kind: "string" },
      {
        name: "outputFormat",
        description: `Preferred output format. One of ${listToSentence(outputFormatEnum)}.`,
        kind: "enum",
        enumValues: outputFormatEnum,
        completionSource: "outputFormat",
      },
    ],
    buildStarterPrompt: (args) => {
      const serviceNo = typeof args["serviceNo"] === "string" ? ` for service ${args["serviceNo"]}` : "";
      return `Bus arrivals at stop ${args["busStopCode"]}${serviceNo}.${renderOptionalOutputFormatHint(args)}`.trim();
    },
  },
  outdoor_event_check: {
    args: [
      {
        name: "planningArea",
        description: "Planning area to evaluate.",
        kind: "enum",
        enumValues: planningAreaEnum,
        completionSource: "planningArea",
      },
      {
        name: "region",
        description: "Singapore region to evaluate.",
        kind: "enum",
        enumValues: regionEnum,
        completionSource: "region",
      },
      {
        name: "outputFormat",
        description: `Preferred output format. One of ${listToSentence(outputFormatEnum)}.`,
        kind: "enum",
        enumValues: outputFormatEnum,
        completionSource: "outputFormat",
      },
    ],
    buildStarterPrompt: (args) => {
      const planningArea = typeof args["planningArea"] === "string" ? ` in ${args["planningArea"]}` : renderOptionalRegion(args);
      return `Environment brief${planningArea}.${renderOptionalOutputFormatHint(args)}`.trim();
    },
  },
  community_club_near_postal_code: {
    args: [
      { name: "postalCode", description: "Postal code to geocode before the proximity search.", kind: "string", required: true },
      {
        name: "type",
        description: `Optional PA outlet type. One of ${listToSentence([...communityOutletTypeEnum])}.`,
        kind: "enum",
        enumValues: [...communityOutletTypeEnum],
        completionSource: "communityOutletType",
      },
    ],
    buildStarterPrompt: (args) => {
      const targetType = typeof args["type"] === "string"
        ? args["type"].replaceAll("_", " ")
        : "community club";
      return `Find a ${targetType} near ${args["postalCode"]}`;
    },
  },
  family_service_near_postal_code: {
    args: [
      { name: "postalCode", description: "Postal code to geocode before the proximity search.", kind: "string", required: true },
    ],
    buildStarterPrompt: (args) => `Find a family service centre near ${args["postalCode"]}`,
  },
  student_care_near_planning_area: {
    args: [
      {
        name: "planningArea",
        description: "Planning area used to anchor the proximity search.",
        kind: "enum",
        required: true,
        enumValues: planningAreaEnum,
        completionSource: "planningArea",
      },
      { name: "auditStatus", description: "Optional audit status filter such as Grade A.", kind: "string" },
    ],
    buildStarterPrompt: (args) => {
      const auditStatus = typeof args["auditStatus"] === "string" ? ` with audit status ${args["auditStatus"]}` : "";
      return `Find student care centres near ${args["planningArea"]}${auditStatus}`;
    },
  },
  scfa_student_care_near_planning_area: {
    args: [
      {
        name: "planningArea",
        description: "Planning area used to anchor the proximity search.",
        kind: "enum",
        required: true,
        enumValues: planningAreaEnum,
        completionSource: "planningArea",
      },
      { name: "auditStatus", description: "Optional audit status filter such as Grade A.", kind: "string" },
    ],
    buildStarterPrompt: (args) => {
      const auditStatus = typeof args["auditStatus"] === "string" ? ` with audit status ${args["auditStatus"]}` : "";
      return `Find SCFA student care near ${args["planningArea"]}${auditStatus}`;
    },
  },
  social_service_office_near_address: {
    args: [
      { name: "address", description: "Address to geocode before the proximity search.", kind: "string", required: true },
    ],
    buildStarterPrompt: (args) => `Find a social service office near ${args["address"]}`,
  },
  sport_facility_near_planning_area: {
    args: [
      {
        name: "planningArea",
        description: "Planning area used to anchor the proximity search.",
        kind: "enum",
        required: true,
        enumValues: planningAreaEnum,
        completionSource: "planningArea",
      },
      { name: "facilityType", description: "Optional SportSG facility type hint such as swimming complex.", kind: "string" },
    ],
    buildStarterPrompt: (args) => {
      const facilityType = typeof args["facilityType"] === "string"
        ? args["facilityType"]
        : "SportSG facility";
      return `Find a ${facilityType} near ${args["planningArea"]}`;
    },
  },
  childcare_vacancy_near_planning_area: {
    args: [
      {
        name: "planningArea",
        description: "Planning area used to anchor the proximity search.",
        kind: "enum",
        required: true,
        enumValues: planningAreaEnum,
        completionSource: "planningArea",
      },
      { name: "centreType", description: "Optional childcare centre type filter.", kind: "string" },
      { name: "operatorType", description: "Optional operator type filter.", kind: "string" },
    ],
    buildStarterPrompt: (args) => {
      const centreType = typeof args["centreType"] === "string" ? `${args["centreType"]} ` : "";
      return `Find ${centreType}childcare centres near ${args["planningArea"]} with vacancies`;
    },
  },
  residents_network_near_address: {
    args: [
      { name: "address", description: "Address to geocode before the proximity search.", kind: "string", required: true },
    ],
    buildStarterPrompt: (args) => `Find a residents' network centre near ${args["address"]}`,
  },
  moe_school_directory_lookup: {
    args: [
      {
        name: "level",
        description: "Optional school level filter.",
        kind: "enum",
        enumValues: ["PRIMARY", "SECONDARY", "JUNIOR COLLEGE"],
      },
      {
        name: "zone",
        description: "Optional MOE school zone filter.",
        kind: "enum",
        enumValues: ["NORTH", "SOUTH", "EAST", "WEST", "CENTRAL"],
      },
      { name: "name", description: "Optional exact school name filter.", kind: "string" },
    ],
    buildStarterPrompt: (args) => {
      const level = typeof args["level"] === "string" ? `${args["level"].toLowerCase()} ` : "";
      const zone = typeof args["zone"] === "string" ? ` in ${args["zone"].toLowerCase()} zone` : "";
      const name = typeof args["name"] === "string" ? ` named "${args["name"]}"` : "";
      return `Find MOE ${level}schools${zone}${name}`.trim();
    },
  },
  moh_healthcare_directory_lookup: {
    args: [
      {
        name: "type",
        description: "Optional healthcare facility type filter.",
        kind: "enum",
        enumValues: ["HOSPITAL", "CLINIC"],
      },
      { name: "postalCode", description: "Optional Singapore postal code filter.", kind: "string" },
      { name: "name", description: "Optional exact facility name filter.", kind: "string" },
    ],
    buildStarterPrompt: (args) => {
      const type = typeof args["type"] === "string" ? `${args["type"].toLowerCase()} ` : "";
      const postalCode = typeof args["postalCode"] === "string" ? ` near postal code ${args["postalCode"]}` : "";
      const name = typeof args["name"] === "string" ? ` named "${args["name"]}"` : "";
      return `Find MOH ${type}facilities${postalCode}${name}`.trim();
    },
  },
  business_due_diligence: {
    args: [
      { name: "entityName", description: "Entity or company name.", kind: "string", required: true },
      { name: "uen", description: "Optional UEN when known.", kind: "string" },
      { name: "registrationNo", description: "Optional registration number when known.", kind: "string" },
    ],
    buildStarterPrompt: (args) => `Business dossier for ${renderBusinessLookupTarget(args)}`,
  },
  architecture_firm_diligence: {
    args: [
      { name: "entityName", description: "Architecture firm name.", kind: "string", required: true },
      { name: "registrationNo", description: "Optional registration number.", kind: "string" },
    ],
    buildStarterPrompt: (args) => `Architecture firm diligence for ${renderBusinessLookupTarget(args)}`,
  },
  healthcare_supplier_diligence: {
    args: [
      { name: "entityName", description: "Healthcare supplier or entity name.", kind: "string", required: true },
    ],
    buildStarterPrompt: (args) => `Healthcare supplier diligence for ${renderBusinessLookupTarget(args)}`,
  },
  hotel_operator_lookup: {
    args: [
      { name: "entityName", description: "Hotel or operator name.", kind: "string", required: true },
    ],
    buildStarterPrompt: (args) => `Hotel operator lookup for ${renderBusinessLookupTarget(args)}`,
  },
  nlb_library_directory_lookup: {
    args: [
      {
        name: "region",
        description: "Optional NLB region filter.",
        kind: "enum",
        enumValues: ["NORTH", "SOUTH", "EAST", "WEST", "CENTRAL"],
      },
      { name: "postalCode", description: "Optional Singapore postal code filter.", kind: "string" },
      { name: "name", description: "Optional exact library name filter.", kind: "string" },
    ],
    buildStarterPrompt: (args) => {
      const region = typeof args["region"] === "string" ? ` in ${args["region"].toLowerCase()} region` : "";
      const postalCode = typeof args["postalCode"] === "string" ? ` near postal code ${args["postalCode"]}` : "";
      const name = typeof args["name"] === "string" ? ` named "${args["name"]}"` : "";
      return `Find public libraries${region}${postalCode}${name}`.trim();
    },
  },
  nparks_park_directory_lookup: {
    args: [
      { name: "name", description: "Optional exact park name filter.", kind: "string" },
    ],
    buildStarterPrompt: (args) => {
      const name = typeof args["name"] === "string" ? ` named "${args["name"]}"` : "";
      return `Find parks and nature reserves${name}`.trim();
    },
  },
  sfa_licensed_food_establishment_lookup: {
    args: [
      { name: "name", description: "Optional exact establishment name filter.", kind: "string" },
    ],
    buildStarterPrompt: (args) => {
      const name = typeof args["name"] === "string" ? ` named "${args["name"]}"` : "";
      return `Find licensed food establishments${name}`.trim();
    },
  },
  singapore_statutes_search: {
    args: [
      { name: "query", description: "Keyword or phrase to search across Singapore Statutes Online.", kind: "string", required: true },
    ],
    buildStarterPrompt: (args) => `Search Singapore statutes for ${String(args["query"] ?? "").trim()}`,
  },
  pulse_overview: {
    args: [
      {
        name: "focus",
        description: "Optional Pulse focus.",
        kind: "enum",
        enumValues: ["mobility", "weather", "all"],
        completionSource: "pulseFocus",
      },
      { name: "area", description: "Optional Singapore area filter.", kind: "string" },
      { name: "region", description: "Optional Singapore region filter.", kind: "string" },
      { name: "stationId", description: "Optional NEA station identifier.", kind: "string" },
    ],
    buildStarterPrompt: (args) => {
      const focus = typeof args["focus"] === "string" ? args["focus"] : "all";
      const area = typeof args["area"] === "string" ? ` for ${args["area"]}` : "";
      return `Show the Swee Pulse ${focus} snapshot${area}`.trim();
    },
    buildPreferredEntrypointInput: (args) => ({
      ...(typeof args["focus"] === "string" ? { focus: args["focus"] } : { focus: "all" }),
      ...(typeof args["area"] === "string" ? { area: args["area"] } : {}),
      ...(typeof args["region"] === "string" ? { region: args["region"] } : {}),
      ...(typeof args["stationId"] === "string" ? { stationId: args["stationId"] } : {}),
    }),
  },
  shield_recent_audit: {
    args: [
      { name: "toolName", description: "Optional tool-name filter.", kind: "string" },
      { name: "traceId", description: "Optional trace identifier filter.", kind: "string" },
      { name: "requestId", description: "Optional request identifier filter.", kind: "string" },
      { name: "limit", description: "Maximum audit rows to return.", kind: "number" },
    ],
    buildStarterPrompt: (args) => {
      const toolName = typeof args["toolName"] === "string" ? ` for ${args["toolName"]}` : "";
      return `Show recent Swee Shield audit rows${toolName}`.trim();
    },
    buildPreferredEntrypointInput: (args) => ({
      ...(typeof args["toolName"] === "string" ? { toolName: args["toolName"] } : {}),
      ...(typeof args["traceId"] === "string" ? { traceId: args["traceId"] } : {}),
      ...(typeof args["requestId"] === "string" ? { requestId: args["requestId"] } : {}),
      ...(typeof args["limit"] === "number" ? { limit: args["limit"] } : { limit: 25 }),
    }),
  },
  splunk_investigation_pack: {
    args: [
      { name: "question", description: "Incident question for bounded Splunk investigation.", kind: "string", required: true },
      { name: "index", description: "Optional allowlisted Splunk index.", kind: "string" },
      { name: "earliest", description: "Optional earliest SPL time bound.", kind: "string" },
      { name: "latest", description: "Optional latest SPL time bound.", kind: "string" },
      { name: "limit", description: "Maximum events per bounded search.", kind: "number" },
    ],
    buildStarterPrompt: (args) => {
      const question = typeof args["question"] === "string" && args["question"].trim() !== ""
        ? args["question"].trim()
        : "recent failed login activity";
      return `Build a Swee Shield Splunk investigation pack for ${question}`;
    },
    buildPreferredEntrypointInput: (args) => ({
      question: typeof args["question"] === "string" ? args["question"] : "Investigate recent failed login activity",
      ...(typeof args["index"] === "string" ? { index: args["index"] } : {}),
      ...(typeof args["earliest"] === "string" ? { earliest: args["earliest"] } : {}),
      ...(typeof args["latest"] === "string" ? { latest: args["latest"] } : {}),
      ...(typeof args["limit"] === "number" ? { limit: args["limit"] } : { limit: 20 }),
    }),
  },
  transit_ops_brief: {
    args: [
      { name: "scopeKey", description: "Optional deterministic scope key used for repeat monitoring runs.", kind: "string" },
      { name: "stopIds", description: "Optional comma-separated stop IDs for targeted transit monitoring.", kind: "string" },
      {
        name: "outputFormat",
        description: `Preferred output format. One of ${listToSentence(outputFormatEnum)}.`,
        kind: "enum",
        enumValues: outputFormatEnum,
        completionSource: "outputFormat",
      },
    ],
    buildStarterPrompt: (args) => {
      const scopeKey = typeof args["scopeKey"] === "string" ? ` with scope key ${args["scopeKey"]}` : "";
      const stopIds = typeof args["stopIds"] === "string" ? ` for stop IDs ${args["stopIds"]}` : "";
      return `Transit ops brief for Singapore right now${scopeKey}${stopIds}.${renderOptionalOutputFormatHint(args)}`.trim();
    },
  },
};

const PLAYBOOK_PROMPT_METADATA: Readonly<Record<string, PromptMetadata>> = {
  city_ops: {
    args: [
      {
        name: "focus",
        description: "Optional operations focus.",
        kind: "enum",
        enumValues: ["mobility", "weather", "all"],
        completionSource: "pulseFocus",
      },
    ],
    buildStarterPrompt: (args) => {
      const focus = typeof args["focus"] === "string" ? args["focus"] : "city";
      return `Open the Swee SG ${focus} operations desk`;
    },
  },
  security_analyst: {
    args: [
      { name: "question", description: "Optional incident question for the security analyst desk.", kind: "string" },
      { name: "index", description: "Optional allowlisted Splunk index.", kind: "string" },
    ],
    buildStarterPrompt: (args) => {
      const question = typeof args["question"] === "string" && args["question"].trim() !== ""
        ? ` for ${args["question"].trim()}`
        : "";
      const index = typeof args["index"] === "string" && args["index"].trim() !== ""
        ? ` in ${args["index"].trim()}`
        : "";
      return `Open the Swee Shield security analyst desk${question}${index}`;
    },
  },
  business_opportunity_scan: {
    args: [
      { name: "entityName", description: "Optional company or target entity name.", kind: "string" },
      { name: "uen", description: "Optional UEN when already known.", kind: "string" },
      { name: "procurementKeyword", description: "Optional procurement or market keyword.", kind: "string" },
      {
        name: "outputFormat",
        description: `Preferred output format. One of ${listToSentence(outputFormatEnum)}.`,
        kind: "enum",
        enumValues: outputFormatEnum,
        completionSource: "outputFormat",
      },
    ],
    buildStarterPrompt: (args) => {
      const target = typeof args["entityName"] === "string"
        ? args["entityName"]
        : typeof args["uen"] === "string"
          ? `UEN ${args["uen"]}`
          : typeof args["procurementKeyword"] === "string"
            ? args["procurementKeyword"]
            : "a Singapore business opportunity";
      return `Build a business opportunity scan for ${target}. ${renderOptionalOutputFormatSentence(args)}`.trim();
    },
  },
  relocation_neighbourhood_brief: {
    args: [
      {
        name: "planningArea",
        description: "Planning area to anchor the relocation brief.",
        kind: "enum",
        required: true,
        enumValues: planningAreaEnum,
        completionSource: "planningArea",
      },
      { name: "postalCode", description: "Optional postal code for a more specific starting point.", kind: "string" },
      {
        name: "region",
        description: "Optional region filter.",
        kind: "enum",
        enumValues: regionEnum,
        completionSource: "region",
      },
      {
        name: "outputFormat",
        description: `Preferred output format. One of ${listToSentence(outputFormatEnum)}.`,
        kind: "enum",
        enumValues: outputFormatEnum,
        completionSource: "outputFormat",
      },
    ],
    buildStarterPrompt: (args) => {
      const postal = typeof args["postalCode"] === "string" ? ` around postal code ${args["postalCode"]}` : "";
      return `Build a relocation neighbourhood brief for ${args["planningArea"]}${postal}${renderOptionalRegion(args)}.${renderOptionalOutputFormatHint(args)}`.trim();
    },
  },
  social_support_navigation: {
    args: [
      { name: "postalCode", description: "Optional postal code to anchor support-service discovery.", kind: "string" },
      { name: "address", description: "Optional address to geocode before discovery.", kind: "string" },
      {
        name: "planningArea",
        description: "Optional planning area anchor for support-service discovery.",
        kind: "enum",
        enumValues: planningAreaEnum,
        completionSource: "planningArea",
      },
      {
        name: "region",
        description: "Optional regional filter for broader support navigation.",
        kind: "enum",
        enumValues: regionEnum,
        completionSource: "region",
      },
    ],
    buildStarterPrompt: (args) => {
      const postalCode = typeof args["postalCode"] === "string" ? `postal code ${args["postalCode"]}` : null;
      const address = typeof args["address"] === "string" ? args["address"] : null;
      const planningArea = typeof args["planningArea"] === "string" ? args["planningArea"] : null;
      const target = postalCode ?? address ?? planningArea ?? "the supplied Singapore location";
      const region = renderOptionalRegion(args);
      return `Build a social support navigation brief for ${target}${region}.`.trim();
    },
  },
  transit_operations_governance: {
    args: [
      { name: "scopeKey", description: "Optional deterministic scope key for recurring governance runs.", kind: "string" },
      { name: "stopIds", description: "Optional comma-separated transit stop IDs for targeted analysis.", kind: "string" },
      {
        name: "objective",
        description: "Optional objective mode when transitioning from ops brief to objective planning.",
        kind: "enum",
        enumValues: ["balanced", "fastest", "accessibility", "safest"],
      },
      {
        name: "outputFormat",
        description: `Preferred output format. One of ${listToSentence(outputFormatEnum)}.`,
        kind: "enum",
        enumValues: outputFormatEnum,
        completionSource: "outputFormat",
      },
    ],
    buildStarterPrompt: (args) => {
      const stopIds = typeof args["stopIds"] === "string" ? ` for stop IDs ${args["stopIds"]}` : "";
      const objective = typeof args["objective"] === "string" ? ` using objective ${args["objective"]}` : "";
      const scopeKey = typeof args["scopeKey"] === "string" ? ` with scope key ${args["scopeKey"]}` : "";
      return `Build a transit operations governance brief${stopIds}${objective}${scopeKey}.${renderOptionalOutputFormatHint(args)}`.trim();
    },
  },
};

export const NORMALIZED_API_CATALOG: readonly NormalizedApiCatalogEntry[] = API_CATALOG.map((entry) => ({
  ...entry,
  id: slugify(entry.name),
}));

export const NORMALIZED_WORKFLOW_CATALOG: readonly NormalizedWorkflowCatalogEntry[] = withCatalogIds(WORKFLOW_CATALOG);
export const NORMALIZED_RECIPE_CATALOG: readonly NormalizedRecipeCatalogEntry[] = withCatalogIds(RECIPE_CATALOG).map((entry) => ({
  ...entry,
  ...(RECIPE_PROMPT_METADATA[entry.id] === undefined
    ? {}
    : { promptMetadata: RECIPE_PROMPT_METADATA[entry.id] }),
}));
export const NORMALIZED_PLAYBOOK_CATALOG: readonly NormalizedPlaybookCatalogEntry[] = withCatalogIds(PLAYBOOK_CATALOG).map((entry) => ({
  ...entry,
  ...(PLAYBOOK_PROMPT_METADATA[entry.id] === undefined
    ? {}
    : { promptMetadata: PLAYBOOK_PROMPT_METADATA[entry.id] }),
}));

export const buildToolCatalog = (
  definitions: readonly RegisteredToolDefinition[],
): readonly ToolCatalogEntry[] => {
  return definitions.map(toToolCatalogEntry);
};

export const buildApiCatalog = (
  definitions: readonly Pick<RegisteredToolDefinition, "name">[],
): readonly NormalizedApiCatalogEntry[] => {
  const activeTools = new Set(definitions.map((definition) => definition.name));
  return NORMALIZED_API_CATALOG.flatMap((entry) => {
    const tools = entry.tools.filter((tool) => activeTools.has(tool));
    if (tools.length === 0) {
      return [];
    }
    return [{
      ...entry,
      tools,
    }];
  });
};

export const getApiCatalogEntry = (id: string): NormalizedApiCatalogEntry | undefined => {
  return NORMALIZED_API_CATALOG.find((entry) => entry.id === id);
};

export const getToolCatalogEntry = (
  definitions: readonly RegisteredToolDefinition[],
  name: string,
): ToolCatalogEntry | undefined => {
  return buildToolCatalog(definitions).find((entry) => entry.name === name);
};

export const getWorkflowCatalogEntry = (id: string): NormalizedWorkflowCatalogEntry | undefined => {
  return NORMALIZED_WORKFLOW_CATALOG.find((entry) => entry.id === id);
};

export const getRecipeCatalogEntry = (id: string): NormalizedRecipeCatalogEntry | undefined => {
  return NORMALIZED_RECIPE_CATALOG.find((entry) => entry.id === id);
};

export const getPlaybookCatalogEntry = (id: string): NormalizedPlaybookCatalogEntry | undefined => {
  return NORMALIZED_PLAYBOOK_CATALOG.find((entry) => entry.id === id);
};
