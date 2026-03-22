import { httpGet, TTL, ApiError } from "@sg-apis/shared";
import type { OneMapSearchResponse, GeocodeResult, ReverseGeocodeResponse, ReverseGeocodeResult, RouteResult, PopulationData, PopulationDataType } from "@sg-apis/shared";
import { withCache, buildCacheKey } from "../../middleware/cache-middleware.js";

const BASE_URL = process.env["MOCK_API_BASE_URL"]
  ? `${process.env["MOCK_API_BASE_URL"]}/onemap`
  : "https://www.onemap.gov.sg/api";

export const geocode = async (searchVal: string, limit = 10): Promise<GeocodeResult[]> => {
  const cacheKey = buildCacheKey("onemap", "geocode", { searchVal });
  const { data } = await withCache(cacheKey, TTL.STATIC, async () => {
    const url = `${BASE_URL}/common/elastic/search?searchVal=${encodeURIComponent(searchVal)}&returnGeom=Y&getAddrDetails=Y&pageNum=1`;
    const response = await httpGet<OneMapSearchResponse>(url, { apiName: "onemap" });

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
  buffer = 50,
): Promise<ReverseGeocodeResult | null> => {
  const cacheKey = buildCacheKey("onemap", "revgeocode", { lat, lng, buffer });
  const { data } = await withCache(cacheKey, TTL.STATIC, async () => {
    const url = `${BASE_URL}/public/revgeocode?location=${lat},${lng}&buffer=${buffer}&addressType=All`;
    const response = await httpGet<ReverseGeocodeResponse>(url, { apiName: "onemap" });

    const entry = response.GeocodeInfo?.[0];
    if (entry === undefined || entry.BUILDINGNAME === "" ) {
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
  const url = `${BASE_URL}/public/routingsvc/route?start=${startLat},${startLng}&end=${endLat},${endLng}&routeType=${routeType}`;
  const response = await httpGet<{
    status_message: string;
    status: number;
    route_instructions: unknown[][];
    route_name: string[];
    route_summary: { start_point: string; end_point: string; total_time: number; total_distance: number };
  }>(url, { apiName: "onemap" });

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
  const cacheKey = buildCacheKey("onemap", "population", { planningArea, year: yr, dataType: type });
  const { data } = await withCache(cacheKey, TTL.STATIC, async () => {
    const url = `${BASE_URL}/public/popapi/${type}?planningArea=${encodeURIComponent(planningArea)}&year=${yr}`;
    const response = await httpGet<Record<string, string>[]>(url, { apiName: "onemap" });
    return {
      planningArea,
      year: yr,
      data: response,
    };
  });
  return data;
};

export const convertSVY21toWGS84 = async (
  easting: number,
  northing: number,
): Promise<{ lat: number; lng: number }> => {
  const cacheKey = buildCacheKey("onemap", "convert", { from: "SVY21", x: easting, y: northing });
  const { data } = await withCache(cacheKey, TTL.STATIC, async () => {
    const url = `${BASE_URL}/common/convert/3414to4326?X=${easting}&Y=${northing}`;
    const response = await httpGet<{ latitude: number; longitude: number }>(url, { apiName: "onemap" });
    return { lat: response.latitude, lng: response.longitude };
  });
  return data;
};

export const convertWGS84toSVY21 = async (
  lat: number,
  lng: number,
): Promise<{ x: number; y: number }> => {
  const cacheKey = buildCacheKey("onemap", "convert", { from: "WGS84", x: lat, y: lng });
  const { data } = await withCache(cacheKey, TTL.STATIC, async () => {
    const url = `${BASE_URL}/common/convert/4326to3414?latitude=${lat}&longitude=${lng}`;
    const response = await httpGet<{ X: number; Y: number }>(url, { apiName: "onemap" });
    return { x: response.X, y: response.Y };
  });
  return data;
};
