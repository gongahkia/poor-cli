import { httpGet } from "@sg-apis/shared";
import { buildCacheKey, withCache } from "../../middleware/cache-middleware.js";

// Singapore Statutes Online public search endpoint.
// [Unverified] the public search JSON shape may change; this client consumes what sso.agc.gov.sg
// returns today and extracts stable fields only.
const SSO_SEARCH_URL = "https://sso.agc.gov.sg/Search/SearchApi";

type SsoSearchResponseRow = Readonly<{
  Title?: string;
  Url?: string;
  Snippet?: string;
  Description?: string;
  DocumentType?: string;
}>;

type SsoSearchResponse = Readonly<{
  Results?: readonly SsoSearchResponseRow[];
}>;

export type LawSearchHit = {
  readonly title: string | null;
  readonly url: string | null;
  readonly snippet: string | null;
  readonly documentType: string | null;
};

export const searchSingaporeLaw = async (
  params: Readonly<{ query: string; limit?: number | undefined }>,
): Promise<readonly LawSearchHit[]> => {
  const cacheKey = buildCacheKey("law", "search", { q: params.query, limit: params.limit ?? 10 });
  const { data } = await withCache(cacheKey, "STATIC", async () => {
    const url = new URL(SSO_SEARCH_URL);
    url.searchParams.set("q", params.query);
    url.searchParams.set("types", "act");
    const response = await httpGet<SsoSearchResponse>(url.toString(), {
      apiName: "law",
      headers: { Accept: "application/json" },
    });
    const rows = response.Results ?? [];
    return rows.slice(0, Math.min(params.limit ?? 10, 50)).map((row) => ({
      title: row.Title ?? null,
      url: row.Url === undefined || row.Url === "" ? null : (row.Url.startsWith("http") ? row.Url : `https://sso.agc.gov.sg${row.Url}`),
      snippet: row.Snippet ?? row.Description ?? null,
      documentType: row.DocumentType ?? null,
    }));
  });
  return data;
};
