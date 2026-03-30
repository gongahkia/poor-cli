import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import Database from "better-sqlite3";
import { httpGet, httpGetText, ApiError, createLogger } from "@sg-apis/shared";
import type {
  DatagovColumnMetadata,
  DatagovDatastoreResult,
  DatagovDatastoreResponse,
  DatagovDataset,
  DatagovDatasetMetadata,
  DatagovMetadataResponse,
  DatagovV2ListResponse,
} from "@sg-apis/shared";
import type { TTLKey } from "@sg-apis/shared";
import { withCache, buildCacheKey } from "../../middleware/cache-middleware.js";

const logger = createLogger("datagov-client");

const BASE_URL = "https://api-production.data.gov.sg/v2/public/api";
const DATASTORE_BASE_URL = "https://data.gov.sg/api/action";
const DOWNLOAD_BASE_URL = "https://api-open.data.gov.sg/v1/public/api";

type DatastoreQueryOptions = {
  readonly limit?: number;
  readonly offset?: number;
  readonly sort?: string;
  readonly filters?: Readonly<Record<string, unknown>>;
};

type DatagovDatasetDownloadResponse = {
  readonly code: number;
  readonly data: {
    readonly url?: string;
    readonly status?: string;
  } | null;
  readonly errorMsg: string;
  readonly name?: string;
};

const INDEX_TTL = 604800; // WHY: dataset list changes slowly, weekly refresh is sufficient
const DATASETS_PAGE_SIZE = 100;
const TABULAR_FORMATS = new Set(["CSV", "JSON", "GEOJSON", "XLSX", "XLS", "TXT"]);

let indexDb: Database.Database | null = null;
let indexWarmPromise: Promise<void> | null = null;

export const resetLocalIndexState = (): void => {
  if (indexDb !== null) {
    indexDb.close();
    indexDb = null;
  }
  indexWarmPromise = null;
};

const getIndexDb = (): Database.Database => {
  if (indexDb !== null) return indexDb;
  const dbDir = join(homedir(), ".sg-apis");
  mkdirSync(dbDir, { recursive: true });
  const db = new Database(join(dbDir, "cache.db"));
  db.exec(`
    CREATE TABLE IF NOT EXISTS datagov_index (
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      description TEXT,
      org TEXT,
      format TEXT,
      updated TEXT
    )
  `);
  // FTS5 virtual table for full-text search
  db.exec(`
    CREATE VIRTUAL TABLE IF NOT EXISTS datagov_fts USING fts5(
      title, description, content=datagov_index, content_rowid=rowid
    )
  `);
  db.exec(`
    CREATE TABLE IF NOT EXISTS datagov_index_meta (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    )
  `);
  indexDb = db;
  return db;
};

const isIndexFresh = (): boolean => {
  try {
    const db = getIndexDb();
    const row = db
      .prepare("SELECT value FROM datagov_index_meta WHERE key = 'last_built'")
      .get() as { value: string } | undefined;
    if (row === undefined) return false;
    const lastBuilt = parseInt(row.value, 10);
    return Date.now() / 1000 - lastBuilt < INDEX_TTL;
  } catch {
    return false;
  }
};

export const buildLocalIndex = async (): Promise<void> => {
  if (isIndexFresh()) return;

  logger.info("building data.gov.sg local index...");
  const allDatasets = await fetchAllDatasets();
  replaceLocalIndex(allDatasets);
  logger.info("data.gov.sg local index built", { datasets: allDatasets.length });
};

const replaceLocalIndex = (datasets: readonly DatagovDataset[]): void => {
  const db = getIndexDb();
  const insertStmt = db.prepare(
    "INSERT OR REPLACE INTO datagov_index (id, title, description, org, format, updated) VALUES (?, ?, ?, ?, ?, ?)",
  );
  const transaction = db.transaction(() => {
    db.exec("DELETE FROM datagov_index");
    db.exec("DELETE FROM datagov_fts");
    for (const ds of datasets) {
      insertStmt.run(
        ds.datasetId,
        ds.name,
        ds.description ?? "",
        ds.managedByAgencyName,
        ds.format,
        ds.lastUpdatedAt,
      );
    }
    db.exec("INSERT INTO datagov_fts(datagov_fts) VALUES('rebuild')");
    db.prepare("INSERT OR REPLACE INTO datagov_index_meta (key, value) VALUES ('last_built', ?)").run(
      String(Math.floor(Date.now() / 1000)),
    );
  });
  transaction();
};

const hasIndexedDatasets = (): boolean => {
  const db = getIndexDb();
  const countRow = db.prepare("SELECT COUNT(*) as count FROM datagov_index").get() as { count: number };
  return countRow.count > 0;
};

export const ensureLocalIndexWarm = (): void => {
  if (isIndexFresh() || indexWarmPromise !== null) {
    return;
  }

  indexWarmPromise = buildLocalIndex()
    .catch((error: unknown) => {
      logger.warn("background data.gov.sg index warm-up failed", {
        error: error instanceof Error ? error.message : String(error),
      });
    })
    .finally(() => {
      indexWarmPromise = null;
    });
};

const scheduleLocalIndexRefresh = (datasets: readonly DatagovDataset[]): void => {
  if (indexWarmPromise !== null) {
    return;
  }

  indexWarmPromise = Promise.resolve()
    .then(() => {
      replaceLocalIndex(datasets);
      logger.info("data.gov.sg local index refreshed from in-band fetch", { datasets: datasets.length });
    })
    .catch((error: unknown) => {
      logger.warn("background data.gov.sg index refresh failed", {
        error: error instanceof Error ? error.message : String(error),
      });
    })
    .finally(() => {
      indexWarmPromise = null;
    });
};

const fetchDatasetsPage = async (page: number): Promise<DatagovV2ListResponse> => {
  const url = `${BASE_URL}/datasets?page=${page}&resultSize=${DATASETS_PAGE_SIZE}`;
  return httpGet<DatagovV2ListResponse>(url, { apiName: "datagov" });
};

const fetchAllDatasets = async (): Promise<DatagovDataset[]> => {
  const datasets: DatagovDataset[] = [];
  let totalPages = 1;

  for (let page = 0; page < totalPages; page++) {
    const response = await fetchDatasetsPage(page);
    if (response.code !== 0) {
      throw new ApiError({
        apiName: "datagov",
        statusCode: 500,
        message: response.errorMsg || "data.gov.sg query failed",
        retryable: true,
      });
    }

    datasets.push(...response.data.datasets);
    totalPages = Math.max(totalPages, response.data.pages);
    if (response.data.datasets.length === 0) {
      break;
    }
  }

  return datasets;
};

const loadIndexedCollections = (): { id: string; name: string; description: string }[] => {
  const db = getIndexDb();
  const rows = db
    .prepare(
      `SELECT org AS name, COUNT(*) AS datasetCount
       FROM datagov_index
       WHERE org != ''
       GROUP BY org
       ORDER BY datasetCount DESC, org ASC`,
    )
    .all() as { name: string; datasetCount: number }[];

  return rows.map(({ name, datasetCount }) => ({
    id: name.toLowerCase().replace(/\s+/g, "-"),
    name,
    description: `${datasetCount} datasets managed by ${name}`,
  }));
};

const localSubstringSearch = (keyword: string, limit = 10): DatagovDataset[] => {
  const db = getIndexDb();
  const normalizedKeyword = keyword.trim().toLowerCase();
  if (normalizedKeyword === "") {
    return [];
  }

  const rows = db
    .prepare(
      `SELECT id, title, description, org, format, updated
       FROM datagov_index
       WHERE lower(title) LIKE ? OR lower(description) LIKE ?
       ORDER BY updated DESC, title ASC
       LIMIT ?`,
    )
    .all(`%${normalizedKeyword}%`, `%${normalizedKeyword}%`, limit) as {
    id: string;
    title: string;
    description: string;
    org: string;
    format: string;
    updated: string;
  }[];

  return rows.map((r) => ({
    datasetId: r.id,
    name: r.title,
    description: r.description,
    managedByAgencyName: r.org,
    format: r.format,
    lastUpdatedAt: r.updated,
    createdAt: "",
    status: "active",
  }));
};

const getIndexedDatasetById = (datasetId: string): DatagovDataset | null => {
  const db = getIndexDb();
  const row = db
    .prepare("SELECT id, title, description, org, format, updated FROM datagov_index WHERE id = ?")
    .get(datasetId) as {
    id: string;
    title: string;
    description: string;
    org: string;
    format: string;
    updated: string;
  } | undefined;

  if (row === undefined) {
    return null;
  }

  return {
    datasetId: row.id,
    name: row.title,
    description: row.description,
    managedByAgencyName: row.org,
    format: row.format,
    lastUpdatedAt: row.updated,
    createdAt: "",
    status: "active",
  };
};

export const localSearch = (keyword: string, limit = 10): DatagovDataset[] => {
  const db = getIndexDb();
  if (!hasIndexedDatasets()) return [];

  const rows = db
    .prepare(
      `SELECT i.id, i.title, i.description, i.org, i.format, i.updated
       FROM datagov_fts f
       JOIN datagov_index i ON f.rowid = i.rowid
       WHERE datagov_fts MATCH ?
       LIMIT ?`,
    )
    .all(keyword, limit) as {
    id: string;
    title: string;
    description: string;
    org: string;
    format: string;
    updated: string;
  }[];

  return rows.map((r) => ({
    datasetId: r.id,
    name: r.title,
    description: r.description,
    managedByAgencyName: r.org,
    format: r.format,
    lastUpdatedAt: r.updated,
    createdAt: "",
    status: "active",
  }));
};

export const searchDatasets = async (keyword: string, limit = 10): Promise<DatagovDataset[]> => {
  const canUseLocalIndex = hasIndexedDatasets();
  const localIndexFresh = canUseLocalIndex && isIndexFresh();
  if (canUseLocalIndex) {
    if (!localIndexFresh) {
      ensureLocalIndexWarm();
    }

    try {
      const localResults = localSearch(keyword, limit);
      if (localResults.length > 0) {
        return localResults;
      }
      const substringResults = localSubstringSearch(keyword, limit);
      if (substringResults.length > 0) {
        return substringResults;
      }
      if (localIndexFresh) {
        return [];
      }
    } catch (error) {
      logger.warn("local search failed, falling back to API", {
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  const cacheKey = buildCacheKey("datagov", "search", { keyword, limit });
  const { data } = await withCache(cacheKey, "DAILY", async () => {
    const datasets = await fetchAllDatasets();
    scheduleLocalIndexRefresh(datasets);
    const lowerKeyword = keyword.toLowerCase();
    return datasets
      .filter(
        (d) =>
          d.name.toLowerCase().includes(lowerKeyword) ||
          (d.description?.toLowerCase().includes(lowerKeyword) ?? false),
      )
      .slice(0, limit);
  });
  return data;
};

const toNormalizedColumns = (
  columnMetadata: DatagovMetadataResponse["data"]["columnMetadata"],
): readonly DatagovColumnMetadata[] => {
  if (columnMetadata?.map === undefined || columnMetadata.metaMapping === undefined) {
    return [];
  }

  const orderedKeys = columnMetadata.order ?? Object.keys(columnMetadata.map);
  return orderedKeys.map((key) => {
    const mappedName = columnMetadata.map?.[key] ?? key;
    const meta = columnMetadata.metaMapping?.[key];
    return {
      key,
      name: meta?.name ?? mappedName,
      title: meta?.columnTitle ?? mappedName,
      dataType: meta?.dataType ?? "unknown",
      index: meta?.index === undefined ? null : Number(meta.index),
      isCategorical: meta?.isCategorical ?? false,
    };
  });
};

const normalizeMetadataResponse = (
  response: DatagovMetadataResponse,
): DatagovDatasetMetadata => {
  const columns = toNormalizedColumns(response.data.columnMetadata);
  const managedByAgencyName = response.data.managedByAgencyName ?? response.data.managedBy ?? "";

  return {
    datasetId: response.data.datasetId,
    name: response.data.name,
    status: response.data.status ?? "active",
    format: response.data.format,
    createdAt: response.data.createdAt,
    lastUpdatedAt: response.data.lastUpdatedAt,
    managedByAgencyName,
    ...(response.data.description === undefined ? {} : { description: response.data.description }),
    ...(response.data.coverageStart === undefined ? {} : { coverageStart: response.data.coverageStart }),
    ...(response.data.coverageEnd === undefined ? {} : { coverageEnd: response.data.coverageEnd }),
    collectionIds: response.data.collectionIds ?? [],
    contactEmails: response.data.contactEmails ?? [],
    datasetSize: response.data.datasetSize ?? null,
    resources: [
      {
        resourceId: response.data.datasetId,
        datasetId: response.data.datasetId,
        name: response.data.name,
        format: response.data.format,
        machineReadable: columns.length > 0 || TABULAR_FORMATS.has(response.data.format.toUpperCase()),
        columns,
      },
    ],
  };
};

export const getDatasetMetadata = async (
  datasetId: string,
): Promise<DatagovDatasetMetadata | null> => {
  const cacheKey = buildCacheKey("datagov", "dataset-metadata", { datasetId });
  const { data } = await withCache(cacheKey, "DAILY", async () => {
    try {
      const url = `${BASE_URL}/datasets/${datasetId}/metadata`;
      const response = await httpGet<DatagovMetadataResponse>(url, { apiName: "datagov" });
      if (response.code !== 0) {
        return null;
      }
      return normalizeMetadataResponse(response);
    } catch {
      return null;
    }
  });

  return data;
};

export const getDataset = async (datasetId: string): Promise<DatagovDataset | null> => {
  const cacheKey = buildCacheKey("datagov", "dataset", { datasetId });
  const { data } = await withCache(cacheKey, "DAILY", async () => {
    // Try local index first
    try {
      const indexed = getIndexedDatasetById(datasetId);
      if (indexed !== null) {
        return indexed;
      }
    } catch {
      // Fall through to API
    }

    const metadata = await getDatasetMetadata(datasetId);
    if (metadata === null) {
      return null;
    }

    return {
      datasetId: metadata.datasetId,
      name: metadata.name,
      description: metadata.description,
      status: metadata.status,
      format: metadata.format,
      createdAt: metadata.createdAt,
      lastUpdatedAt: metadata.lastUpdatedAt,
      managedByAgencyName: metadata.managedByAgencyName,
      coverageStart: metadata.coverageStart,
      coverageEnd: metadata.coverageEnd,
    } as DatagovDataset;
  });
  return data;
};

export const listCollections = async (): Promise<{ id: string; name: string; description: string }[]> => {
  const canUseLocalIndex = hasIndexedDatasets();
  const localIndexFresh = canUseLocalIndex && isIndexFresh();
  if (canUseLocalIndex) {
    if (!localIndexFresh) {
      ensureLocalIndexWarm();
    }

    try {
      const indexedCollections = loadIndexedCollections();
      if (indexedCollections.length > 0) {
        return indexedCollections;
      }
      if (localIndexFresh) {
        return [];
      }
    } catch (error) {
      logger.warn("collection index lookup failed, falling back to API", {
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  const cacheKey = buildCacheKey("datagov", "collections", {});
  const { data } = await withCache(cacheKey, "DAILY", async () => {
    const datasets = await fetchAllDatasets();
    scheduleLocalIndexRefresh(datasets);

    const agencies = new Map<string, { count: number }>();
    for (const ds of datasets) {
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

export const getDatasetResources = async (
  datasetId: string,
): Promise<DatagovDatasetMetadata | null> => {
  return getDatasetMetadata(datasetId);
};

const getDatasetDownloadUrl = async (datasetId: string): Promise<string> => {
  const url = `${DOWNLOAD_BASE_URL}/datasets/${datasetId}/poll-download`;
  const response = await httpGet<DatagovDatasetDownloadResponse>(url, {
    apiName: "datagov",
  });

  if (response.code !== 0 || response.data?.url === undefined) {
    throw new ApiError({
      apiName: "datagov",
      source: "data.gov.sg",
      statusCode: response.code === 0 ? 502 : response.code,
      code: response.name ?? "DATASET_DOWNLOAD_FAILED",
      message: response.errorMsg || `Unable to download dataset ${datasetId}.`,
      retryable: response.code === 24 || response.code >= 500,
      suggestedAction: "Retry later or inspect the dataset page directly on data.gov.sg.",
      details: response,
    });
  }

  return response.data.url;
};

const parseCsvRows = (csv: string): readonly Readonly<Record<string, string>>[] => {
  const rows: string[][] = [];
  let row: string[] = [];
  let value = "";
  let inQuotes = false;

  for (let index = 0; index < csv.length; index += 1) {
    const char = csv[index]!;
    const next = csv[index + 1];

    if (inQuotes) {
      if (char === "\"") {
        if (next === "\"") {
          value += "\"";
          index += 1;
        } else {
          inQuotes = false;
        }
      } else {
        value += char;
      }
      continue;
    }

    if (char === "\"") {
      inQuotes = true;
      continue;
    }

    if (char === ",") {
      row.push(value);
      value = "";
      continue;
    }

    if (char === "\n") {
      row.push(value);
      rows.push(row);
      row = [];
      value = "";
      continue;
    }

    if (char !== "\r") {
      value += char;
    }
  }

  if (value !== "" || row.length > 0) {
    row.push(value);
    rows.push(row);
  }

  const [headerRow, ...dataRows] = rows;
  if (headerRow === undefined) {
    return [];
  }

  const headers = headerRow.map((header) => header.trim());
  return dataRows
    .filter((candidate) => candidate.some((cell) => cell.trim() !== ""))
    .map((cells) =>
      Object.fromEntries(
        headers.map((header, index) => [header, cells[index] ?? ""]),
      ),
    );
};

export const downloadDatasetText = async (
  datasetId: string,
  ttlKey: TTLKey = "DAILY",
): Promise<string> => {
  const cacheKey = buildCacheKey("datagov", "dataset-download", { datasetId, ttlKey });
  const { data } = await withCache(cacheKey, ttlKey, async () => {
    const downloadUrl = await getDatasetDownloadUrl(datasetId);
    return httpGetText(downloadUrl, { apiName: "datagov" });
  });
  return data;
};

export const downloadDatasetGeoJson = async <
  TFeature extends Readonly<Record<string, unknown>> = Readonly<Record<string, unknown>>,
>(
  datasetId: string,
  ttlKey: TTLKey = "DAILY",
): Promise<{
  readonly type: "FeatureCollection";
  readonly features: readonly {
    readonly type: "Feature";
    readonly geometry: {
      readonly type: string;
      readonly coordinates: readonly number[];
    };
    readonly properties: TFeature;
  }[];
}> => {
  const text = await downloadDatasetText(datasetId, ttlKey);
  return JSON.parse(text) as {
    readonly type: "FeatureCollection";
    readonly features: readonly {
      readonly type: "Feature";
      readonly geometry: {
        readonly type: string;
        readonly coordinates: readonly number[];
      };
      readonly properties: TFeature;
    }[];
  };
};

export const downloadDatasetCsvRows = async <
  TRow extends Readonly<Record<string, string>> = Readonly<Record<string, string>>,
>(
  datasetId: string,
  ttlKey: TTLKey = "DAILY",
): Promise<readonly TRow[]> => {
  const text = await downloadDatasetText(datasetId, ttlKey);
  return parseCsvRows(text) as readonly TRow[];
};

export const queryDatastoreResult = async <TRecord extends Readonly<Record<string, unknown>>>(
  resourceId: string,
  options: DatastoreQueryOptions = {},
): Promise<DatagovDatastoreResult<TRecord>> => {
  const cacheKey = buildCacheKey("datagov", "datastore", {
    resourceId,
    ...options,
  });
  const { data } = await withCache(cacheKey, "DAILY", async () => {
    const url = new URL(`${DATASTORE_BASE_URL}/datastore_search`);
    url.searchParams.set("resource_id", resourceId);
    if (options.limit !== undefined) {
      url.searchParams.set("limit", String(options.limit));
    }
    if (options.offset !== undefined) {
      url.searchParams.set("offset", String(options.offset));
    }
    if (options.sort !== undefined) {
      url.searchParams.set("sort", options.sort);
    }
    if (options.filters !== undefined && Object.keys(options.filters).length > 0) {
      url.searchParams.set("filters", JSON.stringify(options.filters));
    }

    const response = await httpGet<DatagovDatastoreResponse<TRecord>>(url.toString(), {
      apiName: "datagov",
    });

    if ("success" in response && response.success === true) {
      return response.result;
    }

    const errorResponse = response as Extract<DatagovDatastoreResponse<TRecord>, { readonly code: number }>;
    throw new ApiError({
      apiName: "datagov",
      source: "data.gov.sg",
      statusCode: errorResponse.code,
      code: errorResponse.name,
      message: errorResponse.errorMsg,
      retryable: errorResponse.code === 429 || errorResponse.code >= 500,
      suggestedAction:
        errorResponse.code === 429
          ? "Wait for the data.gov.sg rate limit window to reset, then retry."
          : "Retry later or narrow the data.gov.sg datastore query filters.",
      details: errorResponse,
    });
  });
  return data;
};

export const queryDatastore = async <TRecord extends Readonly<Record<string, unknown>>>(
  resourceId: string,
  options: DatastoreQueryOptions = {},
): Promise<readonly TRecord[]> => {
  const result = await queryDatastoreResult<TRecord>(resourceId, options);
  return result.records;
};

export const getDatasetRows = async <
  TRecord extends Readonly<Record<string, unknown>> = Readonly<Record<string, unknown>>,
>(
  params: Readonly<{
    datasetId?: string;
    resourceId?: string;
    filters?: Readonly<Record<string, unknown>>;
    limit?: number;
    offset?: number;
    sort?: string;
  }>,
): Promise<{
  readonly datasetId?: string;
  readonly datasetName?: string;
  readonly resourceId: string;
  readonly total: number;
  readonly offset: number;
  readonly limit: number;
  readonly fields: readonly { readonly id: string; readonly type: string }[];
  readonly records: readonly TRecord[];
}> => {
  const datasetMetadata =
    params.datasetId === undefined ? null : await getDatasetMetadata(params.datasetId);
  const resourceId = params.resourceId ?? datasetMetadata?.resources[0]?.resourceId ?? params.datasetId;

  if (resourceId === undefined) {
    throw new ApiError({
      apiName: "datagov",
      source: "data.gov.sg",
      statusCode: 400,
      code: "RESOURCE_ID_REQUIRED",
      message: "A resourceId or datasetId is required for row retrieval.",
      retryable: false,
      suggestedAction: "Call sg_datagov_resources first to inspect the dataset's machine-readable resource metadata.",
    });
  }

  if (datasetMetadata !== null && datasetMetadata.resources[0]?.machineReadable === false) {
    throw new ApiError({
      apiName: "datagov",
      source: "data.gov.sg",
      statusCode: 422,
      code: "RESOURCE_NOT_MACHINE_READABLE",
      message: `${datasetMetadata.name} does not expose a machine-readable tabular resource through the current metadata contract.`,
      retryable: false,
      suggestedAction: "Choose a CSV, JSON, or GeoJSON dataset, or call sg_datagov_resources to inspect the available columns first.",
    });
  }

  const result = await queryDatastoreResult<TRecord>(resourceId, {
    ...(params.filters === undefined ? {} : { filters: params.filters }),
    ...(params.limit === undefined ? {} : { limit: params.limit }),
    ...(params.offset === undefined ? {} : { offset: params.offset }),
    ...(params.sort === undefined ? {} : { sort: params.sort }),
  });

  return {
    ...(params.datasetId === undefined ? {} : { datasetId: params.datasetId }),
    ...(datasetMetadata === null ? {} : { datasetName: datasetMetadata.name }),
    resourceId,
    total: result.total,
    offset: result.offset ?? params.offset ?? 0,
    limit: result.limit ?? params.limit ?? result.records.length,
    fields: result.fields,
    records: result.records,
  };
};

export const queryDatastoreExactMatches = async <TRecord extends Readonly<Record<string, unknown>>>(
  resourceId: string,
  options: DatastoreQueryOptions & {
    readonly exactMatch: (row: TRecord) => boolean;
    readonly matchLimit: number;
    readonly pageSize?: number;
  },
): Promise<readonly TRecord[]> => {
  const matchLimit = Math.max(options.matchLimit, 1);
  const pageSize = Math.max(options.pageSize ?? Math.min(Math.max(matchLimit * 2, 50), 100), 1);
  const matches: TRecord[] = [];
  let offset = options.offset ?? 0;
  let total = Number.POSITIVE_INFINITY;

  while (offset < total && matches.length < matchLimit) {
    const result = await queryDatastoreResult<TRecord>(resourceId, {
      ...options,
      limit: pageSize,
      offset,
    });

    for (const row of result.records) {
      if (options.exactMatch(row)) {
        matches.push(row);
        if (matches.length >= matchLimit) {
          break;
        }
      }
    }

    if (result.records.length === 0) {
      break;
    }

    total = result.total;
    offset += result.records.length;
  }

  return matches;
};
