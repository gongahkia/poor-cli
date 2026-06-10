import type { AiProvider, GenerateResult } from "../ai/providers.js";
import { generateText, ProviderRequestError, resolveAiProviderConfig, type ProviderConfig } from "../ai/providers.js";

type SummaryItem = {
  readonly label: string;
  readonly value: unknown;
  readonly source?: string | null;
};

type EvidenceGap = {
  readonly code: string;
  readonly message: string;
};

type ProvenanceItem = {
  readonly source: string;
  readonly tool: string;
  readonly coverage: string;
  readonly authRequired: boolean;
  readonly recordCount: number;
  readonly sourceUrl?: string;
};

type FreshnessItem = {
  readonly source: string;
  readonly observedAt: string;
  readonly upstreamTimestamp?: string | null;
};

type BriefLimit = {
  readonly code: string;
  readonly message: string;
};

type SourceCoverageItem = {
  readonly family: string;
  readonly label: string;
  readonly tools: readonly string[];
  readonly status: "checked" | "skipped" | "unavailable" | "credential_blocked" | "not_applicable";
  readonly coverageLevel: "full" | "partial" | "none";
  readonly recordCount: number;
  readonly authRequired: boolean;
  readonly reason: string;
  readonly checkedAt?: string | null;
  readonly sourceFreshness?: string | null;
  readonly requiredCredentials?: readonly string[];
  readonly gapCodes?: readonly string[];
  readonly evidenceType?: "official_registry" | "web_discovery" | "operational_metadata";
};

type RiskFlag = {
  readonly code: string;
  readonly severity: "high" | "medium" | "low";
  readonly message: string;
  readonly source: string;
};

type NextCheck = {
  readonly tool: string;
  readonly reason: string;
  readonly input: Record<string, unknown>;
};

type AnalystFollowUp = {
  readonly id: string;
  readonly priority: "critical" | "recommended" | "optional";
  readonly category:
    | "identity_confidence"
    | "source_unavailable"
    | "sector_gap"
    | "supplemental_review"
    | "credential_required"
    | "manual_confirmation"
    | "report_quality";
  readonly action: string;
  readonly reason: string;
  readonly whyThisMatters: string;
  readonly evidenceBasis: readonly {
    readonly kind: "source_gap" | "confidence_blocker" | "skipped_module" | "evidence_limitation";
    readonly ref: string;
    readonly detail: string;
    readonly source?: string | null;
  }[];
  readonly tool?: string;
  readonly input?: Record<string, unknown>;
};

export type AnalystMemoDossier = {
  readonly title: string;
  readonly summary: readonly SummaryItem[];
  readonly evidence: readonly SummaryItem[];
  readonly records: Record<string, unknown>;
  readonly gaps: readonly EvidenceGap[];
  readonly provenance: readonly ProvenanceItem[];
  readonly freshness: readonly FreshnessItem[];
  readonly limits: readonly BriefLimit[];
  readonly sourceCoverage?: readonly SourceCoverageItem[];
  readonly riskFlags?: readonly RiskFlag[];
  readonly analystFollowUps?: readonly AnalystFollowUp[];
  readonly nextChecks?: readonly NextCheck[];
};

type WebPresenceForMemo = {
  readonly query?: string;
  readonly configured: boolean;
  readonly results?: readonly WebSearchResultForMemo[];
  readonly possibleOfficialWebsite?: string | null;
  readonly limits: readonly string[];
};

type PeopleDiscoveryForMemo = {
  readonly entityName: string;
  readonly uen?: string | null;
  readonly query: string;
  readonly configured: boolean;
  readonly results: readonly WebSearchResultForMemo[];
  readonly suggestedActions: readonly string[];
  readonly limits: readonly string[];
};

type WebSearchResultForMemo = {
  readonly title: string;
  readonly snippet: string;
  readonly url: string;
  readonly siteName: string | null;
  readonly position: number;
};

type Citation = {
  readonly id: string;
  readonly label: string;
  readonly source: string;
  readonly text: string;
};

type MemoBullet = {
  readonly text: string;
  readonly citationIds: readonly string[];
};

type MemoRiskRating = {
  readonly level: "low" | "medium" | "high" | "unknown";
  readonly rationale: string;
  readonly citationIds: readonly string[];
  readonly confidenceBlockers: readonly string[];
};

type DecisionAid = {
  readonly nextSteps: readonly string[];
  readonly confidenceBlockers: readonly string[];
  readonly nonAdvisoryReminder: string;
};

type RejectedClaim = {
  readonly claim: string;
  readonly reason: string;
};

export type AnalystMemoReady = {
  readonly status: "ready";
  readonly configured: true;
  readonly provider: AiProvider;
  readonly model: string;
  readonly generatedAt: string;
  readonly evidenceMemo: readonly MemoBullet[];
  readonly riskRating: MemoRiskRating;
  readonly decisionAid: DecisionAid;
  readonly citations: readonly Citation[];
  readonly gaps: readonly EvidenceGap[];
  readonly limits: readonly BriefLimit[];
  readonly rejectedClaims: readonly RejectedClaim[];
};

export type AnalystMemoUnavailable = {
  readonly status: "unavailable";
  readonly configured: false;
  readonly provider: AiProvider;
  readonly model: string;
  readonly generatedAt: string;
  readonly reason: ProviderConfig["configured"] extends false ? never : {
    readonly code: string;
    readonly message: string;
  };
  readonly gaps: readonly EvidenceGap[];
  readonly limits: readonly BriefLimit[];
};

export type AnalystMemoError = {
  readonly status: "error";
  readonly configured: true;
  readonly provider: AiProvider;
  readonly model: string;
  readonly generatedAt: string;
  readonly reason: {
    readonly code: "AI_PROVIDER_FAILED" | "AI_OUTPUT_INVALID";
    readonly message: string;
  };
  readonly gaps: readonly EvidenceGap[];
  readonly limits: readonly BriefLimit[];
};

export type AnalystMemoResponse = AnalystMemoReady | AnalystMemoUnavailable | AnalystMemoError;

type ModelMemo = {
  readonly evidenceMemo?: readonly unknown[];
  readonly riskRating?: unknown;
  readonly decisionAid?: unknown;
  readonly limits?: readonly unknown[];
};

type GenerateText = typeof generateText;

type GenerateAnalystMemoOptions = {
  readonly env?: NodeJS.ProcessEnv;
  readonly generatedAt?: Date;
  readonly generate?: GenerateText;
};

const SYSTEM_PROMPT = [
  "You write counterparty diligence memos from a bounded Singapore public-data dossier.",
  "Use only the provided dossier envelope and the listed citation ids.",
  "Do not add directors, shareholders, ownership, litigation, sanctions, financial strength, or credit opinions unless explicitly present in the dossier.",
  "Write like an internal diligence team: concise, specific, non-repetitive, and oriented to what a reviewer should do next.",
  "Do not repeat the same registry fact in adjacent sentences. Prefer one integrated paragraph over a string of mechanically restated fields.",
  "Do not say 'no sanctions', 'no adverse media', or 'no active licences' unless the relevant provider actually returned searched evidence. If a provider is unavailable, frame it as a gap or blocker.",
  "Web presence and people-discovery snippets are supplemental analyst-review evidence only; never treat them as official registry facts or verified employment/authority evidence.",
  "Decision aid items must be operational next checks and confidence blockers, not legal, tax, investment, or licensed-advisor advice.",
  "The first evidenceMemo item must be a polished 2-3 sentence executive summary for a senior reviewer; it should identify the counterparty, state the most material evidence-backed fact once, explain the risk posture, and call out the main caveats or missing checks.",
  "Confidence blockers must name the missing source, upstream gap, unsupported inference, or unavailable credential. Never return a placeholder such as 'missing evidence that blocks confidence'.",
  "Return strict JSON only.",
].join("\n");

const PROVIDER_KEY_ENV: Record<AiProvider, string> = {
  anthropic: "ANTHROPIC_API_KEY",
  google: "GOOGLE_API_KEY",
  openai: "OPENAI_API_KEY",
};

const stringifyValue = (value: unknown): string => {
  if (value === null || value === undefined || value === "") return "not available";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
};

const citation = (id: string, label: string, source: string, text: string): Citation => ({
  id,
  label,
  source,
  text,
});

const MEMO_RECORD_KEYS = [
  "resolution",
  "quality",
  "acra",
  "bcaLicensedBuilders",
  "bcaRegisteredContractors",
  "ceaSalespersons",
  "gebizTenders",
  "boaArchitects",
  "boaArchitectureFirms",
  "hsaLicensedPharmacies",
  "hsaHealthProductLicensees",
  "hlbHotels",
  "externalDiligence",
] as const;

const MAX_PROMPT_ARRAY_ITEMS = 8;
const MAX_PROMPT_OBJECT_KEYS = 32;
const MAX_PROMPT_STRING_LENGTH = 2400;
const MAX_DIGEST_SAMPLE_ITEMS = 8;
const MAX_DIGEST_FIELD_EXAMPLES = 4;

const boundPromptValue = (value: unknown, depth = 0): unknown => {
  if (value === null || value === undefined) return value;
  if (typeof value === "string") {
    return value.length > MAX_PROMPT_STRING_LENGTH
      ? `${value.slice(0, MAX_PROMPT_STRING_LENGTH)}...`
      : value;
  }
  if (typeof value === "number" || typeof value === "boolean") return value;
  if (depth >= 4) return "[nested value omitted]";
  if (Array.isArray(value)) {
    return value.slice(0, MAX_PROMPT_ARRAY_ITEMS).map((item) => boundPromptValue(item, depth + 1));
  }
  if (typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .slice(0, MAX_PROMPT_OBJECT_KEYS)
        .map(([key, item]) => [key, boundPromptValue(item, depth + 1)]),
    );
  }
  return String(value);
};

const buildMemoRecordsInput = (records: Record<string, unknown>): Record<string, unknown> =>
  Object.fromEntries(
    MEMO_RECORD_KEYS
      .filter((key) => records[key] !== undefined)
      .map((key) => [key, boundPromptValue(records[key])]),
  );

const digestExample = (value: unknown): string | null => {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "string") return value.length > 220 ? `${value.slice(0, 220)}...` : value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return `[array:${value.length}]`;
  if (typeof value === "object") return "[object]";
  return String(value);
};

const buildFieldCoverageDigest = (items: readonly unknown[]) => {
  const fields = new Map<string, { present: number; examples: string[] }>();
  for (const item of items) {
    if (item === null || typeof item !== "object" || Array.isArray(item)) continue;
    for (const [field, value] of Object.entries(item as Record<string, unknown>)) {
      const current = fields.get(field) ?? { examples: [], present: 0 };
      const example = digestExample(value);
      fields.set(field, {
        examples: example === null || current.examples.includes(example) || current.examples.length >= MAX_DIGEST_FIELD_EXAMPLES
          ? current.examples
          : [...current.examples, example],
        present: current.present + 1,
      });
    }
  }
  return Array.from(fields.entries())
    .map(([field, value]) => ({ field, ...value }))
    .sort((left, right) => right.present - left.present || left.field.localeCompare(right.field))
    .slice(0, MAX_PROMPT_OBJECT_KEYS);
};

const buildRecordDigests = (records: Record<string, unknown>): readonly Record<string, unknown>[] =>
  MEMO_RECORD_KEYS.flatMap((key) => {
    const value = records[key];
    if (value === undefined) return [];
    if (!Array.isArray(value)) {
      return [{
        count: 1,
        key,
        sample: boundPromptValue(value),
      }];
    }
    return [{
      count: value.length,
      fieldCoverage: buildFieldCoverageDigest(value),
      key,
      omittedCount: Math.max(value.length - MAX_DIGEST_SAMPLE_ITEMS, 0),
      sample: value.slice(0, MAX_DIGEST_SAMPLE_ITEMS).map((item) => boundPromptValue(item)),
      sampledCount: Math.min(value.length, MAX_DIGEST_SAMPLE_ITEMS),
    }];
  });

const buildRecordCitations = (records: Record<string, unknown>): readonly Citation[] => {
  const citations: Citation[] = [];
  for (const key of MEMO_RECORD_KEYS) {
    const value = records[key];
    if (value === undefined) continue;
    if (Array.isArray(value)) {
      const recordCitationLimit = key === "externalDiligence" ? 5 : 2;
      value.slice(0, recordCitationLimit).forEach((item, index) => {
        citations.push(citation(
          `record-${key}-${index + 1}`,
          `${key} record ${index + 1}`,
          key,
          stringifyValue(boundPromptValue(item)),
        ));
      });
      continue;
    }
    citations.push(citation(`record-${key}`, `${key} record`, key, stringifyValue(boundPromptValue(value))));
  }
  return citations;
};

const buildSupplementalCitationSource = (result: WebSearchResultForMemo): string =>
  result.siteName ?? result.url;

const buildCitations = (
  dossier: AnalystMemoDossier,
  supplemental: Readonly<{
    webPresence?: WebPresenceForMemo;
    peopleDiscovery?: PeopleDiscoveryForMemo;
  }> = {},
): readonly Citation[] => {
  const citations: Citation[] = [];
  dossier.summary.forEach((item, index) => {
    citations.push(citation(
      `summary-${index + 1}`,
      item.label,
      item.source ?? "summary",
      `${item.label}: ${stringifyValue(item.value)}`,
    ));
  });
  dossier.evidence.forEach((item, index) => {
    citations.push(citation(
      `evidence-${index + 1}`,
      item.label,
      item.source ?? "evidence",
      `${item.label}: ${stringifyValue(item.value)}`,
    ));
  });
  (dossier.riskFlags ?? []).forEach((flag, index) => {
    citations.push(citation(
      `risk-${index + 1}`,
      flag.code,
      flag.source,
      `${flag.severity}: ${flag.message}`,
    ));
  });
  dossier.gaps.forEach((gap, index) => {
    citations.push(citation(`gap-${index + 1}`, gap.code, "gap", gap.message));
  });
  dossier.provenance.forEach((item, index) => {
    citations.push(citation(
      `provenance-${index + 1}`,
      item.source,
      item.tool,
      `${item.coverage} Records: ${item.recordCount}. Auth required: ${item.authRequired ? "yes" : "no"}.`,
    ));
  });
  dossier.freshness.forEach((item, index) => {
    citations.push(citation(
      `freshness-${index + 1}`,
      item.source,
      "freshness",
      `Observed at ${item.observedAt}; upstream timestamp ${item.upstreamTimestamp ?? "not provided"}.`,
    ));
  });
  dossier.limits.forEach((limit, index) => {
    citations.push(citation(`limit-${index + 1}`, limit.code, "limit", limit.message));
  });
  (dossier.sourceCoverage ?? []).forEach((item, index) => {
    citations.push(citation(
      `coverage-${index + 1}`,
      item.label,
      "source coverage",
      `${item.status}/${item.coverageLevel}; records ${item.recordCount}; ${item.reason}`,
    ));
  });
  (dossier.analystFollowUps ?? []).forEach((followUp, index) => {
    citations.push(citation(
      `follow-up-${index + 1}`,
      followUp.action,
      "analyst follow-up",
      `${followUp.priority}/${followUp.category}; ${followUp.reason}; why this matters: ${followUp.whyThisMatters}; evidence: ${followUp.evidenceBasis.map((basis) => `${basis.kind}:${basis.ref}`).join(", ")}`,
    ));
  });
  (dossier.nextChecks ?? []).forEach((check, index) => {
    citations.push(citation(
      `next-${index + 1}`,
      check.tool,
      "next check",
      `${check.reason}; input: ${JSON.stringify(check.input)}`,
    ));
  });
  citations.push(...buildRecordCitations(dossier.records));
  if (supplemental.webPresence !== undefined) {
    if (supplemental.webPresence.possibleOfficialWebsite !== undefined && supplemental.webPresence.possibleOfficialWebsite !== null) {
      citations.push(citation(
        "web-presence-official",
        "Possible official website",
        "TinyFish Search",
        supplemental.webPresence.possibleOfficialWebsite,
      ));
    }
    (supplemental.webPresence.results ?? []).slice(0, 5).forEach((result, index) => {
      citations.push(citation(
        `web-presence-${index + 1}`,
        result.title,
        buildSupplementalCitationSource(result),
        `${result.title}: ${result.snippet} (${result.url})`,
      ));
    });
    supplemental.webPresence.limits.forEach((limit, index) => {
      citations.push(citation(`web-presence-limit-${index + 1}`, "Web presence limit", "TinyFish Search", limit));
    });
  }
  if (supplemental.peopleDiscovery !== undefined) {
    supplemental.peopleDiscovery.results.slice(0, 5).forEach((result, index) => {
      citations.push(citation(
        `people-discovery-${index + 1}`,
        result.title,
        buildSupplementalCitationSource(result),
        `${result.title}: ${result.snippet} (${result.url})`,
      ));
    });
    supplemental.peopleDiscovery.suggestedActions.forEach((action, index) => {
      citations.push(citation(`people-discovery-action-${index + 1}`, "People discovery action", "TinyFish Search", action));
    });
    supplemental.peopleDiscovery.limits.forEach((limit, index) => {
      citations.push(citation(`people-discovery-limit-${index + 1}`, "People discovery limit", "TinyFish Search", limit));
    });
  }
  return citations;
};

const buildWebPresencePromptInput = (webPresence: WebPresenceForMemo | undefined) => {
  if (webPresence === undefined) return undefined;
  return {
    configured: webPresence.configured,
    limits: webPresence.limits,
    possibleOfficialWebsite: webPresence.possibleOfficialWebsite ?? null,
    query: webPresence.query ?? null,
    results: (webPresence.results ?? []).slice(0, 5).map((result, index) => ({
      citationId: `web-presence-${index + 1}`,
      position: result.position,
      siteName: result.siteName,
      snippet: result.snippet,
      title: result.title,
      url: result.url,
    })),
  };
};

const buildPeopleDiscoveryPromptInput = (peopleDiscovery: PeopleDiscoveryForMemo | undefined) => {
  if (peopleDiscovery === undefined) return undefined;
  return {
    configured: peopleDiscovery.configured,
    entityName: peopleDiscovery.entityName,
    limits: peopleDiscovery.limits,
    query: peopleDiscovery.query,
    results: peopleDiscovery.results.slice(0, 5).map((result, index) => ({
      citationId: `people-discovery-${index + 1}`,
      position: result.position,
      siteName: result.siteName,
      snippet: result.snippet,
      title: result.title,
      url: result.url,
    })),
    suggestedActions: peopleDiscovery.suggestedActions,
    uen: peopleDiscovery.uen ?? null,
  };
};

const buildPrompt = (
  dossier: AnalystMemoDossier,
  citations: readonly Citation[],
  webPresence: WebPresenceForMemo | undefined,
  peopleDiscovery: PeopleDiscoveryForMemo | undefined,
): string => JSON.stringify({
  instructions: {
    outputSchema: {
      evidenceMemo: [{ text: "Human-written 2-3 sentence executive summary or evidence-bound finding; avoid repeating the same registry fact and do not convert unavailable providers into negative findings", citationIds: ["summary-1"] }],
      riskRating: {
        level: "low|medium|high|unknown",
        rationale: "short evidence-grounded rationale",
        citationIds: ["risk-1", "gap-1"],
        confidenceBlockers: ["specific missing source, unavailable upstream, or unsupported inference"],
      },
      decisionAid: {
        nextSteps: ["operational follow-up only"],
        confidenceBlockers: ["specific source or credential gap that blocks confidence"],
      },
      limits: ["public-data limits carried into the memo"],
    },
    citationIds: citations.map((item) => item.id),
  },
  dossier: {
    evidence: dossier.evidence,
    freshness: dossier.freshness,
    gaps: dossier.gaps,
    limits: dossier.limits,
    analystFollowUps: dossier.analystFollowUps ?? [],
    nextChecks: dossier.nextChecks ?? [],
    provenance: dossier.provenance,
    recordDigests: buildRecordDigests(dossier.records),
    records: {
      ...buildMemoRecordsInput(dossier.records),
    },
    riskFlags: dossier.riskFlags ?? [],
    sourceCoverage: dossier.sourceCoverage ?? [],
    summary: dossier.summary,
    title: dossier.title,
  },
  citations,
  supplementalReview: {
    peopleDiscovery: buildPeopleDiscoveryPromptInput(peopleDiscovery),
    webPresence: buildWebPresencePromptInput(webPresence),
  },
});

const parseJsonObject = (text: string): ModelMemo | null => {
  const trimmed = text.trim();
  const start = trimmed.indexOf("{");
  const end = trimmed.lastIndexOf("}");
  if (start === -1 || end === -1 || end <= start) {
    return null;
  }
  try {
    const parsed = JSON.parse(trimmed.slice(start, end + 1)) as unknown;
    return parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed as ModelMemo
      : null;
  } catch {
    return null;
  }
};

const asString = (value: unknown): string | null =>
  typeof value === "string" && value.trim() !== "" ? value.trim() : null;

const asStringArray = (value: unknown): readonly string[] =>
  Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && item.trim() !== "").map((item) => item.trim())
    : [];

const isRiskLevel = (value: unknown): value is MemoRiskRating["level"] =>
  value === "low" || value === "medium" || value === "high" || value === "unknown";

const getRiskLevelFromDossier = (dossier: AnalystMemoDossier): MemoRiskRating["level"] => {
  const flags = dossier.riskFlags ?? [];
  if (flags.some((flag) => flag.severity === "high")) return "high";
  if (flags.some((flag) => flag.severity === "medium")) return "medium";
  if (flags.some((flag) => flag.severity === "low")) return "low";
  return dossier.provenance.some((item) => item.recordCount > 0) ? "low" : "unknown";
};

const filterCitationIds = (
  citationIds: readonly string[],
  citationById: ReadonlyMap<string, Citation>,
): readonly string[] => citationIds.filter((id) => citationById.has(id));

const prohibitedFollowUpPattern = /\b(approve|approval|reject|rejection|clear|clearance|safe|safety)\b/i;

const filterOperationalFollowUps = (items: readonly string[]): readonly string[] =>
  items.filter((item) => !prohibitedFollowUpPattern.test(item));

const fallbackDecisionNextSteps = (dossier: AnalystMemoDossier): readonly string[] => {
  const analystFollowUps = dossier.analystFollowUps ?? [];
  if (analystFollowUps.length > 0) {
    return analystFollowUps.slice(0, 4).map((followUp) =>
      `[${followUp.priority}] ${followUp.action} Evidence gap: ${followUp.reason}`,
    );
  }
  return (dossier.nextChecks ?? []).slice(0, 4).map((check) => `${check.tool}: ${check.reason}`);
};

const buildFallbackRiskRating = (
  dossier: AnalystMemoDossier,
  citationById: ReadonlyMap<string, Citation>,
): MemoRiskRating => {
  const riskCitationIds = Array.from(citationById.keys())
    .filter((id) => id.startsWith("risk-") || id.startsWith("gap-") || id.startsWith("coverage-") || id.startsWith("provenance-"))
    .slice(0, 4);
  return {
    citationIds: riskCitationIds,
    confidenceBlockers: [
      ...(dossier.sourceCoverage ?? [])
        .filter((item) => item.status !== "checked" || item.coverageLevel !== "full")
        .map((item) => `${item.label}: ${item.reason}`),
      ...dossier.gaps.map((gap) => gap.message),
      ...dossier.limits.slice(0, 2).map((limit) => limit.message),
    ].slice(0, 5),
    level: getRiskLevelFromDossier(dossier),
    rationale: "Risk rating is bounded to returned public registry evidence, risk flags, gaps, and stated limits.",
  };
};

const groundModelMemo = (
  modelMemo: ModelMemo,
  dossier: AnalystMemoDossier,
  citations: readonly Citation[],
): Pick<AnalystMemoReady, "evidenceMemo" | "riskRating" | "decisionAid" | "citations" | "rejectedClaims" | "limits"> => {
  const citationById = new Map(citations.map((item) => [item.id, item]));
  const rejectedClaims: RejectedClaim[] = [];
  const evidenceMemo = (modelMemo.evidenceMemo ?? []).flatMap((item): MemoBullet[] => {
    if (item === null || typeof item !== "object" || Array.isArray(item)) return [];
    const record = item as Record<string, unknown>;
    const text = asString(record["text"]);
    if (text === null) return [];
    const citationIds = filterCitationIds(asStringArray(record["citationIds"]), citationById);
    if (citationIds.length === 0) {
      rejectedClaims.push({ claim: text, reason: "No valid dossier citation id was supplied." });
      return [];
    }
    return [{ text, citationIds }];
  });

  const riskRecord = modelMemo.riskRating !== null && typeof modelMemo.riskRating === "object" && !Array.isArray(modelMemo.riskRating)
    ? modelMemo.riskRating as Record<string, unknown>
    : {};
  const modelRiskCitationIds = filterCitationIds(asStringArray(riskRecord["citationIds"]), citationById);
  const fallbackRisk = buildFallbackRiskRating(dossier, citationById);
  const riskRating: MemoRiskRating = {
    citationIds: modelRiskCitationIds.length === 0 ? fallbackRisk.citationIds : modelRiskCitationIds,
    confidenceBlockers: asStringArray(riskRecord["confidenceBlockers"]).length === 0
      ? fallbackRisk.confidenceBlockers
      : asStringArray(riskRecord["confidenceBlockers"]),
    level: isRiskLevel(riskRecord["level"]) ? riskRecord["level"] : fallbackRisk.level,
    rationale: asString(riskRecord["rationale"]) ?? fallbackRisk.rationale,
  };

  const decisionRecord = modelMemo.decisionAid !== null && typeof modelMemo.decisionAid === "object" && !Array.isArray(modelMemo.decisionAid)
    ? modelMemo.decisionAid as Record<string, unknown>
    : {};
  const nextSteps = filterOperationalFollowUps(asStringArray(decisionRecord["nextSteps"]));
  const confidenceBlockers = asStringArray(decisionRecord["confidenceBlockers"]);
  const decisionAid: DecisionAid = {
    confidenceBlockers: confidenceBlockers.length === 0
      ? riskRating.confidenceBlockers
      : confidenceBlockers,
    nextSteps: nextSteps.length === 0
      ? fallbackDecisionNextSteps(dossier)
      : nextSteps,
    nonAdvisoryReminder: "Operational follow-up only; this is not legal, tax, credit, investment, or licensed-advisor advice.",
  };

  const usedCitationIds = new Set([
    ...evidenceMemo.flatMap((item) => item.citationIds),
    ...riskRating.citationIds,
  ]);
  const usedCitations = citations.filter((item) => usedCitationIds.has(item.id));
  const modelLimits = asStringArray(modelMemo.limits).map((message, index) => ({
    code: `AI_LIMIT_${index + 1}`,
    message,
  }));
  const limits = [...dossier.limits, ...modelLimits];

  return {
    citations: usedCitations.length === 0 ? citations.slice(0, 5) : usedCitations,
    decisionAid,
    evidenceMemo,
    limits,
    rejectedClaims,
    riskRating,
  };
};

const buildUnavailable = (
  config: Extract<ProviderConfig, { readonly configured: false }>,
  dossier: AnalystMemoDossier,
  generatedAt: string,
): AnalystMemoUnavailable => ({
  configured: false,
  gaps: dossier.gaps,
  generatedAt,
  limits: dossier.limits,
  model: config.model,
  provider: config.provider,
  reason: config.reason,
  status: "unavailable",
});

const buildProviderAuthUnavailable = (
  config: Extract<ProviderConfig, { readonly configured: true }>,
  dossier: AnalystMemoDossier,
  generatedAt: string,
): AnalystMemoUnavailable => ({
  configured: false,
  gaps: dossier.gaps,
  generatedAt,
  limits: dossier.limits,
  model: config.model,
  provider: config.provider,
  reason: {
    code: "AI_PROVIDER_AUTH_FAILED",
    message: `${config.provider} credentials were rejected by the provider. Check ${PROVIDER_KEY_ENV[config.provider]} on the REST gateway process.`,
  },
  status: "unavailable",
});

export const generateAnalystMemo = async (
  params: {
    readonly dossier: AnalystMemoDossier;
    readonly webPresence?: WebPresenceForMemo;
    readonly peopleDiscovery?: PeopleDiscoveryForMemo;
  },
  options: GenerateAnalystMemoOptions = {},
): Promise<AnalystMemoResponse> => {
  const generatedAt = (options.generatedAt ?? new Date()).toISOString();
  const config = resolveAiProviderConfig(options.env);
  if (!config.configured) {
    return buildUnavailable(config, params.dossier, generatedAt);
  }

  const citations = buildCitations(params.dossier, {
    ...(params.peopleDiscovery === undefined ? {} : { peopleDiscovery: params.peopleDiscovery }),
    ...(params.webPresence === undefined ? {} : { webPresence: params.webPresence }),
  });
  const prompt = buildPrompt(params.dossier, citations, params.webPresence, params.peopleDiscovery);
  let result: GenerateResult;
  try {
    result = await (options.generate ?? generateText)({
      maxTokens: 1200,
      prompt,
      responseFormat: "json_object",
      system: SYSTEM_PROMPT,
      temperature: 0.1,
    }, config);
  } catch (error) {
    if (error instanceof ProviderRequestError && (error.status === 401 || error.status === 403)) {
      return buildProviderAuthUnavailable(config, params.dossier, generatedAt);
    }

    return {
      configured: true,
      gaps: params.dossier.gaps,
      generatedAt,
      limits: params.dossier.limits,
      model: config.model,
      provider: config.provider,
      reason: {
        code: "AI_PROVIDER_FAILED",
        message: error instanceof Error ? error.message : "AI provider request failed.",
      },
      status: "error",
    };
  }

  const modelMemo = parseJsonObject(result.text);
  if (modelMemo === null) {
    return {
      configured: true,
      gaps: params.dossier.gaps,
      generatedAt,
      limits: params.dossier.limits,
      model: result.model,
      provider: result.provider,
      reason: {
        code: "AI_OUTPUT_INVALID",
        message: "AI provider returned output that was not valid memo JSON.",
      },
      status: "error",
    };
  }

  const grounded = groundModelMemo(modelMemo, params.dossier, citations);
  return {
    configured: true,
    gaps: params.dossier.gaps,
    generatedAt,
    model: result.model,
    provider: result.provider,
    status: "ready",
    ...grounded,
  };
};
