import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { validateInput, MasExchangeRateSchema, MasInterestRateSchema, MasFinancialStatsSchema, MasDataset, formatResponse, resolveOutputFormat } from "@sg-apis/shared";
import type { ToolResult } from "@sg-apis/shared";
import { query } from "../apis/mas/client.js";
import { normalizeMasRecord } from "../apis/mas/normalizer.js";
import { registerTool } from "./registry.js";

export const registerMasTools = (server: McpServer): void => {
  registerTool(server, {
    name: "sg_mas_exchange_rates",
    description: "Get MAS exchange rates for SGD against foreign currencies. Supports latest data or an exact date lookup.",
    inputSchema: MasExchangeRateSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { currency, date, format } = validateInput(MasExchangeRateSchema, input);
      const filters: Record<string, string> = {};
      if (date !== undefined) filters["end_of_day"] = date;
      const params: { limit: number; filters?: Readonly<Record<string, string>> } = { limit: 100 };
      if (Object.keys(filters).length > 0) params.filters = filters;
      const records = await query(MasDataset.EXCHANGE_RATES, params);

      let normalized = records.map(normalizeMasRecord);
      if (currency !== undefined) {
        const key = `${currency.toLowerCase()}_sgd`;
        normalized = normalized.map((r) => ({
          date: r.date,
          [key]: r[key] ?? r[`${currency.toLowerCase()}_sgd_100`] ?? "N/A",
        }));
      }

      const fmt = resolveOutputFormat(format);
      const text = formatResponse(normalized as unknown as Record<string, unknown>[], fmt);
      return { content: [{ type: "text", text }] };
    },
  });

  registerTool(server, {
    name: "sg_mas_interest_rates",
    description: "Get MAS interest rates. This phase supports SORA only, with latest data or an exact date lookup.",
    inputSchema: MasInterestRateSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { date, format } = validateInput(MasInterestRateSchema, input);
      const filters: Record<string, string> = {};
      if (date !== undefined) filters["end_of_day"] = date;
      const params: { limit: number; filters?: Readonly<Record<string, string>> } = { limit: 100 };
      if (Object.keys(filters).length > 0) params.filters = filters;
      const records = await query(MasDataset.INTEREST_RATES_SORA, params);
      const normalized = records.map(normalizeMasRecord);
      const fmt = resolveOutputFormat(format);
      const text = formatResponse(normalized as unknown as Record<string, unknown>[], fmt);
      return { content: [{ type: "text", text }] };
    },
  });

  registerTool(server, {
    name: "sg_mas_financial_stats",
    description: "Get MAS banking statistics. This phase supports banking data only, with latest data or an exact date lookup.",
    inputSchema: MasFinancialStatsSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { date, format } = validateInput(MasFinancialStatsSchema, input);
      const filters: Record<string, string> = {};
      if (date !== undefined) filters["end_of_day"] = date;
      const params: { limit: number; filters?: Readonly<Record<string, string>> } = { limit: 100 };
      if (Object.keys(filters).length > 0) params.filters = filters;
      const records = await query(MasDataset.BANKING_STATS, params);
      const normalized = records.map(normalizeMasRecord);
      const fmt = resolveOutputFormat(format);
      const text = formatResponse(normalized as unknown as Record<string, unknown>[], fmt);
      return { content: [{ type: "text", text }] };
    },
  });
};
