import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { validateInput, MasExchangeRateSchema, MasInterestRateSchema, MasFinancialStatsSchema, MasDataset, formatResponse } from "@sg-apis/shared";
import type { ToolResult, OutputFormat } from "@sg-apis/shared";
import { query } from "../apis/mas/client.js";
import { normalizeMasRecord } from "../apis/mas/normalizer.js";
import { registerTool } from "./registry.js";

export const registerMasTools = (server: McpServer): void => {
  registerTool(server, {
    name: "sg_mas_exchange_rates",
    description: "Get MAS exchange rates for SGD against foreign currencies. Specify a currency code (e.g., USD, EUR) and optional date range.",
    inputSchema: MasExchangeRateSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { currency, startDate, format } = validateInput(MasExchangeRateSchema, input);
      const filters: Record<string, string> = {};
      if (startDate !== undefined) filters["end_of_day"] = startDate;
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

      const fmt = (format ?? "markdown") as OutputFormat;
      const text = formatResponse(normalized as unknown as Record<string, unknown>[], fmt);
      return { content: [{ type: "text", text }] };
    },
  });

  registerTool(server, {
    name: "sg_mas_interest_rates",
    description: "Get MAS interest rates (SORA, prime lending, fixed deposit). SORA is the default benchmark rate.",
    inputSchema: MasInterestRateSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { startDate, format } = validateInput(MasInterestRateSchema, input);
      const filters: Record<string, string> = {};
      if (startDate !== undefined) filters["end_of_day"] = startDate;
      const params: { limit: number; filters?: Readonly<Record<string, string>> } = { limit: 100 };
      if (Object.keys(filters).length > 0) params.filters = filters;
      const records = await query(MasDataset.INTEREST_RATES_SORA, params);
      const normalized = records.map(normalizeMasRecord);
      const fmt = (format ?? "markdown") as OutputFormat;
      const text = formatResponse(normalized as unknown as Record<string, unknown>[], fmt);
      return { content: [{ type: "text", text }] };
    },
  });

  registerTool(server, {
    name: "sg_mas_financial_stats",
    description: "Get MAS financial sector statistics: banking (assets, loans), insurance (premiums, claims), monetary (money supply).",
    inputSchema: MasFinancialStatsSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const { category, startDate, format } = validateInput(MasFinancialStatsSchema, input);
      const resourceId = category === "banking" ? MasDataset.BANKING_STATS : MasDataset.BANKING_STATS;
      const filters: Record<string, string> = {};
      if (startDate !== undefined) filters["end_of_day"] = startDate;
      const params: { limit: number; filters?: Readonly<Record<string, string>> } = { limit: 100 };
      if (Object.keys(filters).length > 0) params.filters = filters;
      const records = await query(resourceId, params);
      const normalized = records.map(normalizeMasRecord);
      const fmt = (format ?? "markdown") as OutputFormat;
      const text = formatResponse(normalized as unknown as Record<string, unknown>[], fmt);
      return { content: [{ type: "text", text }] };
    },
  });
};
