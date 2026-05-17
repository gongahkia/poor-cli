import { BriefArtifactSchema, formatResponse } from "@dude/shared";
import type { BriefArtifact, BriefFreshnessItem, BriefLimit, BriefProvenanceItem, EvidenceGap, RiskFlag, ToolResult } from "@dude/shared";
import { getGovFeedItems } from "../apis/govfeeds/client.js";

type FetchLike = (
  url: string,
  init?: {
    readonly method?: string;
    readonly headers?: Record<string, string>;
    readonly body?: string;
  },
) => Promise<{
  readonly ok: boolean;
  readonly status: number;
  json: () => Promise<unknown>;
  text?: () => Promise<string>;
}>;

type FeedReader = typeof getGovFeedItems;

const nowIso = (): string => new Date().toISOString();
const toGap = (code: string, message: string): EvidenceGap => ({ code, message });
const toLimit = (code: string, message: string): BriefLimit => ({ code, message });
const toFreshness = (source: string, observedAt: string, upstreamTimestamp: string | null = null): BriefFreshnessItem => ({
  source,
  observedAt,
  upstreamTimestamp,
});
const toProvenance = (
  source: string,
  tool: string,
  coverage: string,
  authRequired: boolean,
  recordCount: number,
  sourceUrl: string,
): BriefProvenanceItem => ({
  source,
  tool,
  coverage,
  authRequired,
  recordCount,
  sourceUrl,
  evidenceType: "web_discovery",
});

const normalizeName = (value: unknown): string =>
  typeof value !== "string"
    ? ""
    : value.toLowerCase().replace(/\b(pte|ltd|private|limited|llp|llc|inc|co)\b/g, " ").replace(/[^a-z0-9]+/g, " ").trim();

const entityRoot = (value: unknown): string =>
  normalizeName(value).split(" ").filter((part) => part.length > 2).slice(0, 3).join(" ");

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;

const asArray = (value: unknown): readonly unknown[] => Array.isArray(value) ? value : [];

export const toBriefToolResult = (payload: BriefArtifact, format: "json" | "markdown" = "json"): ToolResult => {
  const validated = BriefArtifactSchema.parse(payload) as BriefArtifact;
  return {
    content: [{
      type: "text",
      text: formatResponse(validated as unknown as Record<string, unknown>, format),
    }],
    structuredContent: { record: validated },
  };
};

export type SanctionsScreenParams = {
  readonly name: string;
  readonly uen?: string | undefined;
  readonly threshold?: number | undefined;
  readonly limit?: number | undefined;
  readonly dataset?: string | undefined;
  readonly format?: "json" | "markdown" | undefined;
};

const getCandidateScore = (candidate: Record<string, unknown>): number => {
  const raw = candidate["score"] ?? candidate["match"] ?? candidate["scoreValue"];
  return typeof raw === "number" && Number.isFinite(raw) ? raw : 0;
};

const getCandidateName = (candidate: Record<string, unknown>): string | null => {
  const caption = candidate["caption"];
  if (typeof caption === "string" && caption.trim() !== "") return caption.trim();
  const properties = asRecord(candidate["properties"]);
  const names = asArray(properties?.["name"]).filter((item): item is string => typeof item === "string");
  return names[0] ?? null;
};

const extractSanctionsCandidates = (payload: unknown): readonly Record<string, unknown>[] => {
  const record = asRecord(payload);
  const responseResults = asArray(asRecord(asRecord(record?.["responses"])?.["q0"])?.["results"]);
  const rootResults = asArray(record?.["results"]);
  return [...responseResults, ...rootResults].flatMap((item) => {
    const candidate = asRecord(item);
    return candidate === null ? [] : [candidate];
  });
};

export const buildSanctionsScreenArtifact = async (
  params: SanctionsScreenParams,
  options: {
    readonly fetcher?: FetchLike;
    readonly apiKey?: string | undefined;
    readonly baseUrl?: string | undefined;
    readonly observedAt?: string | undefined;
  } = {},
): Promise<BriefArtifact> => {
  const observedAt = options.observedAt ?? nowIso();
  const apiKey = options.apiKey ?? process.env["OPENSANCTIONS_API_KEY"];
  const threshold = params.threshold ?? 0.75;
  const limit = Math.min(Math.max(params.limit ?? 10, 1), 25);
  const dataset = params.dataset ?? "default";
  const gaps: EvidenceGap[] = [];
  let candidates: readonly Record<string, unknown>[] = [];

  if (apiKey === undefined || apiKey.trim() === "") {
    gaps.push(toGap("OPENSANCTIONS_API_KEY_REQUIRED", "OpenSanctions screening requires OPENSANCTIONS_API_KEY and an appropriate data license for commercial use."));
  } else {
    try {
      const fetcher = options.fetcher ?? globalThis.fetch as unknown as FetchLike;
      const response = await fetcher(`${options.baseUrl ?? "https://api.opensanctions.org"}/match/${encodeURIComponent(dataset)}`, {
        method: "POST",
        headers: {
          Authorization: `ApiKey ${apiKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          queries: {
            q0: {
              schema: "Company",
              properties: {
                name: [params.name],
                ...(params.uen === undefined ? {} : { registrationNumber: [params.uen] }),
              },
            },
          },
        }),
      });
      if (!response.ok) {
        throw new Error(`OpenSanctions API returned HTTP ${response.status}.`);
      }
      candidates = extractSanctionsCandidates(await response.json())
        .filter((candidate) => getCandidateScore(candidate) >= threshold)
        .slice(0, limit);
    } catch (error) {
      gaps.push(toGap("OPENSANCTIONS_UPSTREAM_FAILED", error instanceof Error ? error.message : String(error)));
    }
  }

  const exactMatches = candidates.filter((candidate) => normalizeName(getCandidateName(candidate)) === normalizeName(params.name));
  const fuzzyMatches = candidates.filter((candidate) => !exactMatches.includes(candidate));
  const riskFlags: RiskFlag[] = candidates.length === 0 ? [] : [{
    code: exactMatches.length > 0 ? "SANCTIONS_EXACT_CANDIDATE" : "SANCTIONS_FUZZY_CANDIDATE",
    severity: exactMatches.length > 0 ? "high" : "medium",
    message: `${candidates.length} OpenSanctions candidate ${candidates.length === 1 ? "match" : "matches"} met the configured threshold. Analyst review is required before treating this as a true hit.`,
    source: "OpenSanctions",
  }];

  return {
    title: "Sanctions Screen",
    summary: [
      { label: "Query name", value: params.name, source: "Input" },
      { label: "UEN", value: params.uen ?? null, source: "Input" },
      { label: "Candidate matches", value: candidates.length, source: "OpenSanctions" },
      { label: "Match type", value: exactMatches.length > 0 ? "exact" : fuzzyMatches.length > 0 ? "fuzzy" : "no-match", source: "OpenSanctions" },
    ],
    evidence: [
      { label: "Threshold", value: threshold, source: "OpenSanctions" },
      { label: "Exact candidates", value: exactMatches.length, source: "OpenSanctions" },
      { label: "Fuzzy candidates", value: fuzzyMatches.length, source: "OpenSanctions" },
    ],
    records: {
      query: { name: params.name, uen: params.uen ?? null, dataset, threshold },
      candidates,
    },
    gaps,
    provenance: [
      toProvenance("OpenSanctions", "sg_sanctions_screen", "Sanctions and watchlist candidate screening by bounded company-name query.", true, candidates.length, "https://www.opensanctions.org/docs/api/"),
    ],
    freshness: [toFreshness("OpenSanctions", observedAt)],
    limits: [
      toLimit("CANDIDATE_SCREEN_ONLY", "Matches are candidates for analyst review, not a final sanctions determination."),
      toLimit("LICENSE_REQUIRED", "OpenSanctions is free for non-commercial users; businesses must use a licensed API key or licensed bulk data."),
    ],
    riskFlags,
  };
};

export type OpenCorporatesParams = {
  readonly entityName: string;
  readonly uen?: string | undefined;
  readonly jurisdictionCode?: string | undefined;
  readonly limit?: number | undefined;
  readonly format?: "json" | "markdown" | undefined;
};

const extractOpenCorporatesCompanies = (payload: unknown): readonly Record<string, unknown>[] => {
  const companies = asArray(asRecord(asRecord(payload)?.["results"])?.["companies"]);
  return companies.flatMap((item) => {
    const company = asRecord(asRecord(item)?.["company"]);
    return company === null ? [] : [company];
  });
};

export const buildOpenCorporatesLinksArtifact = async (
  params: OpenCorporatesParams,
  options: {
    readonly fetcher?: FetchLike;
    readonly apiToken?: string | undefined;
    readonly baseUrl?: string | undefined;
    readonly observedAt?: string | undefined;
  } = {},
): Promise<BriefArtifact> => {
  const observedAt = options.observedAt ?? nowIso();
  const token = options.apiToken ?? process.env["OPENCORPORATES_API_TOKEN"];
  const jurisdictionCode = params.jurisdictionCode ?? "sg";
  const limit = Math.min(Math.max(params.limit ?? 10, 1), 25);
  const gaps: EvidenceGap[] = [];
  let companies: readonly Record<string, unknown>[] = [];

  if (token === undefined || token.trim() === "") {
    gaps.push(toGap("OPENCORPORATES_API_TOKEN_REQUIRED", "OpenCorporates cross-links require OPENCORPORATES_API_TOKEN and license review for the intended use."));
  } else {
    try {
      const fetcher = options.fetcher ?? globalThis.fetch as unknown as FetchLike;
      const url = new URL(`${options.baseUrl ?? "https://api.opencorporates.com"}/v0.4/companies/search`);
      url.searchParams.set("q", params.uen ?? params.entityName);
      url.searchParams.set("jurisdiction_code", jurisdictionCode);
      url.searchParams.set("per_page", String(limit));
      const response = await fetcher(url.toString(), {
        headers: { "X-API-TOKEN": token },
      });
      if (!response.ok) {
        throw new Error(`OpenCorporates API returned HTTP ${response.status}.`);
      }
      companies = extractOpenCorporatesCompanies(await response.json()).slice(0, limit);
      if (companies.length === 0) {
        gaps.push(toGap("OPENCORPORATES_NO_MATCH", "No OpenCorporates company link matched the supplied identifier."));
      }
    } catch (error) {
      gaps.push(toGap("OPENCORPORATES_UPSTREAM_FAILED", error instanceof Error ? error.message : String(error)));
    }
  }

  const exact = companies.filter((company) =>
    normalizeName(company["name"]) === normalizeName(params.entityName)
    || (params.uen !== undefined && String(company["company_number"] ?? "").toUpperCase() === params.uen.toUpperCase()),
  );

  return {
    title: "OpenCorporates Cross-Links",
    summary: [
      { label: "Query", value: params.uen ?? params.entityName, source: "Input" },
      { label: "Jurisdiction", value: jurisdictionCode, source: "Input" },
      { label: "Candidate links", value: companies.length, source: "OpenCorporates" },
      { label: "Exact candidate links", value: exact.length, source: "OpenCorporates" },
    ],
    evidence: [
      { label: "Ambiguous candidates", value: Math.max(companies.length - exact.length, 0), source: "OpenCorporates" },
    ],
    records: {
      query: { entityName: params.entityName, uen: params.uen ?? null, jurisdictionCode },
      companies,
    },
    gaps,
    provenance: [
      toProvenance("OpenCorporates", "sg_opencorporates_links", "Company cross-links from OpenCorporates API search.", true, companies.length, "https://knowledge.opencorporates.com/knowledge-base/api-documentation/"),
    ],
    freshness: [toFreshness("OpenCorporates", observedAt)],
    limits: [
      toLimit("NO_OWNERSHIP_CLAIMS", "OpenCorporates links are identifier cross-references only; this tool does not infer ownership, control, or beneficial owners."),
      toLimit("TOKEN_AND_LICENSE_REQUIRED", "The OpenCorporates REST API requires an API token and appropriate plan for usage volume."),
    ],
  };
};

export type AdverseMediaLiteParams = {
  readonly keyword: string;
  readonly feedIds?: readonly string[] | undefined;
  readonly limitPerFeed?: number | undefined;
  readonly format?: "json" | "markdown" | undefined;
};

const DEFAULT_ADVERSE_FEEDS = [
  "sfa_food_alerts",
  "sfa_media_releases",
  "nea_news_updates",
  "mpa_media_releases",
  "ura_media_releases",
] as const;

export const buildAdverseMediaLiteArtifact = async (
  params: AdverseMediaLiteParams,
  options: {
    readonly feedReader?: FeedReader;
    readonly observedAt?: string | undefined;
  } = {},
): Promise<BriefArtifact> => {
  const observedAt = options.observedAt ?? nowIso();
  const feedReader = options.feedReader ?? getGovFeedItems;
  const feedIds = params.feedIds ?? DEFAULT_ADVERSE_FEEDS;
  const gaps: EvidenceGap[] = [];
  const records: Record<string, unknown>[] = [];
  const freshness: BriefFreshnessItem[] = [];
  const provenance: BriefProvenanceItem[] = [];

  await Promise.all(feedIds.map(async (feedId) => {
    try {
      const result = await feedReader({
        feedId,
        keyword: params.keyword,
        limit: params.limitPerFeed ?? 10,
      });
      records.push(...result.records.map((item) => ({
        feedId,
        agency: result.feed.sourceAgency,
        title: item.title,
        description: item.description,
        link: item.link,
        publishedAt: item.publishedAt,
        confidence: "official_feed_keyword_match",
      })));
      freshness.push(toFreshness(result.feed.title, result.observedAt, result.records[0]?.publishedAt ?? null));
      provenance.push(toProvenance(result.feed.sourceAgency, "sg_adverse_media_lite", `Keyword search over ${result.feed.title}.`, false, result.records.length, result.feed.sourceUrl));
    } catch (error) {
      gaps.push(toGap("GOV_FEED_UNAVAILABLE", `${feedId}: ${error instanceof Error ? error.message : String(error)}`));
    }
  }));

  return {
    title: "Adverse Media Lite",
    summary: [
      { label: "Keyword", value: params.keyword, source: "Input" },
      { label: "Feeds searched", value: feedIds.length, source: "Official feeds" },
      { label: "Feed items matched", value: records.length, source: "Official feeds" },
    ],
    evidence: [
      { label: "Confidence model", value: "official_feed_keyword_match", source: "Dude" },
    ],
    records: {
      query: { keyword: params.keyword, feedIds },
      items: records,
    },
    gaps,
    provenance,
    freshness: freshness.length === 0 ? [toFreshness("Official feeds", observedAt)] : freshness,
    limits: [
      toLimit("NO_GENERAL_WEB_SEARCH", "This is not open web adverse-media monitoring; it searches only configured official Singapore public feeds."),
      toLimit("NO_UNSUPPORTED_NLP", "Confidence means keyword occurrence in an official feed item. The tool does not infer sentiment, culpability, or adverse-event categories."),
    ],
  };
};

export type RelationshipGraphParams = {
  readonly records: Record<string, unknown>;
  readonly format?: "json" | "markdown" | undefined;
};

type GraphNode = {
  readonly id: string;
  readonly label: string;
  readonly kind: "company" | "address";
  readonly source: string;
};

type GraphEdge = {
  readonly from: string;
  readonly to: string;
  readonly kind: "registered_address" | "shared_registered_address" | "name_family";
  readonly evidence: string;
  readonly confidence: "evidence" | "heuristic";
};

const firstString = (record: Record<string, unknown>, keys: readonly string[]): string | null => {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim() !== "") return value.trim();
  }
  return null;
};

const normalizeAddress = (record: Record<string, unknown>): string | null => {
  const postalCode = firstString(record, ["postalCode", "postal_code"]);
  const street = firstString(record, ["streetName", "street", "registeredAddress"]);
  if (postalCode === null && street === null) return null;
  return [street, postalCode].filter(Boolean).join(" ").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
};

const collectAcraGraphRecords = (records: Record<string, unknown>): readonly Record<string, unknown>[] =>
  asArray(records["acra"]).flatMap((item) => {
    const record = asRecord(item);
    return record === null ? [] : [record];
  });

export const buildRelationshipGraphArtifact = (
  params: RelationshipGraphParams,
  observedAt = nowIso(),
): BriefArtifact => {
  const acra = collectAcraGraphRecords(params.records);
  const nodes = new Map<string, GraphNode>();
  const edges: GraphEdge[] = [];
  const byAddress = new Map<string, string[]>();
  const byRoot = new Map<string, string[]>();

  for (const record of acra) {
    const name = firstString(record, ["entityName", "companyName", "name"]) ?? "Unnamed entity";
    const uen = firstString(record, ["uen", "uenNo", "company_number"]);
    const companyId = `company:${uen ?? normalizeName(name)}`;
    nodes.set(companyId, {
      id: companyId,
      label: name,
      kind: "company",
      source: "ACRA",
    });
    const address = normalizeAddress(record);
    if (address !== null) {
      const addressId = `address:${address}`;
      nodes.set(addressId, {
        id: addressId,
        label: address,
        kind: "address",
        source: "ACRA",
      });
      edges.push({
        from: companyId,
        to: addressId,
        kind: "registered_address",
        evidence: "ACRA registered address fields.",
        confidence: "evidence",
      });
      byAddress.set(addressId, [...(byAddress.get(addressId) ?? []), companyId]);
    }
    const root = entityRoot(name);
    if (root !== "") {
      byRoot.set(root, [...(byRoot.get(root) ?? []), companyId]);
    }
  }

  for (const [addressId, companyIds] of byAddress.entries()) {
    if (companyIds.length < 2) continue;
    for (const companyId of companyIds) {
      edges.push({
        from: companyId,
        to: addressId,
        kind: "shared_registered_address",
        evidence: "Multiple ACRA records share the same normalized registered address.",
        confidence: "heuristic",
      });
    }
  }

  for (const [root, companyIds] of byRoot.entries()) {
    const unique = Array.from(new Set(companyIds));
    if (unique.length < 2) continue;
    for (let index = 1; index < unique.length; index += 1) {
      edges.push({
        from: unique[0]!,
        to: unique[index]!,
        kind: "name_family",
        evidence: `Normalized entity-name root "${root}" appears across multiple ACRA records.`,
        confidence: "heuristic",
      });
    }
  }

  const graph = {
    nodes: Array.from(nodes.values()),
    edges,
  };

  return {
    title: "Relationship Graph",
    summary: [
      { label: "Nodes", value: graph.nodes.length, source: "Graph builder" },
      { label: "Edges", value: graph.edges.length, source: "Graph builder" },
      { label: "Heuristic edges", value: graph.edges.filter((edge) => edge.confidence === "heuristic").length, source: "Graph builder" },
    ],
    evidence: [
      { label: "ACRA records inspected", value: acra.length, source: "ACRA" },
    ],
    records: { graph },
    gaps: acra.length === 0 ? [toGap("NO_GRAPH_RECORDS", "No ACRA records were supplied for relationship graph construction.")] : [],
    provenance: [
      toProvenance("ACRA", "sg_relationship_graph", "Graph edges derived from supplied public ACRA record fields.", false, acra.length, "https://www.acra.gov.sg/resources/open-data-initiative/"),
    ],
    freshness: [toFreshness("Relationship graph", observedAt)],
    limits: [
      toLimit("NO_UBO_OR_CONTROL_INFERENCE", "The graph does not infer directors, shareholders, beneficial owners, subsidiaries, parent entities, or control."),
      toLimit("HEURISTIC_EDGES_REQUIRE_REVIEW", "Shared-address and name-family edges are triage heuristics, not proof of relationship."),
    ],
  };
};
