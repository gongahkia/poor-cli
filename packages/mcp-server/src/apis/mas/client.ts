import { httpGet, MasDataset, ApiError, getMockApiBaseUrl } from "@sg-apis/shared";
import type { MasResponse, MasQueryParams, MasRecord } from "@sg-apis/shared";
import { withCache, buildCacheKey } from "../../middleware/cache-middleware.js";

const getBaseUrl = (): string => {
  const mockApiBaseUrl = getMockApiBaseUrl();
  return mockApiBaseUrl !== undefined
    ? `${mockApiBaseUrl}/mas`
    : "https://eservices.mas.gov.sg/api/action/datastore";
};

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

  const cacheKey = buildCacheKey("mas", "query", {
    resourceId,
    limit,
    offset,
    sort: params?.sort,
    filters: params?.filters,
  });
  const { data } = await withCache(cacheKey, "NEAR_REALTIME", async () => {
    const buildSearchUrl = (currentOffset: number): string => {
      let url = `${getBaseUrl()}/search.json?resource_id=${resourceId}&limit=${limit}&offset=${currentOffset}`;
      if (params?.filters !== undefined) {
        url += `&filters=${encodeURIComponent(JSON.stringify(params.filters))}`;
      }
      if (params?.sort !== undefined) {
        url += `&sort=${encodeURIComponent(params.sort)}`;
      }
      return url;
    };

    const url = buildSearchUrl(offset);

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
      const nextUrl = buildSearchUrl(currentOffset);
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
