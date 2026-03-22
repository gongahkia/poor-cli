import { createHash } from "node:crypto";
import { Cache } from "@sg-apis/shared";

let cacheInstance: Cache | null = null;

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
};

export const buildCacheKey = (
  apiName: string,
  operation: string,
  params: Readonly<Record<string, unknown>>,
): string => {
  const sorted = JSON.stringify(params, Object.keys(params).sort());
  const hash = createHash("md5").update(sorted).digest("hex").slice(0, 8);
  return `${apiName}:${operation}:${hash}`;
};

export const withCache = async <T>(
  key: string,
  ttl: number,
  fetcher: () => Promise<T>,
): Promise<{ data: T; cached: boolean }> => {
  const cache = getCache();
  const cached = cache.get(key);
  if (cached !== null) {
    return { data: JSON.parse(cached) as T, cached: true };
  }

  const data = await fetcher();
  cache.set(key, JSON.stringify(data), ttl);
  return { data, cached: false };
};
