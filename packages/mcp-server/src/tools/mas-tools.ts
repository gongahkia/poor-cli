import { validateInput, MasExchangeRateSchema, MasInterestRateSchema, MasFinancialStatsSchema, MasDataset, formatResponse, resolveOutputFormat } from "@dude/shared";
import type { OutputFormat, ToolResult } from "@dude/shared";
import { query } from "../apis/mas/client.js";
import { normalizeMasRecord } from "../apis/mas/normalizer.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const normalizeDateOnly = (value: string): string => value.slice(0, 10);

export const filterMasRecordsByDate = (
  records: readonly Record<string, unknown>[],
  params: Readonly<{ date?: string | undefined; startDate?: string | undefined; endDate?: string | undefined }>,
): readonly Record<string, unknown>[] => {
  const withDate = records.filter((record) => typeof record["date"] === "string");
  const exactDate = params.date;
  const startDate = params.startDate;
  const endDate = params.endDate;

  return withDate
    .filter((record) => {
      const dateValue = normalizeDateOnly(record["date"] as string);
      if (exactDate !== undefined && dateValue !== exactDate) {
        return false;
      }
      if (startDate !== undefined && dateValue < startDate) {
        return false;
      }
      if (endDate !== undefined && dateValue > endDate) {
        return false;
      }
      return true;
    })
    .sort((left, right) =>
      String(right["date"]).localeCompare(String(left["date"])),
    );
};

export const fetchNormalizedMasRecords = async (
  dataset: string,
  params: Readonly<{ date?: string | undefined; startDate?: string | undefined; endDate?: string | undefined }>,
): Promise<readonly Record<string, unknown>[]> => {
  const records = await query(dataset, {
    limit: 100,
    ...(params.date === undefined ? {} : { date: params.date }),
    ...(params.startDate === undefined ? {} : { startDate: params.startDate }),
    ...(params.endDate === undefined ? {} : { endDate: params.endDate }),
  });

  return filterMasRecordsByDate(
    records.map(normalizeMasRecord) as readonly Record<string, unknown>[],
    params,
  );
};

export const handleMasExchangeRates = async (
  params: Readonly<{
    currency?: string | undefined;
    date?: string | undefined;
    startDate?: string | undefined;
    endDate?: string | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const { currency, format } = params;
  let normalized = [...await fetchNormalizedMasRecords(MasDataset.EXCHANGE_RATES, params)];
  if (currency !== undefined) {
    const key = `${currency.toLowerCase()}_sgd`;
    normalized = normalized.map((r) => ({
      date: r.date,
      [key]: r[key] ?? r[`${currency.toLowerCase()}_sgd_100`] ?? "N/A",
    }));
  }

  const fmt = resolveOutputFormat(format);
  const text = formatResponse(normalized as unknown as Record<string, unknown>[], fmt);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: normalized as unknown as readonly Record<string, unknown>[],
    },
  };
};

export const handleMasInterestRates = async (
  params: Readonly<{
    date?: string | undefined;
    startDate?: string | undefined;
    endDate?: string | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const { format } = params;
  const normalized = await fetchNormalizedMasRecords(MasDataset.INTEREST_RATES_SORA, params);
  const fmt = resolveOutputFormat(format);
  const text = formatResponse(normalized as unknown as Record<string, unknown>[], fmt);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: normalized as unknown as readonly Record<string, unknown>[],
    },
  };
};

export const handleMasFinancialStats = async (
  params: Readonly<{
    date?: string | undefined;
    startDate?: string | undefined;
    endDate?: string | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const { format } = params;
  const normalized = await fetchNormalizedMasRecords(MasDataset.BANKING_STATS, params);
  const fmt = resolveOutputFormat(format);
  const text = formatResponse(normalized as unknown as Record<string, unknown>[], fmt);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: normalized as unknown as readonly Record<string, unknown>[],
    },
  };
};

export const masToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_mas_exchange_rates",
    description: "Get MAS exchange rates for SGD against foreign currencies. Supports latest data, an exact date, or a bounded date range.",
    surface: "canonical",
    inputSchema: MasExchangeRateSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      return handleMasExchangeRates(validateInput(MasExchangeRateSchema, input));
    },
  },

  {
    name: "sg_mas_interest_rates",
    description: "Get MAS interest rates. This phase supports SORA only, with latest data, an exact date, or a bounded date range.",
    surface: "canonical",
    inputSchema: MasInterestRateSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      return handleMasInterestRates(validateInput(MasInterestRateSchema, input));
    },
  },

  {
    name: "sg_mas_financial_stats",
    description: "Get MAS banking statistics. This phase supports banking data only, with latest data, an exact date, or a bounded date range.",
    surface: "canonical",
    inputSchema: MasFinancialStatsSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      return handleMasFinancialStats(validateInput(MasFinancialStatsSchema, input));
    },
  },
];
