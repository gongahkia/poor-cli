import { beforeEach, describe, expect, it, vi } from "vitest";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

vi.mock("@dude/shared", async () => {
  const actual = await vi.importActual<typeof import("@dude/shared")>("@dude/shared");
  return {
    ...actual,
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

import { getAirQuality, getForecast2Hr, getRainfall } from "../client.js";

describe("NEA client", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("returns normalized 2-hour forecast rows", async () => {
    const fixture = await import("./fixtures/forecast-response.json");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => fixture.default,
      status: 200,
      statusText: "OK",
      headers: new Headers(),
      text: async () => JSON.stringify(fixture.default),
    });

    const result = await getForecast2Hr("Tampines");
    expect(result[0]).toMatchObject({
      area: "Tampines",
      forecast: "Partly Cloudy",
    });
  });

  it("returns normalized air-quality rows", async () => {
    const psiFixture = await import("./fixtures/psi-response.json");
    const pm25Fixture = await import("./fixtures/pm25-response.json");
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => psiFixture.default,
        status: 200,
        statusText: "OK",
        headers: new Headers(),
        text: async () => JSON.stringify(psiFixture.default),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => pm25Fixture.default,
        status: 200,
        statusText: "OK",
        headers: new Headers(),
        text: async () => JSON.stringify(pm25Fixture.default),
      });

    const result = await getAirQuality("East");
    expect(result[0]).toMatchObject({
      region: "east",
      psi24h: 42,
      pm25OneHourly: 12,
    });
  });

  it("returns normalized rainfall rows", async () => {
    const fixture = await import("./fixtures/rainfall-response.json");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => fixture.default,
      status: 200,
      statusText: "OK",
      headers: new Headers(),
      text: async () => JSON.stringify(fixture.default),
    });

    const result = await getRainfall("S107");
    expect(result[0]).toMatchObject({
      stationId: "S107",
      stationName: "Tampines West",
      value: 0.4,
    });
  });
});
