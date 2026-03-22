import { validateInput, UraPropertyTransactionsSchema, UraPlanningAreaBaseSchema, UraPlanningAreaSchema, UraDevChargesSchema, formatResponse, resolveOutputFormat } from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import type { UraPlanningResponse } from "@sg-apis/shared";
import { geocode } from "../apis/onemap/client.js";
import { getPropertyTransactions, uraFetch } from "../apis/ura/client.js";
import { normalizePlanningData, normalizeTransactions } from "../apis/ura/normalizer.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const lookupPlanningArea = async (
  params: Readonly<{ lat?: number | undefined; lng?: number | undefined; planningArea?: string | undefined }>,
): Promise<{ planningArea: string; region: string }[]> => {
  let coordinates: { lat: number; lng: number };

  if (params.lat !== undefined && params.lng !== undefined) {
    coordinates = { lat: params.lat, lng: params.lng };
  } else if (params.planningArea !== undefined) {
    const candidates = await geocode(params.planningArea, 1);
    const match = candidates[0];
    if (match === undefined) {
      throw new Error(`Could not resolve planning area: ${params.planningArea}`);
    }
    coordinates = { lat: match.lat, lng: match.lng };
  } else {
    throw new Error("Provide planningArea or both lat and lng");
  }

  const result = await uraFetch<UraPlanningResponse>("GET_PLANNING_AREA", {
    lat: String(coordinates.lat),
    lng: String(coordinates.lng),
  });
  return result.Result.map(normalizePlanningData);
};

export const handleUraPropertyTransactions = async (
  params: Readonly<{ propertyType?: string | undefined; area?: string | undefined; period?: string | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const raw = await getPropertyTransactions(params.propertyType, params.area, params.period);
  const normalized = normalizeTransactions(raw);
  const fmt = resolveOutputFormat(params.format);
  const text = formatResponse(normalized as unknown as Record<string, unknown>[], fmt);
  return { content: [{ type: "text", text }] };
};

export const handleUraPlanningArea = async (
  params: Readonly<{ lat?: number | undefined; lng?: number | undefined; planningArea?: string | undefined }>,
): Promise<ToolResult> => {
  const result = await lookupPlanningArea(params);
  const text = formatResponse(result as unknown as Record<string, unknown>[], "markdown");
  return { content: [{ type: "text", text }] };
};

export const uraToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_ura_property_transactions",
    description: "Get property transaction data from URA. Includes resale and rental prices for private residential, commercial, and industrial properties.",
    surface: "canonical",
    inputSchema: UraPropertyTransactionsSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      return handleUraPropertyTransactions(validateInput(UraPropertyTransactionsSchema, input));
    },
  },

  {
    name: "sg_ura_planning_area",
    description: "Get URA master plan data for a location or planning area. Returns zoning information, gross plot ratio, and land use designations.",
    surface: "canonical",
    inputSchema: UraPlanningAreaBaseSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      return handleUraPlanningArea(validateInput(UraPlanningAreaSchema, input));
    },
  },

  {
    name: "sg_ura_dev_charges",
    description: "Get URA development charge rates by use group and sector. Rates are updated semi-annually.",
    surface: "canonical",
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
  },
];
