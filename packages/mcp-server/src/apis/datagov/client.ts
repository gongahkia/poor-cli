import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import Database from "better-sqlite3";
import { httpGet, ApiError, createLogger, getMockApiBaseUrl } from "@sg-apis/shared";
import type {
  DatagovDatastoreResult,
  DatagovDatastoreResponse,
  DatagovDataset,
  DatagovV2ListResponse,
} from "@sg-apis/shared";
import { withCache, buildCacheKey } from "../../middleware/cache-middleware.js";

const logger = createLogger("datagov-client");

const getBaseUrl = (): string => {
  const mockApiBaseUrl = getMockApiBaseUrl();
  return mockApiBaseUrl !== undefined
    ? `${mockApiBaseUrl}/datagov`
    : "https://api-production.data.gov.sg/v2/public/api";
};

const getDatastoreBaseUrl = (): string => {
  const mockApiBaseUrl = getMockApiBaseUrl();
  return mockApiBaseUrl !== undefined
    ? `${mockApiBaseUrl}/datagov/action`
    : "https://data.gov.sg/api/action";
};

type DatastoreQueryOptions = {
  readonly limit?: number;
  readonly offset?: number;
  readonly sort?: string;
  readonly filters?: Readonly<Record<string, unknown>>;
};

const INDEX_TTL = 604800; // WHY: dataset list changes slowly, weekly refresh is sufficient
const DATASETS_PAGE_SIZE = 100;

let indexDb: Database.Database | null = null;

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
  const db = getIndexDb();

  const allDatasets = await fetchAllDatasets();

  // Rebuild index
  const insertStmt = db.prepare(
    "INSERT OR REPLACE INTO datagov_index (id, title, description, org, format, updated) VALUES (?, ?, ?, ?, ?, ?)",
  );
  const transaction = db.transaction(() => {
    db.exec("DELETE FROM datagov_index");
    db.exec("DELETE FROM datagov_fts");
    for (const ds of allDatasets) {
      insertStmt.run(
        ds.datasetId,
        ds.name,
        ds.description ?? "",
        ds.managedByAgencyName,
        ds.format,
        ds.lastUpdatedAt,
      );
    }
    // Rebuild FTS index
    db.exec("INSERT INTO datagov_fts(datagov_fts) VALUES('rebuild')");
    db.prepare("INSERT OR REPLACE INTO datagov_index_meta (key, value) VALUES ('last_built', ?)").run(
      String(Math.floor(Date.now() / 1000)),
    );
  });
  transaction();

  logger.info("data.gov.sg local index built", { datasets: allDatasets.length });
};

const fetchDatasetsPage = async (page: number): Promise<DatagovV2ListResponse> => {
  const url = `${getBaseUrl()}/datasets?page=${page}&resultSize=${DATASETS_PAGE_SIZE}`;
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

  // Check if index has any data
  const countRow = db.prepare("SELECT COUNT(*) as count FROM datagov_index").get() as { count: number };
  if (countRow.count === 0) return [];

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
  // Try local FTS5 index first
  try {
    if (!isIndexFresh()) {
      await buildLocalIndex();
    }
    const localResults = localSearch(keyword, limit);
    if (localResults.length > 0) {
      return localResults;
    }
    const substringResults = localSubstringSearch(keyword, limit);
    if (substringResults.length > 0) {
      return substringResults;
    }
    return [];
  } catch (error) {
    logger.warn("local search failed, falling back to API", {
      error: error instanceof Error ? error.message : String(error),
    });
  }

  // Fallback to API search
  const cacheKey = buildCacheKey("datagov", "search", { keyword, limit });
  const { data } = await withCache(cacheKey, "DAILY", async () => {
    const datasets = await fetchAllDatasets();
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

    // Fetch from API
    try {
      const url = `${getBaseUrl()}/datasets/${datasetId}/metadata`;
      const response = await httpGet<{
        code: number;
        data: {
          name?: string;
          description?: string;
          format?: string;
          managedByAgencyName?: string;
          lastUpdatedAt?: string;
          createdAt?: string;
        };
      }>(url, { apiName: "datagov" });

      if (response.code !== 0) return null;

      return {
        datasetId,
        name: response.data.name ?? datasetId,
        description: response.data.description,
        status: "active",
        format: response.data.format ?? "CSV",
        createdAt: response.data.createdAt ?? "",
        lastUpdatedAt: response.data.lastUpdatedAt ?? "",
        managedByAgencyName: response.data.managedByAgencyName ?? "",
      } as DatagovDataset;
    } catch {
      return null;
    }
  });
  return data;
};

export const listCollections = async (): Promise<{ id: string; name: string; description: string }[]> => {
  try {
    if (!isIndexFresh()) {
      await buildLocalIndex();
    }
    const indexedCollections = loadIndexedCollections();
    if (indexedCollections.length > 0) {
      return indexedCollections;
    }
  } catch (error) {
    logger.warn("collection index lookup failed, falling back to API", {
      error: error instanceof Error ? error.message : String(error),
    });
  }

  const cacheKey = buildCacheKey("datagov", "collections", {});
  const { data } = await withCache(cacheKey, "DAILY", async () => {
    const datasets = await fetchAllDatasets();

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

export const queryDatastoreResult = async <TRecord extends Readonly<Record<string, unknown>>>(
  resourceId: string,
  options: DatastoreQueryOptions = {},
): Promise<DatagovDatastoreResult<TRecord>> => {
  const cacheKey = buildCacheKey("datagov", "datastore", {
    resourceId,
    ...options,
  });
  const { data } = await withCache(cacheKey, "DAILY", async () => {
    const url = new URL(`${getDatastoreBaseUrl()}/datastore_search`);
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
