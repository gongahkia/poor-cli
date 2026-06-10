import { ApiError, httpGet } from "@swee-sg/shared";
import type {
  NeaForecastResponse,
  NeaNormalizedAirQuality,
  NeaNormalizedForecast,
  NeaNormalizedRainfall,
  NeaPm25Response,
  NeaPsiResponse,
  NeaRainfallResponse,
} from "@swee-sg/shared";
import { withCache, buildCacheKey } from "../../middleware/cache-middleware.js";

const BASE_URL = "https://api-open.data.gov.sg/v2/real-time/api";

const neaGet = async <T>(path: string, params: Readonly<Record<string, string>> = {}): Promise<T> => {
  const url = new URL(`${BASE_URL}/${path}`);
  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, value);
  }

  return httpGet<T>(url.toString(), {
    apiName: "nea",
  });
};

const latest = <T>(items: readonly T[]): T => {
  const item = items[items.length - 1];
  if (item === undefined) {
    throw new ApiError({
      apiName: "nea",
      source: "NEA",
      statusCode: 404,
      code: "EMPTY_RESULT",
      message: "NEA returned no data for this query.",
      retryable: false,
      suggestedAction: "Try a broader query or omit the optional date filter.",
    });
  }
  return item;
};

const regionLocationMap = (
  regions: readonly {
    readonly name: string;
    readonly labelLocation: {
      readonly latitude: number;
      readonly longitude: number;
    };
  }[],
): Readonly<Record<string, { readonly lat: number; readonly lng: number }>> => {
  return Object.fromEntries(
    regions.map((region) => [
      region.name.toLowerCase(),
      {
        lat: region.labelLocation.latitude,
        lng: region.labelLocation.longitude,
      },
    ]),
  );
};

export const getForecast2Hr = async (
  area?: string,
  date?: string,
): Promise<readonly NeaNormalizedForecast[]> => {
  const cacheKey = buildCacheKey("nea", "forecast-2hr", { area, date });
  const { data } = await withCache(cacheKey, "REALTIME", async () => {
    const response = await neaGet<NeaForecastResponse>("two-hr-forecast", {
      ...(date === undefined ? {} : { date }),
    });
    const item = latest(response.data.items);
    const areaLocations = Object.fromEntries(
      response.data.area_metadata.map((metadata) => [
        metadata.name.toLowerCase(),
        {
          lat: metadata.label_location.latitude,
          lng: metadata.label_location.longitude,
        },
      ]),
    );
    const normalized = item.forecasts.map((forecast) => {
      const location = areaLocations[forecast.area.toLowerCase()];
      return {
        area: forecast.area,
        forecast: forecast.forecast,
        validFrom: item.valid_period.start,
        validTo: item.valid_period.end,
        validText: item.valid_period.text,
        updatedAt: item.update_timestamp,
        lat: location?.lat ?? null,
        lng: location?.lng ?? null,
      };
    });

    if (area === undefined) {
      return normalized;
    }

    const normalizedArea = area.toLowerCase();
    return normalized.filter((forecast) => forecast.area.toLowerCase() === normalizedArea);
  });
  return data;
};

export const getAirQuality = async (
  region?: string,
  date?: string,
): Promise<readonly NeaNormalizedAirQuality[]> => {
  const cacheKey = buildCacheKey("nea", "air-quality", { region, date });
  const { data } = await withCache(cacheKey, "REALTIME", async () => {
    const [psiResponse, pm25Response] = await Promise.all([
      neaGet<NeaPsiResponse>("psi", {
        ...(date === undefined ? {} : { date }),
      }),
      neaGet<NeaPm25Response>("pm25", {
        ...(date === undefined ? {} : { date }),
      }),
    ]);

    const psiItem = latest(psiResponse.data.items);
    const pm25Item = latest(pm25Response.data.items);
    const locations = regionLocationMap(psiResponse.data.regionMetadata);

    const regions = new Set<string>([
      ...Object.keys(psiItem.readings["psi_twenty_four_hourly"] ?? {}),
      ...Object.keys(psiItem.readings["pm25_twenty_four_hourly"] ?? {}),
      ...Object.keys(pm25Item.readings.pm25_one_hourly ?? {}),
    ]);

    const normalized = Array.from(regions)
      .filter((name) => name !== "national")
      .map((name) => {
        const location = locations[name.toLowerCase()];
        return {
          region: name,
          psi24h: psiItem.readings["psi_twenty_four_hourly"]?.[name] ?? null,
          pm25OneHourly: pm25Item.readings.pm25_one_hourly?.[name] ?? null,
          pm25TwentyFourHourly: psiItem.readings["pm25_twenty_four_hourly"]?.[name] ?? null,
          updatedAt: psiItem.updatedTimestamp,
          lat: location?.lat ?? null,
          lng: location?.lng ?? null,
        };
      });

    if (region === undefined) {
      return normalized;
    }

    const normalizedRegion = region.toLowerCase();
    return normalized.filter((item) => item.region.toLowerCase() === normalizedRegion);
  });
  return data;
};

export const getRainfall = async (
  stationId?: string,
  date?: string,
): Promise<readonly NeaNormalizedRainfall[]> => {
  const cacheKey = buildCacheKey("nea", "rainfall", { stationId, date });
  const { data } = await withCache(cacheKey, "REALTIME", async () => {
    const response = await neaGet<NeaRainfallResponse>("rainfall", {
      ...(date === undefined ? {} : { date }),
    });

    const latestReading = latest(response.data.readings);
    const stationMap = Object.fromEntries(
      response.data.stations.map((station) => [
        station.id,
        {
          name: station.name,
          lat: station.location.latitude,
          lng: station.location.longitude,
        },
      ]),
    );

    const normalized = latestReading.data.map((reading) => {
      const station = stationMap[reading.stationId];
      return {
        stationId: reading.stationId,
        stationName: station?.name ?? reading.stationId,
        value: reading.value,
        unit: response.data.readingUnit,
        timestamp: latestReading.timestamp,
        lat: station?.lat ?? null,
        lng: station?.lng ?? null,
      };
    });

    if (stationId === undefined) {
      return normalized;
    }

    const normalizedStationId = stationId.toLowerCase();
    return normalized.filter((reading) => reading.stationId.toLowerCase() === normalizedStationId);
  });
  return data;
};
