import {
  NeaAirQualitySchema,
  NeaForecast2HrSchema,
  NeaRainfallSchema,
  formatResponse,
  resolveOutputFormat,
  validateInput,
} from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { getAirQuality, getForecast2Hr, getRainfall } from "../apis/nea/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleNeaForecast2Hr = async (
  params: Readonly<{ area?: string | undefined; date?: string | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = await getForecast2Hr(params.area, params.date);
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: data,
    },
  };
};

export const handleNeaAirQuality = async (
  params: Readonly<{ region?: string | undefined; date?: string | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = await getAirQuality(params.region, params.date);
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: data,
    },
  };
};

export const handleNeaRainfall = async (
  params: Readonly<{ stationId?: string | undefined; date?: string | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = await getRainfall(params.stationId, params.date);
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: data,
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
