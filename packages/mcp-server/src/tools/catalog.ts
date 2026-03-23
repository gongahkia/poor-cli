import type { ToolCatalogEntry } from "./tool-definition.js";
import { toToolCatalogEntry } from "./tool-definition.js";
import { ALL_TOOL_DEFINITIONS } from "./tool-set.js";

export type ApiCatalogEntry = {
  readonly name: string;
  readonly description: string;
  readonly tools: readonly string[];
  readonly authRequired: boolean;
  readonly rateLimit: string;
  readonly positioning: string;
  readonly preferredInterface?: string;
  readonly scopeNotes?: readonly string[];
};

export type WorkflowCatalogEntry = {
  readonly name: string;
  readonly intent: string;
  readonly entrypoints: readonly {
    readonly tool: string;
    readonly input: Readonly<Record<string, unknown>>;
  }[];
};

export const API_CATALOG: readonly ApiCatalogEntry[] = [
  {
    name: "SingStat",
    description: "Singapore Department of Statistics for dataset discovery, table reads, time series, and explicit indicator comparisons.",
    tools: ["sg_singstat_search", "sg_singstat_table", "sg_singstat_timeseries", "sg_singstat_compare", "sg_singstat_browse"],
    authRequired: false,
    rateLimit: "10 tokens, 2/sec refill",
    positioning: "Canonical direct tool family for macroeconomic and statistical work.",
    preferredInterface: "sg_query",
  },
  {
    name: "MAS",
    description: "Monetary Authority of Singapore for latest or exact-date exchange rates, SORA, and banking statistics.",
    tools: ["sg_mas_exchange_rates", "sg_mas_interest_rates", "sg_mas_financial_stats"],
    authRequired: false,
    rateLimit: "10 tokens, 2/sec refill",
    positioning: "Narrow but honest monetary-data surface for this pilot.",
    preferredInterface: "sg_query",
    scopeNotes: [
      "sg_mas_exchange_rates supports latest or exact-date lookup only.",
      "sg_mas_interest_rates is SORA-only in this phase.",
      "sg_mas_financial_stats is banking-only in this phase.",
    ],
  },
  {
    name: "OneMap",
    description: "Singapore's national map for geocoding, routing, planning-area demographics, and coordinate conversion.",
    tools: ["sg_onemap_geocode", "sg_onemap_reverse_geocode", "sg_onemap_route", "sg_onemap_population", "sg_onemap_convert_coords"],
    authRequired: true,
    rateLimit: "50 tokens, 4/sec refill (~250/min)",
    positioning: "Primary location and demographic surface.",
    preferredInterface: "sg_query",
  },
  {
    name: "URA",
    description: "Urban Redevelopment Authority for property transactions, planning-area lookup, and development charges.",
    tools: ["sg_ura_property_transactions", "sg_ura_planning_area", "sg_ura_dev_charges"],
    authRequired: true,
    rateLimit: "5 tokens, 1/sec refill",
    positioning: "Primary property and planning context surface.",
    preferredInterface: "sg_query",
  },
  {
    name: "LTA DataMall",
    description: "Land Transport Authority live transport data for bus arrivals, train alerts, and traffic incidents.",
    tools: ["sg_lta_bus_arrivals", "sg_lta_train_alerts", "sg_lta_traffic_incidents"],
    authRequired: true,
    rateLimit: "20 tokens, 2/sec refill",
    positioning: "Primary transport-status surface for live operational checks.",
    preferredInterface: "sg_query",
  },
  {
    name: "NEA",
    description: "National Environment Agency realtime weather, rainfall, and air-quality data.",
    tools: ["sg_nea_forecast_2hr", "sg_nea_air_quality", "sg_nea_rainfall"],
    authRequired: false,
    rateLimit: "20 tokens, 2/sec refill",
    positioning: "Primary environment-status surface for weather and air-quality checks.",
    preferredInterface: "sg_query",
  },
  {
    name: "HDB",
    description: "Curated housing-market surface over official HDB resale and rental datasets from data.gov.sg.",
    tools: ["sg_hdb_resale_prices", "sg_hdb_rental_prices"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill via data.gov.sg",
    positioning: "Explicit housing-market surface for HDB resale and rental checks.",
    preferredInterface: "sg_query",
  },
  {
    name: "data.gov.sg",
    description: "Singapore open data portal for broad dataset discovery and metadata retrieval.",
    tools: ["sg_datagov_search", "sg_datagov_get", "sg_datagov_browse"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill",
    positioning: "Fallback discovery surface when the domain APIs do not fit.",
    preferredInterface: "sg_query",
    scopeNotes: [
      "sg_datagov_get returns dataset metadata only.",
    ],
  },
];

export const TOOL_CATALOG: readonly ToolCatalogEntry[] = ALL_TOOL_DEFINITIONS.map(toToolCatalogEntry);

export const WORKFLOW_CATALOG: readonly WorkflowCatalogEntry[] = [
  {
    name: "Macro Snapshot",
    intent: "Combine SingStat and MAS for a top-down Singapore macro check.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Macro snapshot of Singapore", mode: "execute" } },
      { tool: "sg_singstat_search", input: { keyword: "GDP Singapore" } },
      { tool: "sg_singstat_search", input: { keyword: "CPI Singapore" } },
      { tool: "sg_mas_exchange_rates", input: { currency: "USD" } },
      { tool: "sg_mas_interest_rates", input: {} },
    ],
  },
  {
    name: "Demographic Profile",
    intent: "Inspect a planning area's population and household profile, optionally starting from a postal code.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Demographic profile for postal code 168742", mode: "execute" } },
      { tool: "sg_onemap_population", input: { planningArea: "Tampines", dataType: "getPopulationAgeGroup" } },
      { tool: "sg_onemap_population", input: { planningArea: "Tampines", dataType: "getHouseholdMonthlyIncomeWork" } },
    ],
  },
  {
    name: "Property And Regulatory Due Diligence",
    intent: "Pair URA planning and transaction data with location resolution and optional HDB market context.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Property due diligence for Bedok HDB resale", mode: "execute" } },
      { tool: "sg_ura_property_transactions", input: { propertyType: "residential", area: "Bedok" } },
      { tool: "sg_ura_planning_area", input: { planningArea: "Bedok" } },
      { tool: "sg_hdb_resale_prices", input: { town: "Bedok" } },
    ],
  },
  {
    name: "Dataset Discovery Fallback",
    intent: "Search data.gov.sg when the domain APIs do not cover the topic cleanly.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Find datasets about hawker centres", mode: "execute" } },
      { tool: "sg_datagov_search", input: { keyword: "hawker centres" } },
      { tool: "sg_datagov_get", input: { datasetId: "<dataset-id-from-search>" } },
    ],
  },
  {
    name: "Transport Status",
    intent: "Inspect live bus, train, and traffic conditions from LTA.",
    entrypoints: [
      { tool: "sg_query", input: { query: "Bus arrivals for stop 83139 service 851", mode: "execute" } },
      { tool: "sg_lta_bus_arrivals", input: { busStopCode: "83139", serviceNo: "851" } },
      { tool: "sg_lta_train_alerts", input: {} },
      { tool: "sg_lta_traffic_incidents", input: {} },
    ],
  },
  {
    name: "Environment Snapshot",
    intent: "Inspect live weather, rainfall, and air quality from NEA.",
    entrypoints: [
      { tool: "sg_query", input: { query: "2 hour forecast for Tampines", mode: "execute" } },
      { tool: "sg_nea_forecast_2hr", input: { area: "Tampines" } },
      { tool: "sg_nea_air_quality", input: { region: "East" } },
      { tool: "sg_nea_rainfall", input: {} },
    ],
  },
];

export const RESOURCE_URIS = {
  apis: "sg://apis",
  tools: "sg://tools",
  workflows: "sg://workflows",
} as const;
