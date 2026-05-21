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

const keywordTerms = (keyword: string): readonly string[] => {
  const normalized = keyword.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const parts = normalized.split(/\s+/).filter((part) => part.length > 1);
  return Array.from(new Set([normalized, ...parts].filter(Boolean)));
};

const matchedKeywordTerms = (
  keyword: string,
  item: { readonly title?: string | null; readonly description?: string | null },
): readonly string[] => {
  const haystack = `${item.title ?? ""} ${item.description ?? ""}`.toLowerCase();
  return keywordTerms(keyword).filter((term) => haystack.includes(term));
};

const officialNoticeType = (
  feed: Awaited<ReturnType<FeedReader>>["feed"],
): string => {
  const idAndTitle = `${feed.id} ${feed.title}`.toLowerCase();
  if (idAndTitle.includes("food") && idAndTitle.includes("alert")) return "official_food_alert_feed";
  if (idAndTitle.includes("media") && idAndTitle.includes("release")) return "official_media_release_feed";
  if (idAndTitle.includes("news")) return "official_news_update_feed";
  return "official_public_feed_item";
};

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
        triage: {
          matchedFeed: result.feed.id,
          matchedKeywords: matchedKeywordTerms(params.keyword, item),
          officialNoticeType: officialNoticeType(result.feed),
          requiresAnalystReview: true,
          sentiment: "not_assessed",
          culpability: "not_assessed",
          adverseEventCategory: "not_assessed",
        },
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
      { label: "Triage model", value: "feed_metadata_and_keyword_match_only", source: "Dude" },
      { label: "Items requiring analyst review", value: records.length, source: "Dude" },
      { label: "Unsupported assessments", value: "sentiment, culpability, adverse_event_category", source: "Dude" },
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
      toLimit("NO_UNSUPPORTED_NLP", "Confidence and triage labels are based only on feed metadata and keyword occurrence. Sentiment, culpability, and adverse-event category remain not_assessed."),
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
  readonly kind: "company" | "address" | "entity" | "person";
  readonly source: string;
};

type GraphEdge = {
  readonly from: string;
  readonly to: string;
  readonly kind:
    | "registered_address"
    | "declared_shareholder"
    | "declared_director"
    | "declared_owner"
    | "declared_controller"
    | "declared_parent"
    | "declared_subsidiary"
    | "declared_related_entity";
  readonly evidence: string;
  readonly confidence: "source_declared";
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

const explicitRelationshipKind = (value: unknown): GraphEdge["kind"] | null => {
  if (typeof value !== "string") return null;
  const normalized = value.toLowerCase().replace(/[^a-z0-9]+/g, "_");
  if (/shareholder|shareholding|share_owner/.test(normalized)) return "declared_shareholder";
  if (/director|officer/.test(normalized)) return "declared_director";
  if (/beneficial_owner|owner|ownership/.test(normalized)) return "declared_owner";
  if (/controller|control/.test(normalized)) return "declared_controller";
  if (/parent|holding_company/.test(normalized)) return "declared_parent";
  if (/subsidiary|child/.test(normalized)) return "declared_subsidiary";
  if (/related|affiliate|associate/.test(normalized)) return "declared_related_entity";
  return null;
};

const nodeIdFromLabel = (label: string, kind: GraphNode["kind"] = "entity"): string =>
  `${kind}:${normalizeName(label) || label.toLowerCase().replace(/[^a-z0-9]+/g, "_")}`;

const explicitNode = (
  relationship: Record<string, unknown>,
  keys: readonly string[],
  fallback: Record<string, unknown> | undefined,
  kind: GraphNode["kind"] = "entity",
): { readonly id: string; readonly label: string } | null => {
  const value = firstString(relationship, keys)
    ?? (fallback === undefined ? null : firstString(fallback, ["uen", "uenNo", "entityName", "companyName", "name"]));
  if (value === null) return null;
  return {
    id: value.includes(":") ? value : nodeIdFromLabel(value, kind),
    label: value,
  };
};

const collectExplicitRelationshipRecords = (
  records: Record<string, unknown>,
): readonly { readonly relationship: Record<string, unknown>; readonly fallback?: Record<string, unknown>; readonly sourceGroup: string }[] => [
  ...asArray(records["relationships"]).flatMap((item) => {
    const relationship = asRecord(item);
    return relationship === null ? [] : [{ relationship, sourceGroup: "relationships" }];
  }),
  ...Object.entries(records).flatMap(([sourceGroup, value]) =>
    asArray(value).flatMap((item) => {
      const record = asRecord(item);
      if (record === null) return [];
      return asArray(record["relationships"]).flatMap((relationshipItem) => {
        const relationship = asRecord(relationshipItem);
        return relationship === null ? [] : [{ fallback: record, relationship, sourceGroup }];
      });
    })),
];

export const buildRelationshipGraphArtifact = (
  params: RelationshipGraphParams,
  observedAt = nowIso(),
): BriefArtifact => {
  const acra = collectAcraGraphRecords(params.records);
  const explicitRelationships = collectExplicitRelationshipRecords(params.records);
  const nodes = new Map<string, GraphNode>();
  const edges: GraphEdge[] = [];

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
        evidence: "ACRA source-declared registered address fields; Dude did not infer ownership, control, or affiliation from this address.",
        confidence: "source_declared",
      });
    }
  }

  for (const item of explicitRelationships) {
    const kind = explicitRelationshipKind(
      item.relationship["kind"] ?? item.relationship["type"] ?? item.relationship["relationshipType"] ?? item.relationship["relationship"] ?? item.relationship["role"],
    );
    if (kind === null) continue;
    const from = explicitNode(
      item.relationship,
      ["fromId", "from", "sourceId", "sourceEntity", "sourceName", "entityName", "companyName"],
      item.fallback,
    );
    const toKind: GraphNode["kind"] = kind === "declared_director" ? "person" : "entity";
    const to = explicitNode(
      item.relationship,
      ["toId", "to", "targetId", "targetEntity", "targetName", "relatedEntityName", "personName", "name"],
      undefined,
      toKind,
    );
    if (from === null || to === null) continue;
    const source = firstString(item.relationship, ["source", "sourceRegistry", "registry"]) ?? item.sourceGroup;
    nodes.set(from.id, {
      id: from.id,
      kind: "entity",
      label: from.label,
      source,
    });
    nodes.set(to.id, {
      id: to.id,
      kind: toKind,
      label: to.label,
      source,
    });
    edges.push({
      confidence: "source_declared",
      evidence: firstString(item.relationship, ["evidence", "basis", "sourceText"])
        ?? `Supplied ${source} record explicitly declares this ${kind.replace(/^declared_/, "").replace(/_/g, " ")} relationship; Dude did not infer it.`,
      from: from.id,
      kind,
      to: to.id,
    });
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
      { label: "Source-declared edges", value: graph.edges.filter((edge) => edge.confidence === "source_declared").length, source: "Graph builder" },
      { label: "Inferred ownership/control edges", value: 0, source: "Graph builder" },
    ],
    evidence: [
      { label: "ACRA records inspected", value: acra.length, source: "ACRA" },
      { label: "Explicit relationship records inspected", value: explicitRelationships.length, source: "Input records" },
    ],
    records: { graph },
    gaps: acra.length === 0 && explicitRelationships.length === 0 ? [toGap("NO_GRAPH_RECORDS", "No ACRA or explicit relationship records were supplied for relationship graph construction.")] : [],
    provenance: [
      toProvenance("Supplied dossier records", "sg_relationship_graph", "Graph edges derived from supplied public ACRA fields and explicit source-declared relationship records.", false, acra.length + explicitRelationships.length, "https://www.acra.gov.sg/resources/open-data-initiative/"),
    ],
    freshness: [toFreshness("Relationship graph", observedAt)],
    limits: [
      toLimit("NO_INFERRED_OWNERSHIP_OR_CONTROL", "The graph does not infer directors, shareholders, beneficial owners, subsidiaries, parent entities, or control. It represents those relationships only when supplied records explicitly declare them."),
      toLimit("DECLARED_RELATIONSHIPS_REQUIRE_SOURCE_REVIEW", "Source-declared relationship edges must be reviewed against the underlying source record before relying on them."),
      toLimit("NO_SHARED_ADDRESS_OR_NAME_FAMILY_INFERENCE", "Shared registered addresses and similar entity names are not converted into relationship edges."),
    ],
  };
};
