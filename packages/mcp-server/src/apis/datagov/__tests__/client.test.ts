import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);
const testHomeDir = mkdtempSync(join(tmpdir(), "sg-apis-datagov-test-"));

vi.mock("node:os", async () => {
  const actual = await vi.importActual<typeof import("node:os")>("node:os");
  return {
    ...actual,
    homedir: () => testHomeDir,
  };
});

vi.mock("@swee-sg/shared", async () => {
  const actual = await vi.importActual<typeof import("@swee-sg/shared")>("@swee-sg/shared");
  return {
    ...actual,
    getRateLimiter: () => ({ acquire: vi.fn().mockResolvedValue(undefined) }),
  };
});

vi.mock("../../../middleware/cache-middleware.js", () => ({
  withCache: vi.fn(async (_key: string, _ttl: number, fetcher: () => Promise<unknown>) => ({
    data: await fetcher(),
    cached: false,
  })),
  buildCacheKey: vi.fn((...args: unknown[]) => args.join(":")),
}));

import {
  downloadDatasetCsvRows,
  getDatasetMetadata,
  getDatasetResources,
  getDatasetRows,
  listCollections,
  queryDatastoreExactMatches,
  resetLocalIndexState,
  searchDatasets,
} from "../client.js";

describe("data.gov.sg client", () => {
  let nowSpy: { mockRestore: () => void };
  let nowSeed = Date.UTC(2099, 0, 1);

  beforeEach(() => {
    mockFetch.mockReset();
    resetLocalIndexState();
    rmSync(join(testHomeDir, ".sg-apis"), { recursive: true, force: true });
    nowSeed += 8 * 24 * 60 * 60 * 1000;
    nowSpy = vi.spyOn(Date, "now").mockReturnValue(nowSeed);
  });

  afterEach(() => {
    nowSpy.mockRestore();
  });

  it("searches datasets by keyword", async () => {
    const fixture = await import("./fixtures/search-response.json");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => fixture.default,
    });

    const results = await searchDatasets("hawker");
    expect(results.length).toBeGreaterThan(0);
    expect(results[0]).toHaveProperty("datasetId");
    expect(results[0]).toHaveProperty("name");
  });

  it("filters results by keyword match", async () => {
    const fixture = await import("./fixtures/search-response.json");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => fixture.default,
    });

    const results = await searchDatasets("hawker");
    for (const r of results) {
      const nameOrDesc = (r.name + (r.description ?? "")).toLowerCase();
      expect(nameOrDesc).toContain("hawker");
    }
  });

  it("respects limit parameter", async () => {
    const fixture = await import("./fixtures/search-response.json");
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => fixture.default,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => fixture.default,
      });

    const results = await searchDatasets("a", 1);
    expect(results.length).toBeLessThanOrEqual(1);
  });

  it("returns empty for no matches", async () => {
    const emptyResponse = {
      code: 0,
      data: { datasets: [], pages: 0, rowCount: 0, totalRowCount: 0 },
      errorMsg: "",
    };
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => emptyResponse,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => emptyResponse,
      });

    const results = await searchDatasets("xyznonexistent");
    expect(results).toEqual([]);
  });

  it("lists collections grouped by agency", async () => {
    const fixture = await import("./fixtures/search-response.json");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => fixture.default,
    });

    const collections = await listCollections();
    expect(collections.length).toBeGreaterThan(0);
    expect(collections[0]).toHaveProperty("id");
    expect(collections[0]).toHaveProperty("name");
  });

  it("normalizes dataset metadata and resources from the v2 metadata contract", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        code: 0,
        data: {
          datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
          name: "HDB Resale Flat Prices",
          description: "Resale flat prices based on registration date by town.",
          format: "CSV",
          managedBy: "Housing & Development Board",
          lastUpdatedAt: "2026-03-01T00:00:00+08:00",
          createdAt: "2020-01-01T00:00:00+08:00",
          collectionIds: ["housing"],
          contactEmails: ["data@hdb.gov.sg"],
          datasetSize: 2048,
          columnMetadata: {
            order: ["month", "town", "resale_price"],
            map: {
              month: "month",
              town: "town",
              resale_price: "resale_price",
            },
            metaMapping: {
              month: {
                name: "month",
                columnTitle: "Month",
                dataType: "text",
                index: "1",
                isCategorical: false,
              },
              town: {
                name: "town",
                columnTitle: "Town",
                dataType: "text",
                index: "2",
                isCategorical: true,
              },
              resale_price: {
                name: "resale_price",
                columnTitle: "Resale Price",
                dataType: "numeric",
                index: "3",
                isCategorical: false,
              },
            },
          },
        },
        errorMsg: "",
      }),
    });

    const metadata = await getDatasetMetadata("d_8b84c4ee58e3cfc0ece0d773c8ca6abc");
    expect(metadata).toMatchObject({
      datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
      name: "HDB Resale Flat Prices",
      managedByAgencyName: "Housing & Development Board",
      collectionIds: ["housing"],
    });
    expect(metadata?.resources[0]).toMatchObject({
      resourceId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
      machineReadable: true,
    });
    expect(metadata?.resources[0]?.columns).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: "town", dataType: "text", isCategorical: true }),
      ]),
    );
  });

  it("returns dataset resources as the current machine-readable resource shape", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        code: 0,
        data: {
          datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
          name: "HDB Resale Flat Prices",
          format: "CSV",
          managedByAgencyName: "HDB",
          lastUpdatedAt: "2026-03-01T00:00:00+08:00",
          createdAt: "2020-01-01T00:00:00+08:00",
          columnMetadata: {
            order: ["month"],
            map: { month: "month" },
            metaMapping: {
              month: {
                name: "month",
                columnTitle: "Month",
                dataType: "text",
                index: "1",
                isCategorical: false,
              },
            },
          },
        },
        errorMsg: "",
      }),
    });

    const resources = await getDatasetResources("d_8b84c4ee58e3cfc0ece0d773c8ca6abc");
    expect(resources?.resources).toHaveLength(1);
    expect(resources?.resources[0]?.columns[0]).toMatchObject({
      key: "month",
      title: "Month",
    });
  });

  it("downloads BOA-style CSV rows through the data.gov.sg file-download contract", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          code: 0,
          data: {
            url: "https://download.data.gov.sg/boa-architecture-firms.csv",
            status: "DOWNLOAD_SUCCESS",
          },
          errorMsg: "",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        text: async () => "firm_me,firm_address,firm_phone\nDP ARCHITECTS PTE LTD,6 RAFFLES BOULEVARD,63380111\n",
      });

    const rows = await downloadDatasetCsvRows("d_d5c0a4ffd076a3e40d772275619bbb66", "DAILY");

    expect(rows).toEqual([
      {
        firm_me: "DP ARCHITECTS PTE LTD",
        firm_address: "6 RAFFLES BOULEVARD",
        firm_phone: "63380111",
      },
    ]);
    expect(mockFetch).toHaveBeenNthCalledWith(
      1,
      "https://api-open.data.gov.sg/v1/public/api/datasets/d_d5c0a4ffd076a3e40d772275619bbb66/poll-download",
      expect.any(Object),
    );
    expect(mockFetch).toHaveBeenNthCalledWith(
      2,
      "https://download.data.gov.sg/boa-architecture-firms.csv",
      expect.any(Object),
    );
  });

  it("reads bounded datastore rows with truthful pagination metadata", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          code: 0,
          data: {
            datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
            name: "HDB Resale Flat Prices",
            format: "CSV",
            managedByAgencyName: "HDB",
            lastUpdatedAt: "2026-03-01T00:00:00+08:00",
            createdAt: "2020-01-01T00:00:00+08:00",
            columnMetadata: {
              order: ["month", "town"],
              map: { month: "month", town: "town" },
              metaMapping: {
                month: {
                  name: "month",
                  columnTitle: "Month",
                  dataType: "text",
                  index: "1",
                  isCategorical: false,
                },
                town: {
                  name: "town",
                  columnTitle: "Town",
                  dataType: "text",
                  index: "2",
                  isCategorical: true,
                },
              },
            },
          },
          errorMsg: "",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          result: {
            fields: [
              { id: "month", type: "text" },
              { id: "town", type: "text" },
            ],
            total: 42,
            limit: 5,
            offset: 10,
            records: [
              { month: "2026-02", town: "BEDOK" },
              { month: "2026-01", town: "BEDOK" },
            ],
          },
        }),
      });

    const rows = await getDatasetRows({
      datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
      limit: 5,
      offset: 10,
      sort: "month desc",
      filters: { town: "BEDOK" },
    });

    expect(rows).toMatchObject({
      datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
      datasetName: "HDB Resale Flat Prices",
      resourceId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
      total: 42,
      limit: 5,
      offset: 10,
    });
    expect(rows.records).toHaveLength(2);
  });

  it("indexes datasets across multiple pages before searching", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          code: 0,
          data: {
            datasets: [
              {
                datasetId: "d_page_1",
                name: "Alpha Dataset",
                description: "Page one result",
                managedByAgencyName: "Agency A",
                format: "CSV",
                lastUpdatedAt: "2026-03-01T00:00:00+08:00",
                createdAt: "2026-01-01T00:00:00+08:00",
                status: "active",
              },
            ],
            pages: 2,
            rowCount: 1,
            totalRowCount: 2,
          },
          errorMsg: "",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          code: 0,
          data: {
            datasets: [
              {
                datasetId: "d_page_2",
                name: "Beta Maritime Dataset",
                description: "Page two result",
                managedByAgencyName: "Agency B",
                format: "CSV",
                lastUpdatedAt: "2026-03-01T00:00:00+08:00",
                createdAt: "2026-01-01T00:00:00+08:00",
                status: "active",
              },
            ],
            pages: 2,
            rowCount: 1,
            totalRowCount: 2,
          },
          errorMsg: "",
        }),
      });

    const results = await searchDatasets("maritime");

    expect(results).toMatchObject([
      {
        datasetId: "d_page_2",
        name: "Beta Maritime Dataset",
      },
    ]);
  });

  it("groups collections across the full paginated dataset index", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          code: 0,
          data: {
            datasets: [
              {
                datasetId: "d_page_1",
                name: "Alpha Dataset",
                description: "Page one result",
                managedByAgencyName: "Agency A",
                format: "CSV",
                lastUpdatedAt: "2026-03-01T00:00:00+08:00",
                createdAt: "2026-01-01T00:00:00+08:00",
                status: "active",
              },
            ],
            pages: 2,
            rowCount: 1,
            totalRowCount: 2,
          },
          errorMsg: "",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          code: 0,
          data: {
            datasets: [
              {
                datasetId: "d_page_2",
                name: "Beta Dataset",
                description: "Page two result",
                managedByAgencyName: "Agency B",
                format: "CSV",
                lastUpdatedAt: "2026-03-01T00:00:00+08:00",
                createdAt: "2026-01-01T00:00:00+08:00",
                status: "active",
              },
            ],
            pages: 2,
            rowCount: 1,
            totalRowCount: 2,
          },
          errorMsg: "",
        }),
      });

    const collections = await listCollections();

    expect(collections).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ name: "Agency A" }),
        expect.objectContaining({ name: "Agency B" }),
      ]),
    );
  });

  it("does not perform a second full remote scan after a clean indexed miss", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          code: 0,
          data: {
            datasets: [
              {
                datasetId: "d_page_1",
                name: "Alpha Dataset",
                description: "Page one result",
                managedByAgencyName: "Agency A",
                format: "CSV",
                lastUpdatedAt: "2026-03-01T00:00:00+08:00",
                createdAt: "2026-01-01T00:00:00+08:00",
                status: "active",
              },
            ],
            pages: 2,
            rowCount: 1,
            totalRowCount: 2,
          },
          errorMsg: "",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          code: 0,
          data: {
            datasets: [
              {
                datasetId: "d_page_2",
                name: "Beta Dataset",
                description: "Page two result",
                managedByAgencyName: "Agency B",
                format: "CSV",
                lastUpdatedAt: "2026-03-01T00:00:00+08:00",
                createdAt: "2026-01-01T00:00:00+08:00",
                status: "active",
              },
            ],
            pages: 2,
            rowCount: 1,
            totalRowCount: 2,
          },
          errorMsg: "",
        }),
      });

    const results = await searchDatasets("definitelymissingterm");

    expect(results).toEqual([]);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("pages through datastore results until exact matches are exhausted", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          result: {
            fields: [],
            total: 3,
            limit: 2,
            offset: 0,
            records: [
              { company_name: "ABC CONSTRUCTION PTE LTD", grade: "A1" },
              { company_name: "ABC CONSTRUCTION HOLDINGS", grade: "C3" },
            ],
          },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          result: {
            fields: [],
            total: 3,
            limit: 2,
            offset: 2,
            records: [
              { company_name: "ABC CONSTRUCTION PTE LTD", grade: "C3" },
            ],
          },
        }),
      });

    const matches = await queryDatastoreExactMatches<{ company_name: string; grade: string }>(
      "resource-id",
      {
        matchLimit: 1,
        pageSize: 2,
        filters: { company_name: { ilike: "ABC CONSTRUCTION PTE LTD" } },
        exactMatch: (row) => row.company_name === "ABC CONSTRUCTION PTE LTD" && row.grade === "C3",
      },
    );

    expect(matches).toEqual([
      { company_name: "ABC CONSTRUCTION PTE LTD", grade: "C3" },
    ]);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("omits offset on the first exact-match datastore page", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        success: true,
        result: {
          fields: [],
          total: 1,
          limit: 1,
          records: [{ uen: "196800306E" }],
        },
      }),
    });

    const matches = await queryDatastoreExactMatches<{ uen: string }>(
      "resource-id",
      {
        matchLimit: 1,
        pageSize: 1,
        filters: { uen: "196800306E" },
        exactMatch: (row) => row.uen === "196800306E",
      },
    );

    expect(matches).toEqual([{ uen: "196800306E" }]);
    const firstUrl = new URL(String(mockFetch.mock.calls[0]?.[0]));
    expect(firstUrl.searchParams.has("offset")).toBe(false);
  });

  it("normalizes ilike filters into punctuation-safe text search", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        success: true,
        result: {
          fields: [],
          total: 0,
          limit: 1,
          records: [],
        },
      }),
    });

    await queryDatastoreExactMatches<{ company_name: string }>(
      "resource-id",
      {
        matchLimit: 1,
        pageSize: 1,
        filters: { company_name: { ilike: "DBS BANK LTD." } },
        exactMatch: (row) => row.company_name === "DBS BANK LTD.",
      },
    );

    const firstUrl = new URL(String(mockFetch.mock.calls[0]?.[0]));
    expect(firstUrl.searchParams.get("q")).toBe("DBS BANK LTD");
  });

  it("handles API error response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ code: 1, data: { datasets: [], pages: 0, rowCount: 0, totalRowCount: 0 }, errorMsg: "Error" }),
    });

    await expect(searchDatasets("test")).rejects.toThrow();
  });
});
