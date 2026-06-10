import { createHash } from "node:crypto";
import { Cache, createLogger, getCacheTtl } from "@swee-sg/shared";
import type { TTLKey } from "@swee-sg/shared";

const logger = createLogger("cache-middleware");

let cacheInstance: Cache | null = null;
const inFlightFetches = new Map<string, Promise<unknown>>();

export const getCache = (): Cache => {
  if (cacheInstance === null) {
    cacheInstance = new Cache();
  }
  return cacheInstance;
};

export const closeCache = (): void => {
  if (cacheInstance !== null) {
    cacheInstance.close();
    cacheInstance = null;
  }
  inFlightFetches.clear();
};

const stableJsonValue = (value: unknown): unknown => {
  if (Array.isArray(value)) {
    return value.map(stableJsonValue);
  }

  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Readonly<Record<string, unknown>>)
        .filter(([, nestedValue]) => nestedValue !== undefined)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, nestedValue]) => [key, stableJsonValue(nestedValue)]),
    );
  }

  return value;
};

export const buildCacheKey = (
  apiName: string,
  operation: string,
  params: Readonly<Record<string, unknown>>,
): string => {
  const sorted = JSON.stringify(stableJsonValue(params));
  const hash = createHash("md5").update(sorted).digest("hex").slice(0, 8);
  return `${apiName}:${operation}:${hash}`;
};

export const withCache = async <T>(
  key: string,
  ttlKey: TTLKey,
  fetcher: () => Promise<T>,
): Promise<{ data: T; cached: boolean; stale?: boolean }> => {
  const cache = getCache();
  const cached = cache.getFreshOrStale(key);
  if (cached !== null && !cached.expired) {
    return { data: JSON.parse(cached.value) as T, cached: true };
  }

  const existingFetch = inFlightFetches.get(key);
  if (existingFetch !== undefined) {
    try {
      return { data: (await existingFetch) as T, cached: false };
    } catch (error) {
      if (cached !== null) {
        logger.warn("serving stale cache entry after shared refresh failed", {
          key,
          ageSeconds: cached.ageSeconds,
          error: error instanceof Error ? error.message : String(error),
          ttlKey,
        });
        return { data: JSON.parse(cached.value) as T, cached: true, stale: true };
      }
      throw error;
    }
  }

  const fetchPromise = Promise.resolve()
    .then(fetcher)
    .then((data) => {
      cache.set(key, JSON.stringify(data), getCacheTtl(ttlKey));
      return data;
    })
    .finally(() => {
      inFlightFetches.delete(key);
    });

  inFlightFetches.set(key, fetchPromise);

  try {
    return { data: await fetchPromise, cached: false };
  } catch (error) {
    if (cached !== null) {
      logger.warn("serving stale cache entry after refresh failed", {
        key,
        ageSeconds: cached.ageSeconds,
        error: error instanceof Error ? error.message : String(error),
        ttlKey,
      });
      return { data: JSON.parse(cached.value) as T, cached: true, stale: true };
    }
    throw error;
  }
};
