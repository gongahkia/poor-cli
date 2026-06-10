import {
  NeaAirQualitySchema,
  NeaForecast2HrSchema,
  NeaRainfallSchema,
  formatResponse,
  resolveOutputFormat,
  validateInput,
} from "@swee-sg/shared";
import type { OutputFormat, ToolResult } from "@swee-sg/shared";
import { getAirQuality, getForecast2Hr, getRainfall } from "../apis/nea/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const getObservedAt = (): string => new Date().toISOString();

const toRecordArray = (data: unknown): readonly Readonly<Record<string, unknown>>[] => {
  return Array.isArray(data) ? data as readonly Readonly<Record<string, unknown>>[] : [];
};

const getForecastMeta = (
  params: Readonly<{ area?: string | undefined; date?: string | undefined }>,
  data: readonly Readonly<Record<string, unknown>>[],
): Readonly<Record<string, unknown>> => {
  const primary = data[0];

  return {
    requestedScope: {
      area: params.area ?? null,
      date: params.date ?? null,
    },
    resolvedScope: {
      area: typeof primary?.["area"] === "string" ? primary["area"] : params.area ?? null,
      rowCount: data.length,
    },
    observedAt: getObservedAt(),
    upstreamTimestamp:
      typeof primary?.["updatedAt"] === "string"
        ? primary["updatedAt"]
        : typeof primary?.["validFrom"] === "string"
          ? primary["validFrom"]
          : null,
    coverage: "2-hour forecast coverage for the requested area or the first available area.",
  };
};

const getAirQualityMeta = (
  params: Readonly<{ region?: string | undefined; date?: string | undefined }>,
  data: readonly Readonly<Record<string, unknown>>[],
): Readonly<Record<string, unknown>> => {
  const primary = data[0];

  return {
    requestedScope: {
      region: params.region ?? null,
      date: params.date ?? null,
    },
    resolvedScope: {
      region: typeof primary?.["region"] === "string" ? primary["region"] : params.region ?? null,
      rowCount: data.length,
    },
    observedAt: getObservedAt(),
    upstreamTimestamp: typeof primary?.["updatedAt"] === "string" ? primary["updatedAt"] : null,
    coverage: "Regional air-quality coverage for the requested region or the first available region.",
  };
};

const getRainfallMeta = (
  params: Readonly<{ stationId?: string | undefined; date?: string | undefined }>,
  data: readonly Readonly<Record<string, unknown>>[],
): Readonly<Record<string, unknown>> => {
  const primary = data[0];

  return {
    requestedScope: {
      stationId: params.stationId ?? null,
      date: params.date ?? null,
    },
    resolvedScope: {
      stationId: typeof primary?.["stationId"] === "string" ? primary["stationId"] : params.stationId ?? null,
      stationName: typeof primary?.["stationName"] === "string" ? primary["stationName"] : null,
      rowCount: data.length,
    },
    observedAt: getObservedAt(),
    upstreamTimestamp: typeof primary?.["timestamp"] === "string" ? primary["timestamp"] : null,
    coverage: "Station rainfall coverage for the requested station or the first available station.",
  };
};

export const handleNeaForecast2Hr = async (
  params: Readonly<{ area?: string | undefined; date?: string | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = toRecordArray(await getForecast2Hr(params.area, params.date));
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: data,
      meta: getForecastMeta(params, data as unknown as readonly Readonly<Record<string, unknown>>[]),
    },
  };
};

export const handleNeaAirQuality = async (
  params: Readonly<{ region?: string | undefined; date?: string | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = toRecordArray(await getAirQuality(params.region, params.date));
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: data,
      meta: getAirQualityMeta(params, data as unknown as readonly Readonly<Record<string, unknown>>[]),
    },
  };
};

export const handleNeaRainfall = async (
  params: Readonly<{ stationId?: string | undefined; date?: string | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = toRecordArray(await getRainfall(params.stationId, params.date));
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: data,
      meta: getRainfallMeta(params, data as unknown as readonly Readonly<Record<string, unknown>>[]),
    },
  };
};

export const neaToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_nea_forecast_2hr",
    description: "Get NEA 2-hour weather forecast data, optionally filtered to one area.",
    surface: "canonical",
    inputSchema: NeaForecast2HrSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleNeaForecast2Hr(validateInput(NeaForecast2HrSchema, input)),
  },
  {
    name: "sg_nea_air_quality",
    description: "Get NEA air quality readings by region, including PSI and PM2.5 metrics.",
    surface: "canonical",
    inputSchema: NeaAirQualitySchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleNeaAirQuality(validateInput(NeaAirQualitySchema, input)),
  },
  {
    name: "sg_nea_rainfall",
    description: "Get NEA rainfall readings by station, optionally filtered to one station ID.",
    surface: "canonical",
    inputSchema: NeaRainfallSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleNeaRainfall(validateInput(NeaRainfallSchema, input)),
  },
];
