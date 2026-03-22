import { ApiError, createLogger, getMockApiBaseUrl } from "@sg-apis/shared";
import type {
  OneMapSearchResponse,
  GeocodeResult,
  ReverseGeocodeResponse,
  ReverseGeocodeResult,
  RouteResult,
  PopulationData,
  PopulationDataType,
} from "@sg-apis/shared";
import { withCache, buildCacheKey } from "../../middleware/cache-middleware.js";
import { authenticatedFetch } from "./auth.js";

const logger = createLogger("onemap-client");

const getBaseUrl = (): string => {
  const mockApiBaseUrl = getMockApiBaseUrl();
  return mockApiBaseUrl !== undefined
    ? `${mockApiBaseUrl}/onemap`
    : "https://www.onemap.gov.sg/api";
};

const isMockMode = (): boolean => getMockApiBaseUrl() !== undefined;

const onemapGet = async <T>(url: string): Promise<T> => {
  if (isMockMode()) {
    // In mock mode, skip auth
    const response = await fetch(url);
    if (!response.ok) {
      throw new ApiError({
        apiName: "onemap",
        statusCode: response.status,
        message: `OneMap request failed: ${response.statusText}`,
        retryable: response.status >= 500,
      });
    }
    return (await response.json()) as T;
  }

  // In real mode, use authenticated fetch
  try {
    const response = await authenticatedFetch(url);
    if (!response.ok) {
      throw new ApiError({
        apiName: "onemap",
        statusCode: response.status,
        message: `OneMap request failed: ${response.statusText}`,
        retryable: response.status >= 500,
      });
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    // If auth fails (credentials not configured), fall back to unauthenticated
    logger.warn("auth failed, attempting unauthenticated request", {
      error: error instanceof Error ? error.message : String(error),
    });
    const response = await fetch(url);
    if (!response.ok) {
      throw new ApiError({
        apiName: "onemap",
        statusCode: response.status,
        message: `OneMap request failed: ${response.statusText}`,
        retryable: response.status >= 500,
      });
    }
    return (await response.json()) as T;
  }
};

export const geocode = async (searchVal: string, limit = 10): Promise<GeocodeResult[]> => {
  const cacheKey = buildCacheKey("onemap", "geocode", { searchVal });
  const { data } = await withCache(cacheKey, "STATIC", async () => {
    const url = `${getBaseUrl()}/common/elastic/search?searchVal=${encodeURIComponent(searchVal)}&returnGeom=Y&getAddrDetails=Y&pageNum=1`;
    const response = await onemapGet<OneMapSearchResponse>(url);

    return response.results.slice(0, limit).map((r) => ({
      address: r.ADDRESS,
      building: r.BUILDING,
      postal: r.POSTAL === "NIL" ? null : r.POSTAL,
      lat: parseFloat(r.LATITUDE),
      lng: parseFloat(r.LONGITUDE),
      x: parseFloat(r.X),
      y: parseFloat(r.Y),
    }));
  });
  return data;
};

export const reverseGeocode = async (
  lat: number,
  lng: number,
  buffer = 50, // WHY: 50 meters covers most block-level lookups in dense Singapore
): Promise<ReverseGeocodeResult | null> => {
  const cacheKey = buildCacheKey("onemap", "revgeocode", { lat, lng, buffer });
  const { data } = await withCache(cacheKey, "STATIC", async () => {
    const url = `${getBaseUrl()}/public/revgeocode?location=${lat},${lng}&buffer=${buffer}&addressType=All`;
    const response = await onemapGet<ReverseGeocodeResponse>(url);

    const entry = response.GeocodeInfo?.[0];
    if (entry === undefined || entry.BUILDINGNAME === "") {
      return null;
    }

    return {
      building: entry.BUILDINGNAME,
      address: `${entry.BLOCK} ${entry.ROAD}`.trim(),
      postal: entry.POSTALCODE === "" ? null : entry.POSTALCODE,
      lat: parseFloat(entry.LATITUDE),
      lng: parseFloat(entry.LONGITUDE),
    };
  });
  return data;
};

export const getRoute = async (
  startLat: number,
  startLng: number,
  endLat: number,
  endLng: number,
  routeType: string,
): Promise<RouteResult> => {
  const url = `${getBaseUrl()}/public/routingsvc/route?start=${startLat},${startLng}&end=${endLat},${endLng}&routeType=${routeType}`;
  const response = await onemapGet<{
    status_message: string;
    status: number;
    route_instructions: unknown[][];
    route_name: string[];
    route_summary: {
      start_point: string;
      end_point: string;
      total_time: number;
      total_distance: number;
    };
  }>(url);

  if (response.status !== 0) {
    throw new ApiError({
      apiName: "onemap",
      statusCode: 400,
      message: response.status_message || "Route not found",
      retryable: false,
    });
  }

  return {
    totalDistance: response.route_summary.total_distance,
    totalTime: response.route_summary.total_time,
    instructions: (response.route_instructions ?? []).map((inst) => ({
      instruction: String(inst[0] ?? ""),
      road: String(inst[1] ?? ""),
      distance: Number(inst[2] ?? 0),
    })),
    routeName: response.route_name,
  };
};

export const getPopulationData = async (
  planningArea: string,
  year?: string,
  dataType?: PopulationDataType,
): Promise<PopulationData> => {
  const type = dataType ?? "getPopulationAgeGroup";
  const yr = year ?? "2020";
  const cacheKey = buildCacheKey("onemap", "population", {
    planningArea,
    year: yr,
    dataType: type,
  });
  const { data } = await withCache(cacheKey, "STATIC", async () => {
    const url = `${getBaseUrl()}/public/popapi/${type}?planningArea=${encodeURIComponent(planningArea)}&year=${yr}`;
    const response = await onemapGet<Record<string, string>[]>(url);
    return { planningArea, year: yr, data: response };
  });
  return data;
};

export const convertSVY21toWGS84 = async (
  easting: number,
  northing: number,
): Promise<{ lat: number; lng: number }> => {
  const cacheKey = buildCacheKey("onemap", "convert", { from: "SVY21", x: easting, y: northing });
  const { data } = await withCache(cacheKey, "STATIC", async () => {
    const url = `${getBaseUrl()}/common/convert/3414to4326?X=${easting}&Y=${northing}`;
    const response = await onemapGet<{ latitude: number; longitude: number }>(url);
    return { lat: response.latitude, lng: response.longitude };
  });
  return data;
};

export const convertWGS84toSVY21 = async (
  lat: number,
  lng: number,
): Promise<{ x: number; y: number }> => {
  const cacheKey = buildCacheKey("onemap", "convert", { from: "WGS84", x: lat, y: lng });
  const { data } = await withCache(cacheKey, "STATIC", async () => {
    const url = `${getBaseUrl()}/common/convert/4326to3414?latitude=${lat}&longitude=${lng}`;
    const response = await onemapGet<{ X: number; Y: number }>(url);
    return { x: response.X, y: response.Y };
  });
  return data;
};
