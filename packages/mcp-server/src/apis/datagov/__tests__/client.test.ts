import { describe, it, expect, vi, beforeEach } from "vitest";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

vi.mock("@sg-apis/shared", async () => {
  const actual = await vi.importActual<typeof import("@sg-apis/shared")>("@sg-apis/shared");
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

import { searchDatasets, listCollections } from "../client.js";

describe("data.gov.sg client", () => {
  beforeEach(() => {
    mockFetch.mockReset();
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
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => fixture.default,
    });

    const results = await searchDatasets("a", 1);
    expect(results.length).toBeLessThanOrEqual(1);
  });

  it("returns empty for no matches", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        code: 0,
        data: { datasets: [], pages: 0, rowCount: 0, totalRowCount: 0 },
        errorMsg: "",
      }),
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

  it("handles API error response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ code: 1, data: { datasets: [], pages: 0, rowCount: 0, totalRowCount: 0 }, errorMsg: "Error" }),
    });

    await expect(searchDatasets("test")).rejects.toThrow();
  });
});
