export type ToolSurface = "canonical" | "operational" | "experimental";

export type ToolCatalogEntry = {
  readonly name: string;
  readonly description: string;
  readonly surface: ToolSurface;
  readonly scopeNotes?: readonly string[];
};

export type ApiCatalogEntry = {
  readonly name: string;
  readonly description: string;
  readonly tools: readonly string[];
  readonly authRequired: boolean;
  readonly rateLimit: string;
  readonly positioning: string;
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
  },
  {
    name: "MAS",
    description: "Monetary Authority of Singapore for latest or exact-date exchange rates, SORA, and banking statistics.",
    tools: ["sg_mas_exchange_rates", "sg_mas_interest_rates", "sg_mas_financial_stats"],
    authRequired: false,
    rateLimit: "10 tokens, 2/sec refill",
    positioning: "Narrow but honest monetary-data surface for this pilot.",
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
  },
  {
    name: "URA",
    description: "Urban Redevelopment Authority for property transactions, planning-area lookup, and development charges.",
    tools: ["sg_ura_property_transactions", "sg_ura_planning_area", "sg_ura_dev_charges"],
    authRequired: true,
    rateLimit: "5 tokens, 1/sec refill",
    positioning: "Primary property and planning context surface.",
  },
  {
    name: "data.gov.sg",
    description: "Singapore open data portal for broad dataset discovery and metadata retrieval.",
    tools: ["sg_datagov_search", "sg_datagov_get", "sg_datagov_browse"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill",
    positioning: "Fallback discovery surface when the domain APIs do not fit.",
    scopeNotes: [
      "sg_datagov_get returns dataset metadata only.",
    ],
  },
];

export const TOOL_CATALOG: readonly ToolCatalogEntry[] = [
  { name: "sg_singstat_search", description: "Search SingStat Table Builder for datasets matching a keyword", surface: "canonical" },
  { name: "sg_singstat_table", description: "Retrieve data from a specific SingStat table", surface: "canonical" },
  { name: "sg_singstat_timeseries", description: "Get time series data for a specific indicator", surface: "canonical" },
  { name: "sg_singstat_compare", description: "Compare multiple SingStat indicators side by side", surface: "canonical" },
  { name: "sg_singstat_browse", description: "Browse SingStat dataset categories", surface: "canonical" },
  { name: "sg_mas_exchange_rates", description: "Get MAS exchange rates for SGD against foreign currencies by latest value or exact date", surface: "canonical" },
  { name: "sg_mas_interest_rates", description: "Get MAS SORA interest rates by latest value or exact date", surface: "canonical" },
  { name: "sg_mas_financial_stats", description: "Get MAS banking statistics by latest value or exact date", surface: "canonical" },
  { name: "sg_onemap_geocode", description: "Convert address or postal code to coordinates", surface: "canonical" },
  { name: "sg_onemap_reverse_geocode", description: "Convert coordinates to address", surface: "canonical" },
  { name: "sg_onemap_route", description: "Get routing directions between two locations", surface: "canonical" },
  { name: "sg_onemap_population", description: "Get demographic data for a planning area", surface: "canonical" },
  { name: "sg_onemap_convert_coords", description: "Convert between SVY21 and WGS84 coordinates", surface: "canonical" },
  { name: "sg_ura_property_transactions", description: "Get property transaction data from URA", surface: "canonical" },
  { name: "sg_ura_planning_area", description: "Get URA master plan data for coordinates or a planning area name", surface: "canonical" },
  { name: "sg_ura_dev_charges", description: "Get URA development charge rates", surface: "canonical" },
  { name: "sg_datagov_search", description: "Search data.gov.sg for datasets", surface: "canonical" },
  { name: "sg_datagov_get", description: "Get metadata for a specific data.gov.sg dataset", surface: "canonical", scopeNotes: ["Metadata only."] },
  { name: "sg_datagov_browse", description: "Browse data.gov.sg collections", surface: "canonical" },
  { name: "sg_health_check", description: "Check connectivity and credential presence for all APIs", surface: "operational" },
  { name: "sg_key_set", description: "Store an API key or credential in the local keystore", surface: "operational" },
  { name: "sg_key_list", description: "List stored API keys (masked)", surface: "operational" },
  { name: "sg_key_delete", description: "Delete a stored API key", surface: "operational" },
  { name: "sg_cache_stats", description: "Show cache statistics", surface: "operational" },
  { name: "sg_cache_clear", description: "Clear cached data", surface: "operational" },
  { name: "sg_config_get", description: "Show current configuration", surface: "operational" },
  { name: "sg_config_set", description: "Update supported runtime configuration keys", surface: "operational" },
  { name: "sg_query", description: "Experimental natural language router for supported single-step Singapore data queries", surface: "experimental" },
];

export const WORKFLOW_CATALOG: readonly WorkflowCatalogEntry[] = [
  {
    name: "Macro Snapshot",
    intent: "Combine SingStat and MAS for a top-down Singapore macro check.",
    entrypoints: [
      { tool: "sg_singstat_search", input: { keyword: "GDP Singapore" } },
      { tool: "sg_singstat_search", input: { keyword: "CPI Singapore" } },
      { tool: "sg_mas_exchange_rates", input: { currency: "USD" } },
      { tool: "sg_mas_interest_rates", input: {} },
    ],
  },
  {
    name: "Area Demographics",
    intent: "Inspect a planning area's population and household profile.",
    entrypoints: [
      { tool: "sg_onemap_population", input: { planningArea: "Tampines", dataType: "getPopulationAgeGroup" } },
      { tool: "sg_onemap_population", input: { planningArea: "Tampines", dataType: "getHouseholdMonthlyIncomeWork" } },
    ],
  },
  {
    name: "Property And Location Due Diligence",
    intent: "Pair URA transaction and planning data with location context.",
    entrypoints: [
      { tool: "sg_ura_property_transactions", input: { propertyType: "residential", area: "Bedok" } },
      { tool: "sg_ura_planning_area", input: { planningArea: "Bedok" } },
      { tool: "sg_onemap_geocode", input: { searchVal: "Bedok" } },
    ],
  },
  {
    name: "Dataset Discovery Fallback",
    intent: "Search data.gov.sg when the domain APIs do not cover the topic cleanly.",
    entrypoints: [
      { tool: "sg_datagov_search", input: { keyword: "hawker centres" } },
      { tool: "sg_datagov_get", input: { datasetId: "<dataset-id-from-search>" } },
    ],
  },
];

export const RESOURCE_URIS = {
  apis: "sg://apis",
  tools: "sg://tools",
  workflows: "sg://workflows",
} as const;
