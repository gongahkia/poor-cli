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

const getObservedAt = (): string => new Date().toISOString();

const getBusArrivalsMeta = (
  params: Readonly<{ busStopCode: string; serviceNo?: string | undefined }>,
  data: readonly Readonly<Record<string, unknown>>[],
): Readonly<Record<string, unknown>> => {
  const firstService = data[0];
  const arrivals = Array.isArray(firstService?.["arrivals"])
    ? firstService["arrivals"] as readonly Readonly<Record<string, unknown>>[]
    : [];
  const upstreamTimestamp = typeof arrivals[0]?.["estimatedArrival"] === "string"
    ? arrivals[0]!["estimatedArrival"]
    : null;

  return {
    requestedScope: {
      busStopCode: params.busStopCode,
      ...(params.serviceNo === undefined ? {} : { serviceNo: params.serviceNo }),
    },
    resolvedScope: {
      busStopCode: params.busStopCode,
      ...(params.serviceNo === undefined ? {} : { serviceNo: params.serviceNo }),
      serviceCount: data.length,
    },
    observedAt: getObservedAt(),
    upstreamTimestamp,
    coverage: "Stop-level bus arrival timings for the requested bus stop and optional service.",
  };
};

const getTrainAlertsMeta = (
  data: Readonly<{
    alerts: readonly Readonly<Record<string, unknown>>[];
    messages: readonly Readonly<Record<string, unknown>>[];
  }>,
): Readonly<Record<string, unknown>> => {
  const lines = Array.from(new Set(
    data.alerts
      .map((alert) => alert["line"])
      .filter((line): line is string => typeof line === "string" && line.trim() !== ""),
  ));
  const upstreamTimestamp = typeof data.messages[0]?.["createdDate"] === "string"
    ? data.messages[0]!["createdDate"]
    : null;

  return {
    requestedScope: { networkWide: true },
    resolvedScope: {
      networkWide: true,
      lines,
      alertCount: data.alerts.length,
      messageCount: data.messages.length,
    },
    observedAt: getObservedAt(),
    upstreamTimestamp,
    coverage: "Network-wide train service alerts and operator messages.",
  };
};

const getTrafficIncidentsMeta = (
  data: readonly Readonly<Record<string, unknown>>[],
): Readonly<Record<string, unknown>> => {
  const incidentTypes = Array.from(new Set(
    data
      .map((incident) => incident["type"])
      .filter((type): type is string => typeof type === "string" && type.trim() !== ""),
  ));

  return {
    requestedScope: { networkWide: true },
    resolvedScope: {
      networkWide: true,
      incidentCount: data.length,
      incidentTypes,
    },
    observedAt: getObservedAt(),
    upstreamTimestamp: null,
    coverage: "Live traffic incidents across Singapore.",
  };
};

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
      meta: getBusArrivalsMeta(params, data as unknown as readonly Readonly<Record<string, unknown>>[]),
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
      meta: getTrainAlertsMeta({
        alerts: data.alerts as unknown as readonly Readonly<Record<string, unknown>>[],
        messages: data.messages as unknown as readonly Readonly<Record<string, unknown>>[],
      }),
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
      meta: getTrafficIncidentsMeta(data as unknown as readonly Readonly<Record<string, unknown>>[]),
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
