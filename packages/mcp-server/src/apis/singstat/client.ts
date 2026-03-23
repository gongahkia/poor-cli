import { httpGet, getMockApiBaseUrl } from "@sg-apis/shared";
import type { SingStatSearchResponse, SingStatTableResponse, Dataset, TableData, NormalizedRow, TableMetadata, TimeSeriesRow, TableOptions } from "@sg-apis/shared";
import { withCache, buildCacheKey } from "../../middleware/cache-middleware.js";

const getBaseUrl = (): string => {
  const mockApiBaseUrl = getMockApiBaseUrl();
  return mockApiBaseUrl !== undefined
    ? `${mockApiBaseUrl}/singstat`
    : "https://tablebuilder.singstat.gov.sg/api/table";
};

export const searchDatasets = async (keyword: string, limit = 20): Promise<Dataset[]> => {
  const cacheKey = buildCacheKey("singstat", "search", { keyword, limit });
  const { data } = await withCache(cacheKey, "DAILY", async () => {
    const url = `${getBaseUrl()}/resourceId?keyword=${encodeURIComponent(keyword)}&searchOption=all&limit=${limit}`;
    const response = await httpGet<SingStatSearchResponse>(url, { apiName: "singstat" });
    if (response.StatusCode !== 200) {
      throw new (await import("@sg-apis/shared")).ApiError({
        apiName: "singstat",
        statusCode: response.StatusCode,
        message: response.Message || "SingStat search failed",
        retryable: response.StatusCode >= 500,
      });
    }
    return response.Data.records.map((r) => ({
      id: r.id,
      title: r.title,
      theme: r.theme,
      subject: r.subject,
      topic: r.topic,
      frequency: r.tableType,
    }));
  });
  return data;
};

export const getTableData = async (tableId: string, options?: TableOptions): Promise<TableData> => {
  const params: Record<string, unknown> = { tableId };
  if (options?.timeFilter !== undefined) params["timeFilter"] = options.timeFilter;
  if (options?.variables !== undefined) params["variables"] = options.variables;
  if (options?.limit !== undefined) params["limit"] = options.limit;
  if (options?.offset !== undefined) params["offset"] = options.offset;

  const cacheKey = buildCacheKey("singstat", "table", params);
  const { data } = await withCache(cacheKey, "DAILY", async () => {
    let url = `${getBaseUrl()}/tabledata/${tableId}`;
    const qp: string[] = [];
    if (options?.timeFilter !== undefined) qp.push(`timeFilter=${encodeURIComponent(options.timeFilter)}`);
    if (options?.limit !== undefined) qp.push(`limit=${options.limit}`);
    if (options?.offset !== undefined) qp.push(`offset=${options.offset}`);
    if (qp.length > 0) url += `?${qp.join("&")}`;

    const response = await httpGet<SingStatTableResponse>(url, { apiName: "singstat" });
    if (response.StatusCode !== 200) {
      throw new (await import("@sg-apis/shared")).ApiError({
        apiName: "singstat",
        statusCode: response.StatusCode,
        message: response.Message || "SingStat table fetch failed",
        retryable: response.StatusCode >= 500,
      });
    }

    const requestedVariables = new Set(
      (options?.variables ?? []).map((variable) => variable.trim().toLowerCase()),
    );
    const rows: NormalizedRow[] = response.Data.row.flatMap((row) =>
      row.columns.map((col) => ({
        period: col.key,
        variable: row.rowText,
        value: isNaN(parseFloat(col.value)) ? col.value : parseFloat(col.value),
        unit: row.uoM,
        ...(row.footnote !== "" ? { footnote: row.footnote } : {}),
      })),
    ).filter((row) =>
      requestedVariables.size === 0
        ? true
        : requestedVariables.has(row.variable.trim().toLowerCase()),
    );

    const metadata: TableMetadata = {
      title: response.Data.title,
      frequency: response.Data.frequency,
      source: response.Data.datasource,
      lastUpdated: response.Data.dataLastUpdated,
    };

    return { rows, metadata, total: rows.length };
  });
  return data;
};

export const getTimeSeries = async (
  tableId: string,
  indicator: string,
  startYear: number,
  endYear: number,
): Promise<TimeSeriesRow[]> => {
  const tableData = await getTableData(tableId, {
    timeFilter: `${startYear},${endYear}`,
  });

  return tableData.rows
    .filter((row) => row.variable.toLowerCase().includes(indicator.toLowerCase()))
    .filter((row) => typeof row.value === "number")
    .map((row) => ({
      period: row.period,
      value: row.value as number,
      unit: row.unit,
    }));
};
