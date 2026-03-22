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
    description: "Monetary Authority of Singapore — exchange rates, interest rates, financial statistics",
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
};
