import {
  LtaBusArrivalsSchema,
  LtaTrainAlertsSchema,
  LtaTrafficIncidentsSchema,
  formatResponse,
  resolveOutputFormat,
  validateInput,
} from "@sg-apis/shared";
import type { OutputFormat, ToolResult } from "@sg-apis/shared";
import { getBusArrivals, getTrafficIncidents, getTrainAlerts } from "../apis/lta/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

export const handleLtaBusArrivals = async (
  params: Readonly<{ busStopCode: string; serviceNo?: string | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = await getBusArrivals(params.busStopCode, params.serviceNo);
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: data,
    },
  };
};

export const handleLtaTrainAlerts = async (
  params: Readonly<{ format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = await getTrainAlerts();
  const format = resolveOutputFormat(params.format);
  const payload = [
    ...data.alerts.map((alert) => ({
      kind: "alert",
      ...alert,
    })),
    ...data.messages.map((message) => ({
      kind: "message",
      ...message,
    })),
  ];
  const text = formatResponse(payload as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      alerts: data.alerts,
      messages: data.messages,
    },
  };
};

export const handleLtaTrafficIncidents = async (
  params: Readonly<{ format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = await getTrafficIncidents();
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: data,
    },
  };
};

export const ltaToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_lta_bus_arrivals",
    description: "Get live LTA bus arrival timings for a Singapore bus stop, optionally filtered to one service number.",
    surface: "canonical",
    inputSchema: LtaBusArrivalsSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleLtaBusArrivals(validateInput(LtaBusArrivalsSchema, input)),
  },
  {
    name: "sg_lta_train_alerts",
    description: "Get live LTA train service alerts including affected MRT lines, stations, and free shuttle or bus arrangements.",
    surface: "canonical",
    inputSchema: LtaTrainAlertsSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleLtaTrainAlerts(validateInput(LtaTrainAlertsSchema, input)),
  },
  {
    name: "sg_lta_traffic_incidents",
    description: "Get live LTA traffic incidents with incident type, location, and message.",
    surface: "canonical",
    inputSchema: LtaTrafficIncidentsSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleLtaTrafficIncidents(validateInput(LtaTrafficIncidentsSchema, input)),
  },
];
