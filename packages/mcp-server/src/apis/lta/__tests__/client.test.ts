import { beforeEach, describe, expect, it, vi } from "vitest";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

vi.mock("@swee-sg/shared", async () => {
  const actual = await vi.importActual<typeof import("@swee-sg/shared")>("@swee-sg/shared");
  return {
    ...actual,
    Keystore: class {
      getKey(): string | null {
        return null;
      }
    },
    getRateLimiter: () => ({ acquire: vi.fn().mockResolvedValue(undefined) }),
  };
});

vi.mock("../../../middleware/cache-middleware.js", () => ({
  withCache: vi.fn(async (_key: string, _ttl: string, fetcher: () => Promise<unknown>) => ({
    data: await fetcher(),
    cached: false,
  })),
  buildCacheKey: vi.fn((...args: unknown[]) => args.join(":")),
}));

import { getBusArrivals, getTrafficIncidents, getTrainAlerts } from "../client.js";

describe("LTA client", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    delete process.env["SG_API_LTA_KEY"];
  });

  it("returns normalized bus arrivals", async () => {
    process.env["SG_API_LTA_KEY"] = "test-key";
    const fixture = await import("./fixtures/bus-arrivals-response.json");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => fixture.default,
      status: 200,
      statusText: "OK",
      headers: new Headers(),
      text: async () => JSON.stringify(fixture.default),
    });

    const results = await getBusArrivals("83139", "851");
    expect(results).toHaveLength(1);
    expect(results[0]?.serviceNo).toBe("851");
    expect(results[0]?.arrivals[0]?.lat).toBeTypeOf("number");
  });

  it("returns normalized train alerts", async () => {
    process.env["SG_API_LTA_KEY"] = "test-key";
    const fixture = await import("./fixtures/train-alerts-response.json");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => fixture.default,
      status: 200,
      statusText: "OK",
      headers: new Headers(),
      text: async () => JSON.stringify(fixture.default),
    });

    const result = await getTrainAlerts();
    expect(result.alerts[0]?.line).toContain("North South");
    expect(result.messages[0]?.content).toContain("delay");
  });

  it("returns normalized traffic incidents", async () => {
    process.env["SG_API_LTA_KEY"] = "test-key";
    const fixture = await import("./fixtures/traffic-incidents-response.json");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => fixture.default,
      status: 200,
      statusText: "OK",
      headers: new Headers(),
      text: async () => JSON.stringify(fixture.default),
    });

    const result = await getTrafficIncidents();
    expect(result[0]?.type).toBe("Accident");
  });

  it("fails clearly when the API key is not configured", async () => {
    await expect(getBusArrivals("83139")).rejects.toThrow("LTA API key not configured");
  });
});
