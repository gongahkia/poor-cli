import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

const API_INFO = [
  {
    name: "SingStat",
    description: "Singapore Department of Statistics — GDP, CPI, population, trade, employment",
    tools: ["sg_singstat_search", "sg_singstat_table", "sg_singstat_timeseries", "sg_singstat_compare", "sg_singstat_browse"],
    authRequired: false,
    rateLimit: "10 tokens, 2/sec refill",
  },
  {
    name: "MAS",
    description: "Monetary Authority of Singapore — exchange rates, SORA interest rates, banking statistics",
    tools: ["sg_mas_exchange_rates", "sg_mas_interest_rates", "sg_mas_financial_stats"],
    authRequired: false,
    rateLimit: "10 tokens, 2/sec refill",
  },
  {
    name: "OneMap",
    description: "Singapore's national map — geocoding, routing, demographics, coordinate conversion",
    tools: ["sg_onemap_geocode", "sg_onemap_reverse_geocode", "sg_onemap_route", "sg_onemap_population", "sg_onemap_convert_coords"],
    authRequired: true,
    rateLimit: "50 tokens, 4/sec refill (~250/min)",
  },
  {
    name: "URA",
    description: "Urban Redevelopment Authority — property transactions, planning areas, development charges",
    tools: ["sg_ura_property_transactions", "sg_ura_planning_area", "sg_ura_dev_charges"],
    authRequired: true,
    rateLimit: "5 tokens, 1/sec refill",
  },
  {
    name: "data.gov.sg",
    description: "Singapore open data portal — 2,000+ government datasets",
    tools: ["sg_datagov_search", "sg_datagov_get", "sg_datagov_browse"],
    authRequired: false,
    rateLimit: "20 tokens, 3/sec refill",
  },
];

const TOOL_INFO = [
  { name: "sg_singstat_search", description: "Search SingStat Table Builder for datasets matching a keyword" },
  { name: "sg_singstat_table", description: "Retrieve data from a specific SingStat table" },
  { name: "sg_singstat_timeseries", description: "Get time series data for a specific indicator" },
  { name: "sg_singstat_compare", description: "Compare multiple SingStat indicators side by side" },
  { name: "sg_singstat_browse", description: "Browse SingStat dataset categories" },
  { name: "sg_mas_exchange_rates", description: "Get MAS exchange rates for SGD against foreign currencies by latest value or exact date" },
  { name: "sg_mas_interest_rates", description: "Get MAS SORA interest rates by latest value or exact date" },
  { name: "sg_mas_financial_stats", description: "Get MAS banking statistics by latest value or exact date" },
  { name: "sg_onemap_geocode", description: "Convert address/postal code to coordinates" },
  { name: "sg_onemap_reverse_geocode", description: "Convert coordinates to address" },
  { name: "sg_onemap_route", description: "Get routing directions between two locations" },
  { name: "sg_onemap_population", description: "Get demographic data for a planning area" },
  { name: "sg_onemap_convert_coords", description: "Convert between SVY21 and WGS84 coordinates" },
  { name: "sg_ura_property_transactions", description: "Get property transaction data from URA" },
  { name: "sg_ura_planning_area", description: "Get URA master plan data for coordinates or a planning area name" },
  { name: "sg_ura_dev_charges", description: "Get URA development charge rates" },
  { name: "sg_datagov_search", description: "Search data.gov.sg for datasets" },
  { name: "sg_datagov_get", description: "Get metadata for a specific data.gov.sg dataset" },
  { name: "sg_datagov_browse", description: "Browse data.gov.sg collections" },
  { name: "sg_health_check", description: "Check connectivity for all APIs" },
  { name: "sg_key_set", description: "Store an API key" },
  { name: "sg_key_list", description: "List stored API keys (masked)" },
  { name: "sg_key_delete", description: "Delete a stored API key" },
  { name: "sg_cache_stats", description: "Show cache statistics" },
  { name: "sg_cache_clear", description: "Clear cached data" },
  { name: "sg_config_get", description: "Show current configuration" },
  { name: "sg_config_set", description: "Update configuration" },
  { name: "sg_query", description: "Experimental natural language router for supported single-step Singapore data queries" },
];

export const registerResources = (server: McpServer): void => {
  server.resource("sg-apis", "sg://apis", async () => ({
    contents: [
      {
        uri: "sg://apis",
        text: JSON.stringify(API_INFO, null, 2),
        mimeType: "application/json",
      },
    ],
  }));

  server.resource("sg-tools", "sg://tools", async () => ({
    contents: [
      {
        uri: "sg://tools",
        text: JSON.stringify(TOOL_INFO, null, 2),
        mimeType: "application/json",
      },
    ],
  }));
};
