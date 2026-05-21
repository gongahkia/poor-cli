import type { PeopleDiscovery, WebPresence } from "@/lib/api/client";
import type { BusinessDossier, SourceCoverageItem } from "@/types/dossier";

export type SupplementalProviderState = "configured" | "unconfigured" | "error" | "rate_limited";
export type SupplementalOutcomeState = "candidate_match" | "no_result";

export type SupplementalEvidenceReviewItem = {
  id: string;
  title: string;
  provider: string;
  tool: string;
  evidenceLabels: string[];
  providerState: SupplementalProviderState;
  outcome: SupplementalOutcomeState;
  confidenceLabel: string;
  limitationLabel: string;
  recordCount: number;
  caveat: string;
  sourceUseWarning: string | null;
  gaps: string[];
  limits: string[];
};

type SupplementalEvidenceParams = {
  dossier: BusinessDossier;
  peopleDiscovery?: PeopleDiscovery;
  webPresence?: WebPresence;
};

type ExternalArtifact = {
  title?: unknown;
  summary?: unknown;
  records?: unknown;
  gaps?: unknown;
  provenance?: unknown;
  limits?: unknown;
  riskFlags?: unknown;
};

const SUPPLEMENTAL_FAMILIES = new Set([
  "opensanctions",
  "opencorporates",
  "adverse_media_lite",
  "relationship_graph",
  "web_presence",
  "people_discovery",
]);

const normalize = (value: string): string => value.trim().toLowerCase();

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const asRecords = (value: unknown): Record<string, unknown>[] =>
  Array.isArray(value) ? value.filter(isRecord) : [];

const stringValue = (value: unknown): string | null =>
  typeof value === "string" && value.trim() !== "" ? value.trim() : null;

const numberValue = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;

const artifactTitle = (artifact: ExternalArtifact): string =>
  stringValue(artifact.title) ?? "Supplemental evidence";

const getExternalArtifacts = (dossier: BusinessDossier): ExternalArtifact[] =>
  asRecords(dossier.records.externalDiligence).map((record) => record as ExternalArtifact);

const findCoverage = (
  dossier: BusinessDossier,
  family: string,
): SourceCoverageItem | undefined =>
  (dossier.sourceCoverage ?? []).find((item) => item.family === family);

const supplementalCoverage = (dossier: BusinessDossier): SourceCoverageItem[] =>
  (dossier.sourceCoverage ?? []).filter((item) =>
    SUPPLEMENTAL_FAMILIES.has(item.family) || item.evidenceType === "web_discovery");

const findArtifact = (
  artifacts: readonly ExternalArtifact[],
  title: string,
): ExternalArtifact | undefined =>
  artifacts.find((artifact) => normalize(artifactTitle(artifact)) === normalize(title));

const summaryValue = (artifact: ExternalArtifact | undefined, label: string): unknown => {
  const rows = asRecords(artifact?.summary);
  return rows.find((row) => normalize(String(row["label"] ?? "")) === normalize(label))?.["value"];
};

const artifactGaps = (artifact: ExternalArtifact | undefined): string[] =>
  asRecords(artifact?.gaps).map((gap) => {
    const code = String(gap["code"] ?? "SUPPLEMENTAL_GAP");
    const message = String(gap["message"] ?? "");
    return message === "" ? code : `${code}: ${message}`;
  });

const artifactLimits = (artifact: ExternalArtifact | undefined): string[] =>
  asRecords(artifact?.limits).map((limit) => {
    const code = String(limit["code"] ?? "LIMIT");
    const message = String(limit["message"] ?? "");
    return message === "" ? code : `${code}: ${message}`;
  });

const allGapText = (
  coverage: SourceCoverageItem | undefined,
  artifact: ExternalArtifact | undefined,
): string => [
  coverage?.status,
  coverage?.reason,
  ...(coverage?.gapCodes ?? []),
  ...artifactGaps(artifact),
].filter((value): value is string => typeof value === "string").join(" ");

const providerState = (
  coverage: SourceCoverageItem | undefined,
  artifact: ExternalArtifact | undefined,
): SupplementalProviderState => {
  const gapText = allGapText(coverage, artifact);
  if (/rate[_\s-]?limit|http 429|\b429\b/i.test(gapText)) return "rate_limited";
  if (coverage?.status === "credential_blocked" || /credential|api[_\s-]?key|required|token/i.test(gapText)) {
    return "unconfigured";
  }
  if (coverage?.status === "unavailable" || /unavailable|upstream_failed|failed|http [45]\d\d/i.test(gapText)) {
    return "error";
  }
  return "configured";
};

const sourceUseWarning = (
  coverage: SourceCoverageItem | undefined,
  artifact: ExternalArtifact | undefined,
): string | null => {
  const limitText = artifactLimits(artifact).join(" ");
  if (
    coverage?.authRequired === true
    || (coverage?.requiredCredentials?.length ?? 0) > 0
    || /license|licence|token|credential|api key|commercial/i.test(limitText)
  ) {
    return "Provider credentials, plan terms, and source licences may affect coverage and reuse.";
  }
  return null;
};

const formatCount = (count: number, singular: string, plural = `${singular}s`): string =>
  `${count} ${count === 1 ? singular : plural}`;

const buildExternalItem = (
  params: {
    artifact?: ExternalArtifact;
    caveat: string;
    confidenceNoResult: string;
    confidenceWithResult: string;
    dossier: BusinessDossier;
    family: string;
    limitation: string;
    provider: string;
    recordCount: number;
    title: string;
    tool: string;
    labels?: readonly string[];
  },
): SupplementalEvidenceReviewItem => {
  const coverage = findCoverage(params.dossier, params.family);
  const state = providerState(coverage, params.artifact);
  const recordCount = params.recordCount;
  const evidenceLabels = Array.from(new Set([
    ...(params.labels ?? ["Third-party provider"]),
    "Not official registry fact",
    "Analyst-review only",
  ]));
  return {
    caveat: params.caveat,
    confidenceLabel: recordCount > 0 ? params.confidenceWithResult : params.confidenceNoResult,
    evidenceLabels,
    gaps: [
      ...(coverage?.gapCodes ?? []).map((code) => `${code}: ${coverage.reason}`),
      ...artifactGaps(params.artifact),
    ],
    id: params.family,
    limitationLabel: params.limitation,
    limits: artifactLimits(params.artifact),
    outcome: recordCount > 0 ? "candidate_match" : "no_result",
    provider: params.provider,
    providerState: state,
    recordCount,
    sourceUseWarning: sourceUseWarning(coverage, params.artifact),
    title: params.title,
    tool: params.tool,
  };
};

export const providerStateLabel = (state: SupplementalProviderState): string => {
  if (state === "configured") return "Configured";
  if (state === "unconfigured") return "Unconfigured";
  if (state === "rate_limited") return "Rate-limited";
  return "Error";
};

export const outcomeStateLabel = (state: SupplementalOutcomeState): string =>
  state === "candidate_match" ? "Candidate result" : "No result";

export const buildSupplementalEvidenceReviewItems = ({
  dossier,
  peopleDiscovery,
  webPresence,
}: SupplementalEvidenceParams): SupplementalEvidenceReviewItem[] => {
  const artifacts = getExternalArtifacts(dossier);
  const sanctions = findArtifact(artifacts, "Sanctions Screen");
  const opencorporates = findArtifact(artifacts, "OpenCorporates Cross-Links");
  const adverse = findArtifact(artifacts, "Adverse Media Lite");
  const graph = findArtifact(artifacts, "Relationship Graph");
  const coverageByFamily = new Map(supplementalCoverage(dossier).map((item) => [item.family, item]));
  const items: SupplementalEvidenceReviewItem[] = [];

  const webCoverage = coverageByFamily.get("web_presence");
  if (webPresence !== undefined || webCoverage !== undefined) {
    const configured = webPresence?.configured === true;
    const state: SupplementalProviderState = webPresence === undefined
      ? providerState(webCoverage, undefined)
      : !configured
        ? "unconfigured"
        : webCoverage?.status === "unavailable"
          ? "error"
          : "configured";
    const recordCount = webPresence?.results.length ?? webCoverage?.recordCount ?? 0;
    items.push({
      caveat: "Web presence is a public web lead only. It is not registry identity evidence.",
      confidenceLabel: recordCount > 0
        ? "Candidate web result. Confirm the site is company-controlled before relying on it."
        : "No web result returned. This is not evidence that no web presence exists.",
      evidenceLabels: ["Supplemental public web", "Not official registry fact", "Analyst-review only"],
      gaps: webCoverage?.gapCodes?.map((code) => `${code}: ${webCoverage.reason}`) ?? [],
      id: "web_presence",
      limitationLabel: "Search snippets can be stale, duplicated, SEO-biased, or unrelated to the legal entity.",
      limits: webPresence?.limits ?? [],
      outcome: recordCount > 0 ? "candidate_match" : "no_result",
      provider: "TinyFish Search",
      providerState: state,
      recordCount,
      sourceUseWarning: sourceUseWarning(webCoverage, undefined),
      title: "Web presence",
      tool: "TinyFish Search",
    });
  }

  const peopleCoverage = coverageByFamily.get("people_discovery");
  if (peopleDiscovery !== undefined || peopleCoverage !== undefined) {
    const configured = peopleDiscovery?.configured === true;
    const state: SupplementalProviderState = peopleDiscovery === undefined
      ? providerState(peopleCoverage, undefined)
      : !configured
        ? "unconfigured"
        : peopleCoverage?.status === "unavailable"
          ? "error"
          : "configured";
    const recordCount = peopleDiscovery?.results.length ?? peopleCoverage?.recordCount ?? 0;
    items.push({
      caveat: "People discovery finds public candidate references only. It does not verify employment, authority, or current role.",
      confidenceLabel: recordCount > 0
        ? "Candidate people reference. Verify role and authority against official or company-controlled sources."
        : "No people-oriented result returned. This is not evidence that no relevant person exists.",
      evidenceLabels: ["Supplemental public web", "Not official registry fact", "Analyst-review only"],
      gaps: peopleCoverage?.gapCodes?.map((code) => `${code}: ${peopleCoverage.reason}`) ?? [],
      id: "people_discovery",
      limitationLabel: "Search snippets may identify unrelated, former, or unauthorised people.",
      limits: peopleDiscovery?.limits ?? [],
      outcome: recordCount > 0 ? "candidate_match" : "no_result",
      provider: "TinyFish Search",
      providerState: state,
      recordCount,
      sourceUseWarning: sourceUseWarning(peopleCoverage, undefined),
      title: "People discovery",
      tool: "TinyFish Search",
    });
  }

  if (sanctions !== undefined || coverageByFamily.has("opensanctions")) {
    const count = numberValue(summaryValue(sanctions, "Candidate matches"))
      ?? coverageByFamily.get("opensanctions")?.recordCount
      ?? 0;
    items.push(buildExternalItem({
      artifact: sanctions,
      caveat: "OpenSanctions returns candidate screening results only; absence of candidates is not sanctions clearance.",
      confidenceNoResult: "No candidate above threshold. Not a regulated sanctions determination.",
      confidenceWithResult: `${formatCount(count, "candidate")} above threshold. Analyst review required before treating as a true hit.`,
      dossier,
      family: "opensanctions",
      limitation: "Provider coverage, threshold, matching model, credentials, and licence terms affect review value.",
      provider: "OpenSanctions",
      recordCount: count,
      title: "OpenSanctions candidate screen",
      tool: "sg_sanctions_screen",
    }));
  }

  if (opencorporates !== undefined || coverageByFamily.has("opencorporates")) {
    const count = numberValue(summaryValue(opencorporates, "Candidate links"))
      ?? coverageByFamily.get("opencorporates")?.recordCount
      ?? 0;
    items.push(buildExternalItem({
      artifact: opencorporates,
      caveat: "OpenCorporates links are cross-references only; they are not ownership, control, or beneficial-owner evidence.",
      confidenceNoResult: "No candidate company link returned. This is a cross-link gap, not proof of no link.",
      confidenceWithResult: `${formatCount(count, "candidate link")} returned. Confirm against source rows before use.`,
      dossier,
      family: "opencorporates",
      limitation: "Provider token, plan terms, jurisdiction coverage, and matching quality affect results.",
      provider: "OpenCorporates",
      recordCount: count,
      title: "OpenCorporates cross-links",
      tool: "sg_opencorporates_links",
    }));
  }

  if (adverse !== undefined || coverageByFamily.has("adverse_media_lite")) {
    const count = numberValue(summaryValue(adverse, "Feed items matched"))
      ?? coverageByFamily.get("adverse_media_lite")?.recordCount
      ?? 0;
    items.push(buildExternalItem({
      artifact: adverse,
      caveat: "Adverse-media lite searches configured official feeds only. No result is not adverse-media clearance.",
      confidenceNoResult: "No configured-feed keyword result. Not open-web adverse-media clearance.",
      confidenceWithResult: `${formatCount(count, "official-feed item")} matched keyword rules. Analyst review required.`,
      dossier,
      family: "adverse_media_lite",
      labels: ["Supplemental public web"],
      limitation: "No sentiment, culpability, or adverse-event category is inferred.",
      provider: "Official Singapore public feeds",
      recordCount: count,
      title: "Adverse-media lite",
      tool: "sg_adverse_media_lite",
    }));
  }

  if (graph !== undefined || coverageByFamily.has("relationship_graph")) {
    const count = numberValue(summaryValue(graph, "Source-declared edges")) ?? 0;
    items.push(buildExternalItem({
      artifact: graph,
      caveat: "Relationship graph output is limited to explicit source-declared links. It does not infer beneficial ownership or control.",
      confidenceNoResult: "No explicit source-declared relationship link returned.",
      confidenceWithResult: `${formatCount(count, "explicit source-declared link")} returned. Review the underlying source record.`,
      dossier,
      family: "relationship_graph",
      labels: ["Analyst-review only"],
      limitation: "No beneficial ownership, control, parent, subsidiary, or director relationship is inferred.",
      provider: "Dude relationship graph",
      recordCount: count,
      title: "Relationship graph",
      tool: "sg_relationship_graph",
    }));
  }

  return items;
};

export const supplementalEvidenceCaveat = "Supplemental evidence is not official registry evidence, sanctions clearance, adverse-media clearance, credit advice, or an ownership/control determination. No result is a coverage gap, not a positive finding.";
