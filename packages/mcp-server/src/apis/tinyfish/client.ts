import { httpGet, createLogger } from "@sg-apis/shared";

const TINYFISH_SEARCH_URL = "https://api.search.tinyfish.ai";
const logger = createLogger("tinyfish-client");

type TinyFishSearchResult = {
  readonly position: number;
  readonly site_name?: string | undefined;
  readonly title: string;
  readonly snippet: string;
  readonly url: string;
};

type TinyFishSearchResponse = {
  readonly query: string;
  readonly results: readonly TinyFishSearchResult[];
  readonly total_results?: number | undefined;
  readonly page?: number | undefined;
};

export type WebSearchResult = {
  readonly title: string;
  readonly snippet: string;
  readonly url: string;
  readonly siteName: string | null;
  readonly position: number;
};

export type WebPresence = {
  readonly query: string;
  readonly configured: boolean;
  readonly results: readonly WebSearchResult[];
  readonly possibleOfficialWebsite: string | null;
  readonly limits: readonly string[];
};

export type TinyFishSearchReadiness = {
  readonly configured: boolean;
  readonly resultCount?: number;
};

const SEARCH_CACHE_TTL_MS = 10 * 60 * 1000;
const DIRECTORY_HOST_PARTS = [
  "acra.gov.sg",
  "bizfile.gov.sg",
  "companies.sg",
  "uenfind.com",
  "addressadda.com",
  "recordowl.com",
  "sgpgrid.com",
  "yellowpages.com.sg",
  "sgbizverify.com",
  "linkedin.com",
  "facebook.com",
  "instagram.com",
  "x.com",
  "twitter.com",
];

const searchCache = new Map<string, { readonly expiresAt: number; readonly results: readonly WebSearchResult[] }>();

const getTinyFishApiKey = (): string | undefined => {
  const value = process.env["TINYFISH_API_KEY"]?.trim();
  return value === "" ? undefined : value;
};

export const isTinyFishSearchConfigured = (): boolean => getTinyFishApiKey() !== undefined;

export const probeTinyFishSearchReadiness = async (): Promise<TinyFishSearchReadiness> => {
  const apiKey = getTinyFishApiKey();
  if (apiKey === undefined) {
    return { configured: false };
  }

  const url = new URL(TINYFISH_SEARCH_URL);
  url.searchParams.set("query", "Singapore company UEN ACRA");
  url.searchParams.set("location", "SG");
  url.searchParams.set("language", "en");

  const response = await httpGet<TinyFishSearchResponse>(url.toString(), {
    apiName: "tinyfish",
    headers: { "X-API-Key": apiKey },
    retries: 0,
    timeout: 5000,
  });

  return {
    configured: true,
    resultCount: response.results.length,
  };
};

export const searchTinyFish = async (
  query: string,
  options: Readonly<{
    location?: string | undefined;
    language?: string | undefined;
    page?: number | undefined;
  }> = {},
): Promise<readonly WebSearchResult[]> => {
  const apiKey = getTinyFishApiKey();
  const normalizedQuery = query.trim();
  if (apiKey === undefined || normalizedQuery === "") {
    return [];
  }
  const cacheKey = JSON.stringify({
    query: normalizedQuery,
    location: options.location ?? "SG",
    language: options.language ?? "en",
    page: options.page ?? 0,
  });
  const cached = searchCache.get(cacheKey);
  if (cached !== undefined && cached.expiresAt > Date.now()) {
    return cached.results;
  }

  const url = new URL(TINYFISH_SEARCH_URL);
  url.searchParams.set("query", normalizedQuery);
  url.searchParams.set("location", options.location ?? "SG");
  url.searchParams.set("language", options.language ?? "en");
  if (options.page !== undefined) {
    url.searchParams.set("page", String(options.page));
  }

  try {
    const response = await httpGet<TinyFishSearchResponse>(url.toString(), {
      apiName: "tinyfish",
      headers: { "X-API-Key": apiKey },
      retries: 1,
    });

    const results = response.results.map((result) => ({
      title: result.title,
      snippet: result.snippet,
      url: result.url,
      siteName: result.site_name ?? null,
      position: result.position,
    }));
    if (results.length > 0) {
      searchCache.set(cacheKey, { expiresAt: Date.now() + SEARCH_CACHE_TTL_MS, results });
    }
    return results;
  } catch (error) {
    logger.warn("tinyfish search failed", {
      query: normalizedQuery,
      error: error instanceof Error ? error.message : String(error),
    });
    return [];
  }
};

const hostnameFor = (url: string): string | null => {
  try {
    return new URL(url).hostname.toLowerCase().replace(/^www\./, "");
  } catch {
    return null;
  }
};

const isDirectoryHost = (host: string): boolean =>
  DIRECTORY_HOST_PARTS.some((part) => host === part || host.endsWith(`.${part}`));

const choosePossibleOfficialWebsite = (results: readonly WebSearchResult[]): string | null => {
  const hostCounts = new Map<string, { count: number; firstUrl: string }>();
  for (const result of results) {
    const host = hostnameFor(result.url);
    if (host === null || isDirectoryHost(host)) {
      continue;
    }
    const existing = hostCounts.get(host);
    hostCounts.set(host, {
      count: (existing?.count ?? 0) + 1,
      firstUrl: existing?.firstUrl ?? result.url,
    });
  }

  const candidates = Array.from(hostCounts.entries()).sort((a, b) => b[1].count - a[1].count);
  const best = candidates[0];
  return best !== undefined && best[1].count >= 2 ? best[1].firstUrl : null;
};

export const getWebPresence = async (query: string): Promise<WebPresence> => {
  const normalizedQuery = query.trim();
  if (!isTinyFishSearchConfigured()) {
    return {
      query: normalizedQuery,
      configured: false,
      results: [],
      possibleOfficialWebsite: null,
      limits: [
        "TinyFish Search is not configured on the server.",
        "Web discovery is not registry evidence and is not used to decide official matches.",
      ],
    };
  }

  const results = (await searchTinyFish(`${normalizedQuery} Singapore company UEN`, {
    location: "SG",
    language: "en",
  })).slice(0, 8);

  return {
    query: normalizedQuery,
    configured: true,
    results,
    possibleOfficialWebsite: choosePossibleOfficialWebsite(results),
    limits: [
      "Web discovery is not registry evidence.",
      "Results come from live web search snippets; verify important claims against official sources.",
      "TinyFish Fetch is not used in this flow.",
    ],
  };
};
