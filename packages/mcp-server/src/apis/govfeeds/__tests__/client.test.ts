import { beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

vi.mock("@swee-sg/shared", async () => {
  const actual = await vi.importActual<typeof import("@swee-sg/shared")>("@swee-sg/shared");
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

describe("government feeds client", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("returns catalog entries and family filtering", () => {
    const all = getGovFeedCatalog();
    const weather = getGovFeedCatalog("weather");
    const mpa = getGovFeedCatalog("mpa");
    const nhb = getGovFeedCatalog("nhb");
    const ura = getGovFeedCatalog("ura");

    expect(all.length).toBe(25);
    expect(weather.map((entry) => entry.id)).toEqual([
      "weather_2hr_forecast",
      "weather_24hr_forecast",
      "weather_4day_forecast",
      "weather_heavy_rain",
      "weather_cap_alert",
      "weather_portal_updates",
    ]);
    expect(mpa.map((entry) => entry.id)).toEqual([
      "mpa_media_releases",
      "mpa_press_releases",
    ]);
    expect(nhb.map((entry) => entry.id)).toEqual([
      "nhb_general",
      "nhb_exhibitions",
      "nhb_programmes",
      "nhb_publications",
      "nhb_trails",
    ]);
    expect(ura.map((entry) => entry.id)).toEqual([
      "ura_media_releases",
      "ura_speeches",
      "ura_announcements",
      "ura_news",
      "ura_publications",
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

  it("fetches and normalizes URA listing items", async () => {
    const fixturePath = new URL("./fixtures/sample-ura-listing.html", import.meta.url);
    const fixture = readFileSync(fixturePath, "utf8");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      statusText: "OK",
      headers: new Headers({ "content-type": "text/html" }),
      text: async () => fixture,
    });

    const result = await getGovFeedItems({
      feedId: "ura_media_releases",
      limit: 5,
    });

    expect(result.feed.id).toBe("ura_media_releases");
    expect(result.records).toHaveLength(2);
    expect(result.records[0]).toMatchObject({
      title: "Release of flash estimate for 1st Quarter 2026 private residential property price index",
      link: "https://www.ura.gov.sg/Corporate/Media-Room/Media-Releases/pr26-26",
      publishedAtRaw: "1 April 2026",
    });
  });

  it("parses Atom feed entries when RSS item blocks are absent", async () => {
    const fixturePath = new URL("./fixtures/sample-atom.xml", import.meta.url);
    const fixture = readFileSync(fixturePath, "utf8");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      statusText: "OK",
      headers: new Headers({ "content-type": "application/atom+xml" }),
      text: async () => fixture,
    });

    const result = await getGovFeedItems({
      feedId: "sfa_newsroom",
      limit: 5,
    });

    expect(result.feed.id).toBe("sfa_newsroom");
    expect(result.channelTitle).toBe("Sample Atom Feed");
    expect(result.records).toHaveLength(2);
    expect(result.records[0]).toMatchObject({
      title: "Atom Entry One",
      description: "First atom item.",
      link: "https://example.gov.sg/atom/1",
      guid: "tag:example.gov.sg,2026:atom-1",
      publishedAtRaw: "2026-04-22T08:00:00Z",
      publishedAt: "2026-04-22T08:00:00.000Z",
    });
    expect(result.records[1]).toMatchObject({
      title: "Atom Entry Two",
      description: "Second atom item.",
      link: "https://example.gov.sg/atom/2",
      guid: "tag:example.gov.sg,2026:atom-2",
      publishedAtRaw: "2026-04-21T10:30:00Z",
      publishedAt: "2026-04-21T10:30:00.000Z",
    });
  });

  it("throws a bounded error for unknown feed ids", async () => {
    await expect(getGovFeedItems({ feedId: "unknown_feed" })).rejects.toMatchObject({
      code: "UNKNOWN_FEED_ID",
      statusCode: 400,
    });
  });
});
