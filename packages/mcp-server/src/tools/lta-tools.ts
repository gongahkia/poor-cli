import {
  LtaBusArrivalsSchema,
  LtaCarparkAvailabilitySchema,
  LtaRoadOpeningsSchema,
  LtaRoadWorksSchema,
  LtaTaxiAvailabilitySchema,
  LtaTrafficImagesSchema,
  LtaTrainAlertsSchema,
  LtaTrafficIncidentsSchema,
  formatResponse,
  resolveOutputFormat,
  validateInput,
} from "@dude/shared";
import type { OutputFormat, ToolResult } from "@dude/shared";
import {
  getBusArrivals,
  getCarparkAvailability,
  getRoadOpenings,
  getRoadWorks,
  getTaxiAvailability,
  getTrafficImages,
  getTrafficIncidents,
  getTrainAlerts,
} from "../apis/lta/client.js";
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

const getRoadEventsMeta = (
  data: readonly Readonly<Record<string, unknown>>[],
  eventType: "road-work" | "road-opening",
): Readonly<Record<string, unknown>> => {
  const roadNames = Array.from(new Set(
    data
      .map((event) => event["roadName"])
      .filter((name): name is string => typeof name === "string" && name.trim() !== ""),
  ));

  return {
    requestedScope: { networkWide: true },
    resolvedScope: {
      networkWide: true,
      eventType,
      eventCount: data.length,
      roadNames,
    },
    observedAt: getObservedAt(),
    upstreamTimestamp: null,
    coverage: eventType === "road-work"
      ? "Live road-work events across Singapore."
      : "Live road-opening events across Singapore.",
  };
};

const getTrafficImagesMeta = (
  data: readonly Readonly<Record<string, unknown>>[],
): Readonly<Record<string, unknown>> => {
  const latestTimestamp = data
    .map((camera) => camera["timestamp"])
    .find((timestamp): timestamp is string => typeof timestamp === "string" && timestamp.trim() !== "");

  return {
    requestedScope: { networkWide: true },
    resolvedScope: {
      networkWide: true,
      cameraCount: data.length,
    },
    observedAt: getObservedAt(),
    upstreamTimestamp: latestTimestamp ?? null,
    coverage: "Traffic camera snapshots sourced from data.gov.sg transport feeds.",
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

export const handleLtaRoadWorks = async (
  params: Readonly<{ format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = await getRoadWorks();
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: data,
      meta: getRoadEventsMeta(data as unknown as readonly Readonly<Record<string, unknown>>[], "road-work"),
    },
  };
};

export const handleLtaRoadOpenings = async (
  params: Readonly<{ format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = await getRoadOpenings();
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: data,
      meta: getRoadEventsMeta(data as unknown as readonly Readonly<Record<string, unknown>>[], "road-opening"),
    },
  };
};

export const handleLtaTrafficImages = async (
  params: Readonly<{ format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = await getTrafficImages();
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: data,
      meta: getTrafficImagesMeta(data as unknown as readonly Readonly<Record<string, unknown>>[]),
    },
  };
};

const getCarparkMeta = (
  params: Readonly<{ carparkId?: string | undefined; development?: string | undefined }>,
  data: readonly Readonly<Record<string, unknown>>[],
): Readonly<Record<string, unknown>> => {
  const agencies = Array.from(new Set(
    data.map((row) => row["agency"]).filter((v): v is string => typeof v === "string" && v.trim() !== ""),
  ));
  return {
    requestedScope: {
      carparkId: params.carparkId ?? null,
      development: params.development ?? null,
    },
    resolvedScope: { rowCount: data.length, agencies },
    observedAt: getObservedAt(),
    upstreamTimestamp: null,
    coverage: "Live LTA DataMall carpark availability for HDB, URA, and LTA-managed carparks.",
  };
};

export const handleLtaCarparkAvailability = async (
  params: Readonly<{ carparkId?: string | undefined; development?: string | undefined; limit?: number | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = await getCarparkAvailability(params);
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: data,
      meta: getCarparkMeta(params, data as unknown as readonly Readonly<Record<string, unknown>>[]),
    },
  };
};

const getTaxiMeta = (
  data: readonly Readonly<Record<string, unknown>>[],
): Readonly<Record<string, unknown>> => ({
  requestedScope: { networkWide: true },
  resolvedScope: { networkWide: true, taxiCount: data.length },
  observedAt: getObservedAt(),
  upstreamTimestamp: null,
  coverage: "Live LTA DataMall available taxi positions across Singapore.",
});

export const handleLtaTaxiAvailability = async (
  params: Readonly<{ limit?: number | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  const data = await getTaxiAvailability(params);
  const format = resolveOutputFormat(params.format);
  const text = formatResponse(data as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: data,
      meta: getTaxiMeta(data as unknown as readonly Readonly<Record<string, unknown>>[]),
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
  {
    name: "sg_lta_road_works",
    description: "Get live LTA road-work events with start and end timing context.",
    surface: "canonical",
    inputSchema: LtaRoadWorksSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleLtaRoadWorks(validateInput(LtaRoadWorksSchema, input)),
  },
  {
    name: "sg_lta_road_openings",
    description: "Get live LTA road-opening events with start and end timing context.",
    surface: "canonical",
    inputSchema: LtaRoadOpeningsSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleLtaRoadOpenings(validateInput(LtaRoadOpeningsSchema, input)),
  },
  {
    name: "sg_lta_traffic_images",
    description: "Get live Singapore traffic camera image references with camera coordinates.",
    surface: "canonical",
    inputSchema: LtaTrafficImagesSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleLtaTrafficImages(validateInput(LtaTrafficImagesSchema, input)),
  },
  {
    name: "sg_lta_carpark_availability",
    description: "Get live LTA DataMall carpark availability with optional filters on carpark id or development name.",
    surface: "canonical",
    inputSchema: LtaCarparkAvailabilitySchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleLtaCarparkAvailability(validateInput(LtaCarparkAvailabilitySchema, input)),
  },
  {
    name: "sg_lta_taxi_availability",
    description: "Get live LTA DataMall available taxi coordinates across Singapore, bounded by an optional limit.",
    surface: "canonical",
    inputSchema: LtaTaxiAvailabilitySchema.shape,
    handler: async (input: unknown): Promise<ToolResult> =>
      handleLtaTaxiAvailability(validateInput(LtaTaxiAvailabilitySchema, input)),
  },
];
