import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import Database from "better-sqlite3";
import { httpGet, TTL, ApiError, createLogger } from "@sg-apis/shared";
import type { DatagovV2ListResponse, DatagovDataset } from "@sg-apis/shared";
import { withCache, buildCacheKey } from "../../middleware/cache-middleware.js";

const logger = createLogger("datagov-client");

const BASE_URL = process.env["MOCK_API_BASE_URL"]
  ? `${process.env["MOCK_API_BASE_URL"]}/datagov`
  : "https://api-production.data.gov.sg/v2/public/api";

const INDEX_TTL = 604800; // WHY: dataset list changes slowly, weekly refresh is sufficient

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

  // Fetch datasets across multiple pages
  const allDatasets: DatagovDataset[] = [];
  const PAGE_SIZE = 50; // WHY: reasonable page size to avoid overloading API
  const MAX_PAGES = 10; // WHY: cap at 500 datasets for index build time

  for (let page = 0; page < MAX_PAGES; page++) {
    try {
      const url = `${BASE_URL}/datasets?page=${page}&resultSize=${PAGE_SIZE}`;
      const response = await httpGet<DatagovV2ListResponse>(url, { apiName: "datagov" });
      if (response.code !== 0 || response.data.datasets.length === 0) break;
      allDatasets.push(...response.data.datasets);
      if (page >= response.data.pages - 1) break;
    } catch {
      break;
    }
  }

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
  } catch (error) {
    logger.warn("local search failed, falling back to API", {
      error: error instanceof Error ? error.message : String(error),
    });
  }

  // Fallback to API search
  const cacheKey = buildCacheKey("datagov", "search", { keyword, limit });
  const { data } = await withCache(cacheKey, TTL.DAILY, async () => {
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
    // Try local index first
    try {
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

      if (row !== undefined) {
        return {
          datasetId: row.id,
          name: row.title,
          description: row.description,
          managedByAgencyName: row.org,
          format: row.format,
          lastUpdatedAt: row.updated,
          createdAt: "",
          status: "active",
        } as DatagovDataset;
      }
    } catch {
      // Fall through to API
    }

    // Fetch from API
    try {
      const url = `${BASE_URL}/datasets/${datasetId}/metadata`;
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
  const cacheKey = buildCacheKey("datagov", "collections", {});
  const { data } = await withCache(cacheKey, TTL.DAILY, async () => {
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
