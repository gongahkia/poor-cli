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

import { searchDatasets, getTableData } from "../client.js";

describe("SingStat client", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("constructs correct URL for search", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        Data: { records: [], total: 0, generatedBy: "", dateGenerated: "" },
        StatusCode: 200,
        Message: "",
      }),
    });

    await searchDatasets("GDP", 10);

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("keyword=GDP"),
      expect.any(Object),
    );
  });

  it("parses search response correctly", async () => {
    const fixture = await import("./fixtures/search-response.json");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => fixture.default,
    });

    const results = await searchDatasets("GDP");
    expect(results).toHaveLength(3);
    expect(results[0]).toMatchObject({
      id: expect.any(String),
      title: expect.any(String),
    });
  });

  it("parses table data response", async () => {
    const fixture = await import("./fixtures/data-response.json");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => fixture.default,
    });

    const result = await getTableData("M015631");
    expect(result.rows.length).toBeGreaterThan(0);
    expect(result.metadata.title).toBe("GDP Growth Rate, Quarterly");
  });

  it("handles empty results", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        Data: { records: [], total: 0, generatedBy: "", dateGenerated: "" },
        StatusCode: 200,
        Message: "",
      }),
    });

    const results = await searchDatasets("xyznonexistent");
    expect(results).toEqual([]);
  });

  it("throws on error response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        Data: { records: [], total: 0, generatedBy: "", dateGenerated: "" },
        StatusCode: 500,
        Message: "Internal Server Error",
      }),
    });

    await expect(searchDatasets("test")).rejects.toThrow();
  });
});
