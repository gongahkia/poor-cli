import { ApiError, getTimeout, httpGetText } from "@sg-apis/shared";
import { buildCacheKey, withCache } from "../../middleware/cache-middleware.js";

export type GovFeedFamily = "nea" | "weather" | "sfa" | "mpa" | "nhb" | "ura";
type GovFeedSourceFormat = "rss" | "ura_listing";

export type GovFeedDefinition = Readonly<{
  id: string;
  title: string;
  family: GovFeedFamily;
  sourceAgency: string;
  sourceUrl: string;
  format?: GovFeedSourceFormat;
}>;

export type GovFeedItem = Readonly<{
  title: string | null;
  description: string | null;
  link: string | null;
  guid: string | null;
  publishedAtRaw: string | null;
  publishedAt: string | null;
}>;

const GOV_FEED_DEFINITIONS: readonly GovFeedDefinition[] = [
  {
    id: "nea_news_updates",
    title: "NEA News Updates",
    family: "nea",
    sourceAgency: "National Environment Agency",
    sourceUrl: "https://www.nea.gov.sg/rss/news_update",
  },
  {
    id: "nea_tender_notices",
    title: "NEA Tender Notices",
    family: "nea",
    sourceAgency: "National Environment Agency",
    sourceUrl: "https://www.nea.gov.sg/rss/tender_notices_update",
  },
  {
    id: "nea_upcoming_events",
    title: "NEA Upcoming Events",
    family: "nea",
    sourceAgency: "National Environment Agency",
    sourceUrl: "https://www.nea.gov.sg/rss/upcoming_events_update",
  },
  {
    id: "weather_2hr_forecast",
    title: "Weather 2-Hour Forecast Feed",
    family: "weather",
    sourceAgency: "Meteorological Service Singapore",
    sourceUrl: "https://www.weather.gov.sg/files/rss/rss2HrForecast.xml",
  },
  {
    id: "weather_24hr_forecast",
    title: "Weather 24-Hour Forecast Feed",
    family: "weather",
    sourceAgency: "Meteorological Service Singapore",
    sourceUrl: "https://www.weather.gov.sg/files/rss/rss24HrForecast.xml",
  },
  {
    id: "weather_4day_forecast",
    title: "Weather 4-Day Forecast Feed",
    family: "weather",
    sourceAgency: "Meteorological Service Singapore",
    sourceUrl: "https://www.weather.gov.sg/files/rss/rss4day.xml",
  },
  {
    id: "weather_heavy_rain",
    title: "Weather Heavy Rain Alerts Feed",
    family: "weather",
    sourceAgency: "Meteorological Service Singapore",
    sourceUrl: "https://www.weather.gov.sg/files/rss/rssHeavyRain_new.xml",
  },
  {
    id: "weather_cap_alert",
    title: "Weather CAP Alerts Feed",
    family: "weather",
    sourceAgency: "Meteorological Service Singapore",
    sourceUrl: "https://www.weather.gov.sg/files/rss/rsscapalert/rsscapalert.xml",
  },
  {
    id: "weather_portal_updates",
    title: "Weather Portal Updates Feed",
    family: "weather",
    sourceAgency: "Meteorological Service Singapore",
    sourceUrl: "https://www.weather.gov.sg/feed/",
  },
  {
    id: "sfa_newsroom",
    title: "SFA Newsroom",
    family: "sfa",
    sourceAgency: "Singapore Food Agency",
    sourceUrl: "https://www.sfa.gov.sg/rss/newsroom",
  },
  {
    id: "sfa_media_releases",
    title: "SFA Media Releases",
    family: "sfa",
    sourceAgency: "Singapore Food Agency",
    sourceUrl: "https://www.sfa.gov.sg/rss/media-releases",
  },
  {
    id: "sfa_food_alerts",
    title: "SFA Food Alerts",
    family: "sfa",
    sourceAgency: "Singapore Food Agency",
    sourceUrl: "https://www.sfa.gov.sg/rss/annual-listing-food-alerts",
  },
  {
    id: "sfa_circulars",
    title: "SFA Circulars",
    family: "sfa",
    sourceAgency: "Singapore Food Agency",
    sourceUrl: "https://www.sfa.gov.sg/rss/annual-listing-circulars",
  },
  {
    id: "mpa_media_releases",
    title: "MPA Media Releases",
    family: "mpa",
    sourceAgency: "Maritime and Port Authority of Singapore",
    sourceUrl: "https://www.mpa.gov.sg/feeds/media-releases",
  },
  {
    id: "mpa_press_releases",
    title: "MPA Press Releases",
    family: "mpa",
    sourceAgency: "Maritime and Port Authority of Singapore",
    sourceUrl: "https://www.mpa.gov.sg/feeds/press-releases",
  },
  {
    id: "nhb_general",
    title: "NHB General Updates",
    family: "nhb",
    sourceAgency: "National Heritage Board",
    sourceUrl: "https://www.nhb.gov.sg/Custom/Nhb2017/Widget/RSS/NhbRSSHandler.ashx?topic=General",
  },
  {
    id: "nhb_exhibitions",
    title: "NHB Exhibitions",
    family: "nhb",
    sourceAgency: "National Heritage Board",
    sourceUrl: "https://www.nhb.gov.sg/Custom/Nhb2017/Widget/RSS/NhbRSSHandler.ashx?topic=Exhibitions",
  },
  {
    id: "nhb_programmes",
    title: "NHB Programmes",
    family: "nhb",
    sourceAgency: "National Heritage Board",
    sourceUrl: "https://www.nhb.gov.sg/Custom/Nhb2017/Widget/RSS/NhbRSSHandler.ashx?topic=Programs",
  },
  {
    id: "nhb_publications",
    title: "NHB Publications",
    family: "nhb",
    sourceAgency: "National Heritage Board",
    sourceUrl: "https://www.nhb.gov.sg/Custom/Nhb2017/Widget/RSS/NhbRSSHandler.ashx?topic=Publications",
  },
  {
    id: "nhb_trails",
    title: "NHB Trails",
    family: "nhb",
    sourceAgency: "National Heritage Board",
    sourceUrl: "https://www.nhb.gov.sg/Custom/Nhb2017/Widget/RSS/NhbRSSHandler.ashx?topic=Trails",
  },
  {
    id: "ura_media_releases",
    title: "URA Media Releases",
    family: "ura",
    sourceAgency: "Urban Redevelopment Authority",
    sourceUrl: "https://www.ura.gov.sg/Corporate/Media-Room/Media-Releases",
    format: "ura_listing",
  },
  {
    id: "ura_speeches",
    title: "URA Speeches",
    family: "ura",
    sourceAgency: "Urban Redevelopment Authority",
    sourceUrl: "https://www.ura.gov.sg/Corporate/Media-Room/Speeches",
    format: "ura_listing",
  },
  {
    id: "ura_announcements",
    title: "URA Announcements",
    family: "ura",
    sourceAgency: "Urban Redevelopment Authority",
    sourceUrl: "https://www.ura.gov.sg/Corporate/Media-Room/Announcements",
    format: "ura_listing",
  },
  {
    id: "ura_news",
    title: "URA News",
    family: "ura",
    sourceAgency: "Urban Redevelopment Authority",
    sourceUrl: "https://www.ura.gov.sg/Corporate/Media-Room/News",
    format: "ura_listing",
  },
  {
    id: "ura_publications",
    title: "URA Publications",
    family: "ura",
    sourceAgency: "Urban Redevelopment Authority",
    sourceUrl: "https://www.ura.gov.sg/Corporate/Media-Room/Publications",
    format: "ura_listing",
  },
] as const;

const GOV_FEED_BY_ID = new Map(GOV_FEED_DEFINITIONS.map((feed) => [feed.id, feed]));

const decodeXmlEntities = (value: string): string => {
  return value.replace(/&(#x?[0-9a-fA-F]+|[a-zA-Z]+);/g, (match, entity: string) => {
    if (entity.startsWith("#x")) {
      const code = Number.parseInt(entity.slice(2), 16);
      return Number.isFinite(code) ? String.fromCodePoint(code) : match;
    }
    if (entity.startsWith("#")) {
      const code = Number.parseInt(entity.slice(1), 10);
      return Number.isFinite(code) ? String.fromCodePoint(code) : match;
    }
    switch (entity) {
      case "amp":
        return "&";
      case "lt":
        return "<";
      case "gt":
        return ">";
      case "quot":
        return "\"";
      case "apos":
        return "'";
      case "nbsp":
        return " ";
      default:
        return match;
    }
  });
};

const normalizeText = (value: string): string => {
  return decodeXmlEntities(
    value
      .replace(/^<!\[CDATA\[([\s\S]*?)\]\]>$/i, "$1")
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .trim(),
  );
};

const extractTagValue = (xml: string, tagName: string): string | null => {
  const pattern = new RegExp(`<${tagName}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${tagName}>`, "i");
  const match = pattern.exec(xml);
  if (match === null) {
    return null;
  }
  const raw = match[1];
  if (raw === undefined) {
    return null;
  }
  const normalized = normalizeText(raw);
  return normalized.length === 0 ? null : normalized;
};

const toIsoTimestamp = (value: string | null): string | null => {
  if (value === null) {
    return null;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : new Date(parsed).toISOString();
};

const parseFeedItems = (xml: string): readonly GovFeedItem[] => {
  const itemMatches = [...xml.matchAll(/<item(?:\s[^>]*)?>[\s\S]*?<\/item>/gi)];
  return itemMatches.map((match) => {
    const block = match[0];
    const publishedAtRaw = extractTagValue(block, "pubDate") ?? extractTagValue(block, "dc:date");
    return {
      title: extractTagValue(block, "title"),
      description: extractTagValue(block, "description"),
      link: extractTagValue(block, "link"),
      guid: extractTagValue(block, "guid"),
      publishedAtRaw,
      publishedAt: toIsoTimestamp(publishedAtRaw),
    };
  });
};

const parseUraListingItems = (html: string, sourceUrl: string): readonly GovFeedItem[] => {
  const itemMatches = [...html.matchAll(
    /<li id="column_2_main_0_rpCircularWithoutColumn_listItems_[^"]*"[\s\S]*?<\/li>/gi,
  )];
  return itemMatches
    .map((match) => {
      const block = match[0];
      const dateMatch = /class="date"[^>]*>([\s\S]*?)<\/div>/i.exec(block)
        ?? /col-md-3[\s\S]*?<div class="text">([\s\S]*?)<\/div>/i.exec(block);
      const publishedAtRaw = dateMatch === null ? null : normalizeText(dateMatch[1] ?? "");
      const linkMatch = /<a\s+href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/i.exec(block);
      const relativeLink = linkMatch?.[1] ?? null;
      const title = linkMatch === null ? null : normalizeText(linkMatch[2] ?? "");
      const link = relativeLink === null || relativeLink.trim() === ""
        ? null
        : new URL(relativeLink, sourceUrl).toString();
      return {
        title: title === "" ? null : title,
        description: null,
        link,
        guid: link,
        publishedAtRaw: publishedAtRaw === "" ? null : publishedAtRaw,
        publishedAt: toIsoTimestamp(publishedAtRaw),
      } satisfies GovFeedItem;
    })
    .filter((record) => record.title !== null || record.link !== null);
};

const fetchAndParseFeed = async (definition: GovFeedDefinition): Promise<{
  observedAt: string;
  channelTitle: string | null;
  records: readonly GovFeedItem[];
}> => {
  const payload = await httpGetText(definition.sourceUrl, {
    apiName: "govfeeds",
    timeout: getTimeout("govfeeds"),
  });

  if (definition.format === "ura_listing") {
    if (!/rpCircularWithoutColumn_listItems_/i.test(payload)) {
      throw new ApiError({
        apiName: "govfeeds",
        source: definition.sourceAgency,
        statusCode: 502,
        code: "UNEXPECTED_FEED_PAGE_FORMAT",
        retryable: false,
        message: `${definition.id} did not return the expected URA listing page shape.`,
        suggestedAction: "Retry later. If this persists, verify whether the URA page structure changed.",
      });
    }
    return {
      observedAt: new Date().toISOString(),
      channelTitle: extractTagValue(payload, "title"),
      records: parseUraListingItems(payload, definition.sourceUrl),
    };
  }

  if (!/<rss\b/i.test(payload) && !/<feed\b/i.test(payload)) {
    throw new ApiError({
      apiName: "govfeeds",
      source: definition.sourceAgency,
      statusCode: 502,
      code: "UNEXPECTED_FEED_FORMAT",
      retryable: false,
      message: `${definition.id} did not return an RSS/Atom feed payload.`,
      suggestedAction: "Retry later. If this persists, verify whether the upstream feed format changed.",
    });
  }

  const channelMatch = /<channel(?:\s[^>]*)?>([\s\S]*?)<\/channel>/i.exec(payload);
  const channelTitle = channelMatch === null
    ? extractTagValue(payload, "title")
    : extractTagValue(channelMatch[1] ?? "", "title");

  return {
    observedAt: new Date().toISOString(),
    channelTitle,
    records: parseFeedItems(payload),
  };
};

export const getGovFeedCatalog = (
  family?: GovFeedFamily | "all",
): readonly GovFeedDefinition[] => {
  if (family === undefined || family === "all") {
    return GOV_FEED_DEFINITIONS;
  }
  return GOV_FEED_DEFINITIONS.filter((definition) => definition.family === family);
};

export const getGovFeedItems = async (params: {
  feedId: string;
  limit?: number | undefined;
  keyword?: string | undefined;
}): Promise<{
  readonly feed: GovFeedDefinition;
  readonly observedAt: string;
  readonly channelTitle: string | null;
  readonly records: readonly GovFeedItem[];
  readonly cached: boolean;
}> => {
  const definition = GOV_FEED_BY_ID.get(params.feedId);
  if (definition === undefined) {
    throw new ApiError({
      apiName: "govfeeds",
      source: "govfeeds",
      statusCode: 400,
      code: "UNKNOWN_FEED_ID",
      retryable: false,
      message: `Unknown feedId: ${params.feedId}`,
      suggestedAction: "Call sg_gov_feed_catalog to discover supported feedId values.",
    });
  }

  const cacheKey = buildCacheKey("govfeeds", "fetchFeed", { feedId: definition.id });
  const cachedResult = await withCache(
    cacheKey,
    "DAILY",
    async () => fetchAndParseFeed(definition),
  );

  const keyword = params.keyword?.trim().toLowerCase();
  const filtered = keyword === undefined || keyword === ""
    ? cachedResult.data.records
    : cachedResult.data.records.filter((record) => {
      const title = (record.title ?? "").toLowerCase();
      const description = (record.description ?? "").toLowerCase();
      return title.includes(keyword) || description.includes(keyword);
    });

  const limit = Math.min(Math.max(params.limit ?? 20, 1), 100);
  return {
    feed: definition,
    observedAt: cachedResult.data.observedAt,
    channelTitle: cachedResult.data.channelTitle,
    records: filtered.slice(0, limit),
    cached: cachedResult.cached,
  };
};
