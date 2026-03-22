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

import { geocode, reverseGeocode } from "../client.js";

describe("OneMap client", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("geocode returns parsed results", async () => {
    const fixture = await import("./fixtures/search-response.json");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => fixture.default,
    });

    const results = await geocode("Raffles Place");
    expect(results).toHaveLength(2);
    expect(results[0]).toHaveProperty("lat");
    expect(results[0]).toHaveProperty("lng");
    expect(results[0]).toHaveProperty("address");
  });

  it("geocode parses coordinates as numbers", async () => {
    const fixture = await import("./fixtures/search-response.json");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => fixture.default,
    });

    const results = await geocode("Raffles Place");
    expect(typeof results[0]?.lat).toBe("number");
    expect(typeof results[0]?.lng).toBe("number");
  });

  it("geocode respects limit parameter", async () => {
    const fixture = await import("./fixtures/search-response.json");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => fixture.default,
    });

    const results = await geocode("Raffles Place", 1);
    expect(results).toHaveLength(1);
  });

  it("geocode handles NIL postal code", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        found: 1, totalNumPages: 1, pageNum: 1,
        results: [{ SEARCHVAL: "TEST", BLK_NO: "", ROAD_NAME: "NIL", BUILDING: "TEST", ADDRESS: "TEST", POSTAL: "NIL", X: "30000", Y: "29000", LATITUDE: "1.28", LONGITUDE: "103.85" }],
      }),
    });

    const results = await geocode("test");
    expect(results[0]?.postal).toBeNull();
  });

  it("geocode handles empty results", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ found: 0, totalNumPages: 0, pageNum: 1, results: [] }),
    });

    const results = await geocode("xyznonexistent");
    expect(results).toEqual([]);
  });

  it("reverseGeocode returns null for no results", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ GeocodeInfo: [{ BUILDINGNAME: "", BLOCK: "", ROAD: "", POSTALCODE: "", XCOORD: "", YCOORD: "", LATITUDE: "", LONGITUDE: "", LONGTITUDE: "" }] }),
    });

    const result = await reverseGeocode(1.28, 103.85);
    expect(result).toBeNull();
  });
});
