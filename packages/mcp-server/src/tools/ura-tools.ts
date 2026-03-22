import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { validateInput, UraPropertyTransactionsSchema, UraPlanningAreaSchema, UraDevChargesSchema, formatResponse, resolveOutputFormat } from "@sg-apis/shared";
import type { ToolResult } from "@sg-apis/shared";
import { getPropertyTransactions, uraFetch } from "../apis/ura/client.js";
import { normalizeTransactions } from "../apis/ura/normalizer.js";
import { registerTool } from "./registry.js";

export const registerUraTools = (server: McpServer): void => {
  registerTool(server, {
    name: "sg_ura_property_transactions",
    description: "Get property transaction data from URA. Includes resale and rental prices for private residential, commercial, and industrial properties.",
    inputSchema: UraPropertyTransactionsSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { propertyType, area, period, format } = validateInput(UraPropertyTransactionsSchema, input);
      const raw = await getPropertyTransactions(propertyType, area, period);
      const normalized = normalizeTransactions(raw);
      const fmt = resolveOutputFormat(format);
      const text = formatResponse(normalized as unknown as Record<string, unknown>[], fmt);
      return { content: [{ type: "text", text }] };
    },
  });

  registerTool(server, {
    name: "sg_ura_planning_area",
    description: "Get URA master plan data for a location or planning area. Returns zoning information, gross plot ratio, and land use designations.",
    inputSchema: UraPlanningAreaSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { lat, lng, planningArea } = validateInput(UraPlanningAreaSchema, input);
      if (lat !== undefined && lng !== undefined) {
        const result = await uraFetch<{ Status: string; Result: { pln_area_n: string; region: string }[] }>("GET_PLANNING_AREA", { lat: String(lat), lng: String(lng) });
        const text = formatResponse(result.Result as unknown as Record<string, unknown>[], "markdown");
        return { content: [{ type: "text", text }] };
      }
      return { content: [{ type: "text", text: `Planning area: ${planningArea ?? "Not specified"}` }] };
    },
  });

  registerTool(server, {
    name: "sg_ura_dev_charges",
    description: "Get URA development charge rates by use group and sector. Rates are updated semi-annually.",
    inputSchema: UraDevChargesSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { useGroup, sector } = validateInput(UraDevChargesSchema, input);
      const result = await uraFetch<{ Status: string; Result: { use_grp: string; sector: string; rate: string; effDate: string }[] }>("DC_Rates");
      let data = result.Result;
      if (useGroup !== undefined) data = data.filter((d) => d.use_grp === useGroup);
      if (sector !== undefined) data = data.filter((d) => d.sector === sector);
      const text = formatResponse(data as unknown as Record<string, unknown>[], "markdown");
      return { content: [{ type: "text", text }] };
    },
  });
};
