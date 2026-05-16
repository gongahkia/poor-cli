import { ApiError, Keystore, httpGet } from "@dude/shared";
import type {
  DatagovTrafficImagesResponse,
  LtaBusArrivalResponse,
  LtaBusStopsResponse,
  LtaNormalizedBusStop,
  LtaNormalizedBusArrival,
  LtaNormalizedRoadEvent,
  LtaNormalizedTrafficCamera,
  LtaNormalizedTrafficIncident,
  LtaNormalizedTrainAlert,
  LtaNormalizedTrainAlertMessage,
  LtaRoadEventsResponse,
  LtaTrafficIncidentsResponse,
  LtaTrainAlertsResponse,
} from "@dude/shared";
import { withCache, buildCacheKey } from "../../middleware/cache-middleware.js";

const BASE_URL = "https://datamall2.mytransport.sg/ltaodataservice";
const DATA_GOV_TRAFFIC_IMAGES_URL = "https://api.data.gov.sg/v1/transport/traffic-images";

let keystoreInstance: Keystore | null = null;

const getKeystore = (): Keystore => {
  if (keystoreInstance === null) {
    keystoreInstance = new Keystore();
  }
  return keystoreInstance;
};

const getApiKey = (): string => {
  const envKey = process.env["SG_API_LTA_KEY"];
  if (envKey !== undefined && envKey !== "") {
    return envKey;
  }

  const key = getKeystore().getKey("lta");
  if (key === null) {
    throw new ApiError({
      apiName: "lta",
      source: "LTA DataMall",
      statusCode: 401,
      code: "AUTH_MISSING",
      message: "LTA API key not configured.",
      retryable: false,
      suggestedAction: "Set SG_API_LTA_KEY or run sg_key_set with apiName=lta.",
    });
  }
  return key;
};

const ltaGet = async <T>(
  path: string,
  params: Readonly<Record<string, string>> = {},
): Promise<T> => {
  const apiKey = getApiKey();
  const url = new URL(`${BASE_URL}/${path}`);
  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, value);
  }

  return httpGet<T>(url.toString(), {
    apiName: "lta",
    headers: {
      AccountKey: apiKey,
    },
  });
};

const normalizeNullableNumber = (value: number | string | undefined): number | null => {
  if (value === undefined || value === "") {
    return null;
  }
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const normalizeTiming = (
  timing: Readonly<{
    OriginCode?: string;
    DestinationCode?: string;
    EstimatedArrival?: string;
    Monitored?: number;
    Latitude?: string;
    Longitude?: string;
    VisitNumber?: string;
    Load?: string;
    Feature?: string;
    Type?: string;
  }>,
  ordinal: 1 | 2 | 3,
) => ({
  ordinal,
  estimatedArrival: timing.EstimatedArrival ?? null,
  load: timing.Load ?? null,
  feature: timing.Feature ?? null,
  type: timing.Type ?? null,
  monitored: timing.Monitored === 1,
  visitNumber: timing.VisitNumber ?? null,
  originCode: timing.OriginCode ?? null,
  destinationCode: timing.DestinationCode ?? null,
  lat: normalizeNullableNumber(timing.Latitude),
  lng: normalizeNullableNumber(timing.Longitude),
});

const normalizeRoadEvent = (
  value: Readonly<{
    EventID?: string;
    StartDate?: string;
    EndDate?: string;
    Latitude?: number | string;
    Longitude?: number | string;
    RoadName?: string;
    Message?: string;
  }>,
  eventType: "road-work" | "road-opening",
): LtaNormalizedRoadEvent => ({
  id: value.EventID ?? `${eventType}:${value.RoadName ?? "unknown"}:${value.StartDate ?? "na"}`,
  eventType,
  lat: normalizeNullableNumber(value.Latitude),
  lng: normalizeNullableNumber(value.Longitude),
  roadName: value.RoadName ?? null,
  message: value.Message ?? "",
  startTime: value.StartDate ?? null,
  endTime: value.EndDate ?? null,
});

const normalizeBusStop = (
  value: Readonly<{
    BusStopCode?: string;
    Description?: string;
    RoadName?: string;
    Latitude?: number | string;
    Longitude?: number | string;
  }>,
): LtaNormalizedBusStop | null => {
  if (typeof value.BusStopCode !== "string" || value.BusStopCode.trim() === "") {
    return null;
  }
  return {
    busStopCode: value.BusStopCode,
    description: value.Description ?? null,
    roadName: value.RoadName ?? null,
    lat: normalizeNullableNumber(value.Latitude),
    lng: normalizeNullableNumber(value.Longitude),
  };
};

export const getBusArrivals = async (
  busStopCode: string,
  serviceNo?: string,
): Promise<readonly LtaNormalizedBusArrival[]> => {
  const cacheKey = buildCacheKey("lta", "bus-arrivals", { busStopCode, serviceNo });
  const { data } = await withCache(cacheKey, "REALTIME", async () => {
    const response = await ltaGet<LtaBusArrivalResponse>("v3/BusArrival", {
      BusStopCode: busStopCode,
      ...(serviceNo === undefined ? {} : { ServiceNo: serviceNo }),
    });

    return (response.Services ?? [])
      .filter((service) => serviceNo === undefined || service.ServiceNo === serviceNo)
      .map((service) => ({
        busStopCode: response.BusStopCode,
        serviceNo: service.ServiceNo,
        operator: service.Operator,
        arrivals: [
          normalizeTiming(service.NextBus, 1),
          normalizeTiming(service.NextBus2, 2),
          normalizeTiming(service.NextBus3, 3),
        ],
      }));
  });
  return data;
};

export const getTrainAlerts = async (): Promise<{
  readonly alerts: readonly LtaNormalizedTrainAlert[];
  readonly messages: readonly LtaNormalizedTrainAlertMessage[];
}> => {
  const cacheKey = buildCacheKey("lta", "train-alerts", {});
  const { data } = await withCache(cacheKey, "REALTIME", async () => {
    const response = await ltaGet<LtaTrainAlertsResponse>("TrainServiceAlerts");
    const alerts = (response.value ?? []).map((entry) => ({
      line: entry.Line ?? "Unknown",
      status: entry.Status ?? null,
      direction: entry.Direction ?? null,
      stations:
        entry.Stations?.split(",")
          .map((station) => station.trim())
          .filter((station) => station.length > 0) ?? [],
      freePublicBus:
        entry.FreePublicBus?.split(",")
          .map((station) => station.trim())
          .filter((station) => station.length > 0) ?? [],
      freeMrtShuttle:
        entry.FreeMRTShuttle?.split(",")
          .map((station) => station.trim())
          .filter((station) => station.length > 0) ?? [],
      mrtShuttleDirection: entry.MRTShuttleDirection ?? null,
    }));
    const messages = (response.Message ?? [])
      .filter((message) => typeof message.Content === "string" && message.Content.trim() !== "")
      .map((message) => ({
        content: message.Content!,
        createdDate: message.CreatedDate ?? null,
      }));

    return { alerts, messages };
  });
  return data;
};

export const getTrafficIncidents = async (): Promise<readonly LtaNormalizedTrafficIncident[]> => {
  const cacheKey = buildCacheKey("lta", "traffic-incidents", {});
  const { data } = await withCache(cacheKey, "REALTIME", async () => {
    const response = await ltaGet<LtaTrafficIncidentsResponse>("TrafficIncidents");
    return (response.value ?? []).map((incident) => ({
      type: incident.Type ?? "Unknown",
      lat: normalizeNullableNumber(incident.Latitude),
      lng: normalizeNullableNumber(incident.Longitude),
      message: incident.Message ?? "",
    }));
  });
  return data;
};

export const getRoadWorks = async (): Promise<readonly LtaNormalizedRoadEvent[]> => {
  const cacheKey = buildCacheKey("lta", "road-works", {});
  const { data } = await withCache(cacheKey, "REALTIME", async () => {
    const response = await ltaGet<LtaRoadEventsResponse>("RoadWorks");
    return (response.value ?? []).map((entry) => normalizeRoadEvent(entry, "road-work"));
  });
  return data;
};

export const getRoadOpenings = async (): Promise<readonly LtaNormalizedRoadEvent[]> => {
  const cacheKey = buildCacheKey("lta", "road-openings", {});
  const { data } = await withCache(cacheKey, "REALTIME", async () => {
    const response = await ltaGet<LtaRoadEventsResponse>("RoadOpenings");
    return (response.value ?? []).map((entry) => normalizeRoadEvent(entry, "road-opening"));
  });
  return data;
};

export const getTrafficImages = async (): Promise<readonly LtaNormalizedTrafficCamera[]> => {
  const cacheKey = buildCacheKey("datagov", "traffic-images", {});
  const { data } = await withCache(cacheKey, "REALTIME", async () => {
    const payload = await httpGet<DatagovTrafficImagesResponse>(DATA_GOV_TRAFFIC_IMAGES_URL, {
      apiName: "datagov",
    });
    const latest = payload.items?.[0];
    const timestamp = latest?.timestamp ?? null;
    return (latest?.cameras ?? [])
      .filter((camera) => typeof camera.camera_id === "string" && typeof camera.image === "string")
      .map((camera) => ({
        cameraId: camera.camera_id!,
        imageUrl: camera.image!,
        timestamp: camera.timestamp ?? timestamp,
        lat: normalizeNullableNumber(camera.location?.latitude),
        lng: normalizeNullableNumber(camera.location?.longitude),
      }));
  });
  return data;
};

type LtaCarparkAvailabilityRecord = Readonly<{
  CarParkID?: string;
  Area?: string;
  Development?: string;
  Location?: string;
  AvailableLots?: number | string;
  LotType?: string;
  Agency?: string;
}>;

type LtaCarparkAvailabilityResponse = Readonly<{ value?: readonly LtaCarparkAvailabilityRecord[] }>;

export type LtaNormalizedCarpark = {
  readonly carparkId: string;
  readonly development: string | null;
  readonly area: string | null;
  readonly availableLots: number | null;
  readonly lotType: string | null;
  readonly agency: string | null;
  readonly lat: number | null;
  readonly lng: number | null;
};

const parseCarparkLocation = (location: string | undefined): { lat: number | null; lng: number | null } => {
  if (location === undefined) return { lat: null, lng: null };
  const parts = location.trim().split(/\s+/);
  if (parts.length !== 2) return { lat: null, lng: null };
  return { lat: normalizeNullableNumber(parts[0]), lng: normalizeNullableNumber(parts[1]) };
};

export const getCarparkAvailability = async (
  params: Readonly<{ carparkId?: string | undefined; development?: string | undefined; limit?: number | undefined }> = {},
): Promise<readonly LtaNormalizedCarpark[]> => {
  const cacheKey = buildCacheKey("lta", "carpark-availability", params);
  const { data } = await withCache(cacheKey, "REALTIME", async () => {
    const records: LtaCarparkAvailabilityRecord[] = [];
    let skip = 0;
    // LTA returns up to 500 rows per page; iterate until exhausted or cap at 2000.
    while (skip < 2000) {
      const response = await ltaGet<LtaCarparkAvailabilityResponse>("CarParkAvailabilityv2", { "$skip": String(skip) });
      const page = response.value ?? [];
      records.push(...page);
      if (page.length < 500) break;
      skip += 500;
    }
    return records;
  });

  const carparkId = params.carparkId?.trim().toUpperCase();
  const devNeedle = params.development?.trim().toLowerCase();
  const filtered = data.filter((row) => {
    if (carparkId !== undefined && (row.CarParkID ?? "").toUpperCase() !== carparkId) return false;
    if (devNeedle !== undefined && !(row.Development ?? "").toLowerCase().includes(devNeedle)) return false;
    return true;
  });
  const limited = filtered.slice(0, Math.min(params.limit ?? 200, 500));
  return limited.map((row) => {
    const { lat, lng } = parseCarparkLocation(row.Location);
    return {
      carparkId: row.CarParkID ?? "",
      development: row.Development ?? null,
      area: row.Area ?? null,
      availableLots: normalizeNullableNumber(row.AvailableLots),
      lotType: row.LotType ?? null,
      agency: row.Agency ?? null,
      lat,
      lng,
    };
  });
};

type LtaTaxiAvailabilityResponse = Readonly<{
  value?: readonly Readonly<{ Longitude?: number | string; Latitude?: number | string }>[];
}>;

export type LtaNormalizedTaxiPosition = {
  readonly lat: number | null;
  readonly lng: number | null;
};

export const getTaxiAvailability = async (
  params: Readonly<{ limit?: number | undefined }> = {},
): Promise<readonly LtaNormalizedTaxiPosition[]> => {
  const cacheKey = buildCacheKey("lta", "taxi-availability", params);
  const { data } = await withCache(cacheKey, "REALTIME", async () => {
    const records: LtaNormalizedTaxiPosition[] = [];
    let skip = 0;
    const cap = Math.min(params.limit ?? 1000, 5000);
    while (records.length < cap) {
      const response = await ltaGet<LtaTaxiAvailabilityResponse>("Taxi-Availability", { "$skip": String(skip) });
      const page = response.value ?? [];
      for (const row of page) {
        records.push({ lat: normalizeNullableNumber(row.Latitude), lng: normalizeNullableNumber(row.Longitude) });
      }
      if (page.length < 500) break;
      skip += 500;
    }
    return records.slice(0, cap);
  });
  return data;
};

const getAllBusStops = async (): Promise<readonly LtaNormalizedBusStop[]> => {
  const cacheKey = buildCacheKey("lta", "bus-stops-all", {});
  const { data } = await withCache(cacheKey, "STATIC", async () => {
    const records: LtaNormalizedBusStop[] = [];
    let skip = 0;

    while (true) {
      const response = await ltaGet<LtaBusStopsResponse>("BusStops", { "$skip": String(skip) });
      const rows = (response.value ?? [])
        .map((entry) => normalizeBusStop(entry))
        .filter((entry): entry is LtaNormalizedBusStop => entry !== null);
      records.push(...rows);
      if (rows.length < 500) {
        break;
      }
      skip += 500;
    }

    return records;
  });
  return data;
};

export const getBusStopLookups = async (
  busStopCodes: readonly string[],
): Promise<Readonly<Record<string, LtaNormalizedBusStop>>> => {
  if (busStopCodes.length === 0) {
    return {};
  }
  const normalizedCodes = new Set(busStopCodes);
  const all = await getAllBusStops();
  const result: Record<string, LtaNormalizedBusStop> = {};
  for (const record of all) {
    if (normalizedCodes.has(record.busStopCode)) {
      result[record.busStopCode] = record;
    }
  }
  return result;
};
