import {
  HdbRentalPricesSchema,
  HdbResalePricesSchema,
  formatResponse,
  resolveOutputFormat,
  validateInput,
} from "@swee-sg/shared";
import type { OutputFormat, ToolResult } from "@swee-sg/shared";
import { getHdbRentalPrices, getHdbResalePrices } from "../apis/hdb/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleHdbResalePrices = async (
  params: Readonly<{
    town?: string | undefined;
    flatType?: string | undefined;
    startMonth?: string | undefined;
    endMonth?: string | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getHdbResalePrices(params);
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: data,
    },
  };
};

export const handleHdbRentalPrices = async (
  params: Readonly<{
    town?: string | undefined;
    flatType?: string | undefined;
    startMonth?: string | undefined;
    endMonth?: string | undefined;
    limit?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const data = await getHdbRentalPrices(params);
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: data,
    },
  };
};

export const hdbToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_hdb_resale_prices",
    description: "Get curated HDB resale-price records from data.gov.sg, filtered by town, flat type, and month range.",
    surface: "canonical",
    inputSchema: HdbResalePricesSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleHdbResalePrices(validateInput(HdbResalePricesSchema, input)),
  },
  {
    name: "sg_hdb_rental_prices",
    description: "Get curated HDB rental-price records from data.gov.sg, filtered by town, flat type, and month range.",
    surface: "canonical",
    inputSchema: HdbRentalPricesSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleHdbRentalPrices(validateInput(HdbRentalPricesSchema, input)),
  },
];
