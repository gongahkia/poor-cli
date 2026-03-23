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

import { query, getResourceId } from "../client.js";

describe("MAS client", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("constructs correct URL with resource ID", async () => {
    const fixture = await import("./fixtures/search-response.json");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => fixture.default,
    });

    await query("95932927-c8bc-4e7a-b484-68a66a24edfe", { limit: 10 });
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("resource_id=95932927"),
      expect.any(Object),
    );
  });

  it("parses exchange rate records", async () => {
    const fixture = await import("./fixtures/search-response.json");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => fixture.default,
    });

    const records = await query("95932927-c8bc-4e7a-b484-68a66a24edfe");
    expect(records).toHaveLength(2);
    expect(records[0]).toHaveProperty("usd_sgd");
  });

  it("resolves known dataset to resource ID", () => {
    const id = getResourceId("EXCHANGE_RATES");
    expect(id).toBe("95932927-c8bc-4e7a-b484-68a66a24edfe");
  });

  it("throws on unknown dataset", () => {
    expect(() => getResourceId("UNKNOWN_DATASET")).toThrow("Unknown MAS dataset");
  });

  it("handles failed API response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: false, result: { resource_id: "", total: 0, records: [], limit: 0, offset: 0, fields: [] } }),
    });

    await expect(query("bad-id")).rejects.toThrow("MAS query failed");
  });

  it("includes filters in URL when provided", async () => {
    const fixture = await import("./fixtures/search-response.json");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => fixture.default,
    });

    await query("95932927-c8bc-4e7a-b484-68a66a24edfe", { filters: { end_of_day: "2025-01-02" } });
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("filters="),
      expect.any(Object),
    );
  });

  it("preserves filters and sort when auto-paginating", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          result: {
            resource_id: "95932927-c8bc-4e7a-b484-68a66a24edfe",
            total: 2,
            records: [{ _id: 1, end_of_day: "2025-01-02", usd_sgd: "1.35" }],
            limit: 1,
            offset: 0,
            fields: [],
          },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          result: {
            resource_id: "95932927-c8bc-4e7a-b484-68a66a24edfe",
            total: 2,
            records: [{ _id: 2, end_of_day: "2025-01-03", usd_sgd: "1.36" }],
            limit: 1,
            offset: 1,
            fields: [],
          },
        }),
      });

    await query("95932927-c8bc-4e7a-b484-68a66a24edfe", {
      limit: 1,
      sort: "end_of_day desc",
      filters: { end_of_day: "2025-01-02" },
    });

    expect(mockFetch).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining("filters="),
      expect.any(Object),
    );
    expect(mockFetch).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining("sort=end_of_day%20desc"),
      expect.any(Object),
    );
  });
});
