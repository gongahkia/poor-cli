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

const getTinyFishApiKey = (): string | undefined => {
  const value = process.env["TINYFISH_API_KEY"]?.trim();
  return value === "" ? undefined : value;
};

export const isTinyFishSearchConfigured = (): boolean => getTinyFishApiKey() !== undefined;

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

    return response.results.map((result) => ({
      title: result.title,
      snippet: result.snippet,
      url: result.url,
      siteName: result.site_name ?? null,
      position: result.position,
    }));
  } catch (error) {
    logger.warn("tinyfish search failed", {
      query: normalizedQuery,
      error: error instanceof Error ? error.message : String(error),
    });
    return [];
  }
};
