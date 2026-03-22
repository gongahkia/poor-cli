import { httpGet, TTL, ApiError } from "@sg-apis/shared";
import type { DatagovV2ListResponse, DatagovDataset } from "@sg-apis/shared";
import { withCache, buildCacheKey } from "../../middleware/cache-middleware.js";

const BASE_URL = process.env["MOCK_API_BASE_URL"]
  ? `${process.env["MOCK_API_BASE_URL"]}/datagov`
  : "https://api-production.data.gov.sg/v2/public/api";

export const searchDatasets = async (keyword: string, limit = 10): Promise<DatagovDataset[]> => {
  const cacheKey = buildCacheKey("datagov", "search", { keyword, limit });
  const { data } = await withCache(cacheKey, TTL.DAILY, async () => {
    // data.gov.sg v2 does not have keyword search param - fetch pages and filter client-side
    const url = `${BASE_URL}/datasets?page=0&resultSize=50`;
    const response = await httpGet<DatagovV2ListResponse>(url, { apiName: "datagov" });

    if (response.code !== 0) {
      throw new ApiError({
        apiName: "datagov",
        statusCode: 500,
        message: response.errorMsg || "data.gov.sg query failed",
        retryable: true,
      });
    }

    const lowerKeyword = keyword.toLowerCase();
    return response.data.datasets
      .filter(
        (d) =>
          d.name.toLowerCase().includes(lowerKeyword) ||
          (d.description?.toLowerCase().includes(lowerKeyword) ?? false),
      )
      .slice(0, limit);
  });
  return data;
};

export const getDataset = async (datasetId: string): Promise<DatagovDataset | null> => {
  const cacheKey = buildCacheKey("datagov", "dataset", { datasetId });
  const { data } = await withCache(cacheKey, TTL.DAILY, async () => {
    const url = `${BASE_URL}/datasets/${datasetId}/metadata`;
    try {
      const response = await httpGet<{ code: number; data: { columnMetadata: unknown } }>(url, { apiName: "datagov" });
      if (response.code !== 0) return null;
      return { datasetId, name: datasetId, status: "active", format: "CSV", createdAt: "", lastUpdatedAt: "", managedByAgencyName: "" } as DatagovDataset;
    } catch {
      return null;
    }
  });
  return data;
};

export const listCollections = async (): Promise<{ id: string; name: string; description: string }[]> => {
  const cacheKey = buildCacheKey("datagov", "collections", {});
  const { data } = await withCache(cacheKey, TTL.DAILY, async () => {
    // v2 API uses datasets endpoint - group by agency as "collections"
    const url = `${BASE_URL}/datasets?page=0&resultSize=50`;
    const response = await httpGet<DatagovV2ListResponse>(url, { apiName: "datagov" });

    const agencies = new Map<string, { count: number }>();
    for (const ds of response.data.datasets) {
      const existing = agencies.get(ds.managedByAgencyName);
      if (existing !== undefined) {
        existing.count++;
      } else {
        agencies.set(ds.managedByAgencyName, { count: 1 });
      }
    }

    return Array.from(agencies.entries()).map(([name, { count }]) => ({
      id: name.toLowerCase().replace(/\s+/g, "-"),
      name,
      description: `${count} datasets managed by ${name}`,
    }));
  });
  return data;
};
