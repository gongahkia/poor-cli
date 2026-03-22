import { httpGet, TTL, MasDataset, ApiError } from "@sg-apis/shared";
import type { MasResponse, MasQueryParams, MasRecord } from "@sg-apis/shared";
import { withCache, buildCacheKey } from "../../middleware/cache-middleware.js";

const BASE_URL = process.env["MOCK_API_BASE_URL"]
  ? `${process.env["MOCK_API_BASE_URL"]}/mas`
  : "https://eservices.mas.gov.sg/api/action/datastore";

export const getResourceId = (dataset: string): string => {
  const id = MasDataset[dataset as keyof typeof MasDataset];
  if (id === undefined) {
    throw new ApiError({
      apiName: "mas",
      statusCode: 400,
      message: `Unknown MAS dataset: ${dataset}`,
      retryable: false,
    });
  }
  return id;
};

export const query = async (
  resourceId: string,
  params?: MasQueryParams,
): Promise<MasRecord[]> => {
  const limit = params?.limit ?? 100;
  const offset = params?.offset ?? 0;

  const cacheKey = buildCacheKey("mas", "query", { resourceId, limit, offset, ...params?.filters });
  const { data } = await withCache(cacheKey, TTL.NEAR_REALTIME, async () => {
    let url = `${BASE_URL}/search.json?resource_id=${resourceId}&limit=${limit}&offset=${offset}`;
    if (params?.filters !== undefined) {
      url += `&filters=${encodeURIComponent(JSON.stringify(params.filters))}`;
    }
    if (params?.sort !== undefined) {
      url += `&sort=${encodeURIComponent(params.sort)}`;
    }

    const response = await httpGet<MasResponse>(url, { apiName: "mas" });
    if (!response.success) {
      throw new ApiError({
        apiName: "mas",
        statusCode: 500,
        message: "MAS query failed",
        retryable: true,
      });
    }

    let allRecords = [...response.result.records];

    // Auto-paginate
    const total = response.result.total;
    let currentOffset = offset + limit;
    while (currentOffset < total) {
      const nextUrl = `${BASE_URL}/search.json?resource_id=${resourceId}&limit=${limit}&offset=${currentOffset}`;
      const nextResponse = await httpGet<MasResponse>(nextUrl, { apiName: "mas" });
      if (nextResponse.success) {
        allRecords = [...allRecords, ...nextResponse.result.records];
      }
      currentOffset += limit;
    }

    return allRecords;
  });
  return data;
};
