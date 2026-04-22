import { beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";

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
  withCache: vi.fn(async (_key: string, _ttl: string, fetcher: () => Promise<unknown>) => ({
    data: await fetcher(),
    cached: false,
  })),
  buildCacheKey: vi.fn((...args: unknown[]) => args.join(":")),
}));

import { getGovFeedCatalog, getGovFeedItems } from "../client.js";

describe("government RSS feeds client", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("returns catalog entries and family filtering", () => {
    const all = getGovFeedCatalog();
    const weather = getGovFeedCatalog("weather");

    expect(all.length).toBe(11);
    expect(weather.map((entry) => entry.id)).toEqual([
      "weather_2hr_forecast",
      "weather_24hr_forecast",
      "weather_4day_forecast",
      "weather_heavy_rain",
    ]);
  });

  it("fetches and normalizes feed items with keyword filtering", async () => {
    const fixturePath = new URL("./fixtures/sample-rss.xml", import.meta.url);
    const fixture = readFileSync(fixturePath, "utf8");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      statusText: "OK",
      headers: new Headers({ "content-type": "text/xml" }),
      text: async () => fixture,
    });

    const result = await getGovFeedItems({
      feedId: "sfa_newsroom",
      keyword: "latest",
      limit: 5,
    });

    expect(result.feed.id).toBe("sfa_newsroom");
    expect(result.channelTitle).toBe("Sample Feed");
    expect(result.records).toHaveLength(1);
    expect(result.records[0]).toMatchObject({
      title: "First & Latest Update",
      description: "Testing feed item one.",
      guid: "item-1",
      link: "https://example.gov.sg/first",
      publishedAtRaw: "22 Apr 2026 12:00 PM",
    });
  });

  it("throws a bounded error for unknown feed ids", async () => {
    await expect(getGovFeedItems({ feedId: "unknown_feed" })).rejects.toMatchObject({
      code: "UNKNOWN_FEED_ID",
      statusCode: 400,
    });
  });
});
