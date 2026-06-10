import type { AiProvider, GenerateResult } from "../ai/providers.js";
import { generateText, ProviderRequestError, resolveAiProviderConfig, type ProviderConfig } from "../ai/providers.js";
import type { AnalystMemoDossier } from "./analyst-memo.js";

export const SUMMARY_TARGET_IDS = [
  "overview.summary",
  "overview.snapshot",
  "overview.risk",
  "overview.memo",
  "overview.confidence",
  "evidence.metrics",
  "evidence.searched",
  "evidence.notSearched",
  "evidence.records",
  "evidence.webPresence",
  "evidence.peopleDiscovery",
  "actions.pdpa",
  "actions.nextChecks",
  "audit.handoff",
  "audit.gaps",
  "audit.provenance",
] as const;

export type SummaryTargetId = (typeof SUMMARY_TARGET_IDS)[number];

type SummarySegment = {
  readonly text: string;
  readonly emphasized: boolean;
  readonly targetId: SummaryTargetId;
};

type SummaryReason = {
  readonly code: string;
  readonly message: string;
};

type InteractiveSummaryPrompt = {
  readonly system: string;
  readonly user: string;
  readonly copyText: string;
};

export type InteractiveSummaryReady = {
  readonly status: "ready";
  readonly configured: true;
  readonly provider: AiProvider;
  readonly model: string;
  readonly generatedAt: string;
  readonly prompt: InteractiveSummaryPrompt;
  readonly sentence: string;
  readonly segments: readonly SummarySegment[];
  readonly gaps: AnalystMemoDossier["gaps"];
  readonly limits: AnalystMemoDossier["limits"];
};

export type InteractiveSummaryUnavailable = {
  readonly status: "unavailable";
  readonly configured: false;
  readonly provider: AiProvider;
  readonly model: string;
  readonly generatedAt: string;
  readonly prompt: InteractiveSummaryPrompt;
  readonly reason: SummaryReason;
  readonly gaps: AnalystMemoDossier["gaps"];
  readonly limits: AnalystMemoDossier["limits"];
};

export type InteractiveSummaryError = {
  readonly status: "error";
  readonly configured: true;
  readonly provider: AiProvider;
  readonly model: string;
  readonly generatedAt: string;
  readonly prompt: InteractiveSummaryPrompt;
  readonly reason: SummaryReason;
  readonly gaps: AnalystMemoDossier["gaps"];
  readonly limits: AnalystMemoDossier["limits"];
};

export type InteractiveSummaryResponse =
  | InteractiveSummaryReady
  | InteractiveSummaryUnavailable
  | InteractiveSummaryError;

type ModelSummary = {
  readonly segments?: readonly unknown[];
};

type GenerateText = typeof generateText;

type GenerateInteractiveSummaryOptions = {
  readonly env?: NodeJS.ProcessEnv;
  readonly generatedAt?: Date;
  readonly generate?: GenerateText;
};

type WebPresenceForSummary = {
  readonly query?: string;
  readonly configured: boolean;
  readonly results?: readonly WebSearchResultForSummary[];
  readonly possibleOfficialWebsite?: string | null;
  readonly limits: readonly string[];
};

type PeopleDiscoveryForSummary = {
  readonly entityName: string;
  readonly uen?: string | null;
  readonly query: string;
  readonly configured: boolean;
  readonly results: readonly WebSearchResultForSummary[];
  readonly suggestedActions: readonly string[];
  readonly limits: readonly string[];
};

type WebSearchResultForSummary = {
  readonly title: string;
  readonly snippet: string;
  readonly url: string;
  readonly siteName: string | null;
  readonly position: number;
};

const TARGET_LABELS: Record<SummaryTargetId, string> = {
  "actions.nextChecks": "Actions / Next checks",
  "actions.pdpa": "Actions / PDPA checklist",
  "audit.gaps": "Missing / Evidence gaps",
  "audit.handoff": "Audit / Agent handoff",
  "audit.provenance": "Audit / Provenance and freshness",
  "evidence.metrics": "Evidence / Evidence metrics",
  "evidence.notSearched": "Evidence / Not searched modules",
  "evidence.peopleDiscovery": "Evidence / People discovery",
  "evidence.records": "Evidence / Matched records",
  "evidence.searched": "Evidence / Searched modules",
  "evidence.webPresence": "Evidence / Web presence",
  "overview.confidence": "Overview / Confidence",
  "overview.memo": "Overview / Analyst memo",
  "overview.risk": "Overview / Risk signals",
  "overview.snapshot": "Overview / Diligence snapshot",
  "overview.summary": "Overview / Registry summary",
};

const SYSTEM_PROMPT = [
  "You write one-sentence interactive summaries for a Singapore public-data counterparty dossier UI.",
  "Use only the provided dossier envelope. Do not add directors, shareholders, litigation, sanctions, credit, legal, tax, or advisory claims unless present.",
  "Build the sentence from every composite evidence pack present in the envelope: ACRA identity, selected official modules, supplemental diligence artifacts, web presence, people discovery, gaps, provenance, freshness, and limits.",
  "Treat sanctions, OpenCorporates, adverse-media, relationship graph, web presence, and people-discovery content as supplemental analyst-review evidence; unavailable providers are confidence blockers, not negative findings.",
  "Return strict JSON only. The rendered text must be exactly one sentence.",
  "Bold-worthy segments must point to one of the provided target ids so the UI can navigate to the supporting section.",
].join("\n");

const PROVIDER_KEY_ENV: Record<AiProvider, string> = {
  anthropic: "ANTHROPIC_API_KEY",
  google: "GOOGLE_API_KEY",
  openai: "OPENAI_API_KEY",
};

const summaryValue = (dossier: AnalystMemoDossier, label: string): string | null => {
  const value = dossier.summary.find((item) => item.label.toLowerCase() === label.toLowerCase())?.value;
  return typeof value === "string" && value.trim() !== "" ? value.trim() : null;
};

const SUMMARY_RECORD_KEYS = [
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

const buildSummaryRecordsInput = (records: Record<string, unknown>): Record<string, unknown> =>
  Object.fromEntries(
    SUMMARY_RECORD_KEYS
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
  SUMMARY_RECORD_KEYS.flatMap((key) => {
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

const asStringArray = (value: unknown): readonly string[] =>
  Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && item.trim() !== "")
    : [];

const externalDiligenceTitles = (dossier: AnalystMemoDossier): readonly string[] => {
  const externalDiligence = dossier.records["externalDiligence"];
  if (!Array.isArray(externalDiligence)) return [];
  return externalDiligence.flatMap((item): string[] => {
    if (item === null || typeof item !== "object" || Array.isArray(item)) return [];
    const title = (item as Record<string, unknown>)["title"];
    return typeof title === "string" && title.trim() !== "" ? [title.trim()] : [];
  });
};

const buildCompositeEvidencePacks = (
  dossier: AnalystMemoDossier,
  supplemental: Readonly<{
    peopleDiscovery?: PeopleDiscoveryForSummary;
    webPresence?: WebPresenceForSummary;
  }> = {},
) => {
  const resolution = dossier.records["resolution"] as Record<string, unknown> | undefined;
  return {
    officialModules: {
      matched: asStringArray(resolution?.["matchedModules"]),
      searched: asStringArray(resolution?.["searchedModules"]),
      selected: asStringArray(resolution?.["selectedModules"]),
      unsearched: asStringArray(resolution?.["unsearchedModules"]),
    },
    recordGroups: SUMMARY_RECORD_KEYS
      .filter((key) => dossier.records[key] !== undefined)
      .map((key) => ({
        key,
        count: Array.isArray(dossier.records[key]) ? dossier.records[key].length : 1,
      })),
    supplementalDiligence: externalDiligenceTitles(dossier),
    supplementalDiscovery: {
      peopleDiscovery: supplemental.peopleDiscovery === undefined ? null : {
        configured: supplemental.peopleDiscovery.configured,
        limits: supplemental.peopleDiscovery.limits,
        query: supplemental.peopleDiscovery.query,
        resultCount: supplemental.peopleDiscovery.results.length,
        suggestedActions: supplemental.peopleDiscovery.suggestedActions,
      },
      webPresence: supplemental.webPresence === undefined ? null : {
        configured: supplemental.webPresence.configured,
        limits: supplemental.webPresence.limits,
        possibleOfficialWebsite: supplemental.webPresence.possibleOfficialWebsite ?? null,
        query: supplemental.webPresence.query ?? null,
        resultCount: supplemental.webPresence.results?.length ?? 0,
      },
    },
  };
};

const buildWebPresencePromptInput = (webPresence: WebPresenceForSummary | undefined) => {
  if (webPresence === undefined) return undefined;
  return {
    configured: webPresence.configured,
    limits: webPresence.limits,
    possibleOfficialWebsite: webPresence.possibleOfficialWebsite ?? null,
    query: webPresence.query ?? null,
    results: (webPresence.results ?? []).slice(0, 5).map((result) => ({
      position: result.position,
      siteName: result.siteName,
      snippet: result.snippet,
      title: result.title,
      url: result.url,
    })),
  };
};

const buildPeopleDiscoveryPromptInput = (peopleDiscovery: PeopleDiscoveryForSummary | undefined) => {
  if (peopleDiscovery === undefined) return undefined;
  return {
    configured: peopleDiscovery.configured,
    entityName: peopleDiscovery.entityName,
    limits: peopleDiscovery.limits,
    query: peopleDiscovery.query,
    results: peopleDiscovery.results.slice(0, 5).map((result) => ({
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
  supplemental: Readonly<{
    peopleDiscovery?: PeopleDiscoveryForSummary;
    webPresence?: WebPresenceForSummary;
  }> = {},
): string => JSON.stringify({
  instructions: {
    outputSchema: {
      segments: [
        {
          emphasized: false,
          targetId: "overview.summary",
          text: "Plain sentence text, including spaces and punctuation where needed.",
        },
        {
          emphasized: true,
          targetId: "evidence.records",
          text: "Short evidence-backed phrase to render in bold.",
        },
      ],
    },
    rules: [
      "Return 6 to 12 segments whose text concatenates into exactly one sentence.",
      "Set emphasized=true only for 3 to 5 important phrases.",
      "Every emphasized segment must use the target id for the most relevant supporting subsection.",
      "The sentence must account for the available composite evidence packs, including supplemental diligence artifacts when present.",
      "Use audit.gaps only when dossier.gaps is non-empty; otherwise use audit.provenance for provenance, freshness, limits, or bounded coverage claims.",
      "Do not invent absent evidence. Say public-data coverage is limited when gaps or limits are important.",
    ],
    targetIds: SUMMARY_TARGET_IDS.map((id) => ({ id, label: TARGET_LABELS[id] })),
  },
  dossier: {
    evidence: dossier.evidence,
    freshness: dossier.freshness,
    gaps: dossier.gaps,
    limits: dossier.limits,
    nextChecks: dossier.nextChecks ?? [],
    provenance: dossier.provenance,
    compositeEvidencePacks: buildCompositeEvidencePacks(dossier, supplemental),
    recordDigests: buildRecordDigests(dossier.records),
    records: buildSummaryRecordsInput(dossier.records),
    riskFlags: dossier.riskFlags ?? [],
    summary: dossier.summary,
    title: dossier.title,
  },
  supplementalReview: {
    peopleDiscovery: buildPeopleDiscoveryPromptInput(supplemental.peopleDiscovery),
    webPresence: buildWebPresencePromptInput(supplemental.webPresence),
  },
});

const buildCopyablePrompt = (userPrompt: string): InteractiveSummaryPrompt => ({
  copyText: [
    "SYSTEM",
    SYSTEM_PROMPT,
    "",
    "USER",
    userPrompt,
  ].join("\n"),
  system: SYSTEM_PROMPT,
  user: userPrompt,
});

const parseJsonObject = (text: string): ModelSummary | null => {
  const trimmed = text.trim();
  const start = trimmed.indexOf("{");
  const end = trimmed.lastIndexOf("}");
  if (start === -1 || end === -1 || end <= start) {
    return null;
  }
  try {
    const parsed = JSON.parse(trimmed.slice(start, end + 1)) as unknown;
    return parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed as ModelSummary
      : null;
  } catch {
    return null;
  }
};

const targetIds = new Set<string>(SUMMARY_TARGET_IDS);

const isSummaryTargetId = (value: unknown): value is SummaryTargetId =>
  typeof value === "string" && targetIds.has(value);

const normalizeTargetId = (targetId: SummaryTargetId, dossier: AnalystMemoDossier): SummaryTargetId =>
  targetId === "audit.gaps" && dossier.gaps.length === 0 ? "audit.provenance" : targetId;

const asSegmentText = (value: unknown): string | null =>
  typeof value === "string" && value.trim() !== "" ? value : null;

const sentenceFromSegments = (segments: readonly SummarySegment[]): string =>
  segments.map((segment) => segment.text).join("").replace(/\s+/g, " ").trim();

const isOneSentence = (sentence: string): boolean => {
  const punctuation = sentence.match(/[.!?]/g) ?? [];
  return sentence.length > 0 && punctuation.length <= 1;
};

const buildFallbackSegments = (dossier: AnalystMemoDossier): readonly SummarySegment[] => {
  const entity = summaryValue(dossier, "Entity") ?? dossier.title;
  const status = summaryValue(dossier, "Entity status");
  const matchedModules = (dossier.records["resolution"] as { matchedModules?: unknown } | undefined)?.matchedModules;
  const matchedModuleText = Array.isArray(matchedModules) && matchedModules.length > 0
    ? matchedModules.filter((item): item is string => typeof item === "string").map((item) => item.toUpperCase()).join(", ")
    : "the returned public records";
  const riskText = (dossier.riskFlags ?? []).length > 0
    ? `${dossier.riskFlags?.length ?? 0} risk signal${(dossier.riskFlags?.length ?? 0) === 1 ? "" : "s"}`
    : "no returned risk flags";
  const gapText = dossier.gaps.length > 0
    ? `${dossier.gaps.length} evidence gap${dossier.gaps.length === 1 ? "" : "s"}`
    : "provenance and freshness notes";
  const supplementalTitles = externalDiligenceTitles(dossier);
  const supplementalText = supplementalTitles.length > 0
    ? supplementalTitles.map((title) => title.replace(/\s+/g, " ")).join(", ")
    : null;

  return [
    { emphasized: false, targetId: "overview.summary", text: "The dossier identifies " },
    { emphasized: true, targetId: "overview.summary", text: entity },
    ...(status === null ? [] : [
      { emphasized: false as const, targetId: "overview.summary" as const, text: " as " },
      { emphasized: true as const, targetId: "overview.snapshot" as const, text: status },
    ]),
    { emphasized: false, targetId: "evidence.records", text: " with " },
    { emphasized: true, targetId: "evidence.records", text: matchedModuleText },
    ...(supplementalText === null ? [] : [
      { emphasized: false as const, targetId: "audit.provenance" as const, text: " plus supplemental checks covering " },
      { emphasized: true as const, targetId: "audit.provenance" as const, text: supplementalText },
    ]),
    { emphasized: false, targetId: "overview.risk", text: ", " },
    { emphasized: true, targetId: "overview.risk", text: riskText },
    { emphasized: false, targetId: "audit.gaps", text: ", and " },
    { emphasized: true, targetId: dossier.gaps.length > 0 ? "audit.gaps" : "audit.provenance", text: gapText },
    { emphasized: false, targetId: "audit.provenance", text: "." },
  ];
};

const groundSegments = (
  modelSummary: ModelSummary,
  dossier: AnalystMemoDossier,
): readonly SummarySegment[] => {
  const segments = (modelSummary.segments ?? []).flatMap((item): SummarySegment[] => {
    if (item === null || typeof item !== "object" || Array.isArray(item)) return [];
    const record = item as Record<string, unknown>;
    const text = asSegmentText(record["text"]);
    if (text === null) return [];
    const targetId = normalizeTargetId(
      isSummaryTargetId(record["targetId"]) ? record["targetId"] : "overview.summary",
      dossier,
    );
    return [{
      emphasized: record["emphasized"] === true,
      targetId,
      text,
    }];
  });
  const hasEmphasis = segments.some((segment) => segment.emphasized);
  const sentence = sentenceFromSegments(segments);
  if (segments.length < 2 || !hasEmphasis || !isOneSentence(sentence)) {
    return buildFallbackSegments(dossier);
  }
  return segments;
};

const buildUnavailable = (
  config: Extract<ProviderConfig, { readonly configured: false }>,
  dossier: AnalystMemoDossier,
  generatedAt: string,
  prompt: InteractiveSummaryPrompt,
): InteractiveSummaryUnavailable => ({
  configured: false,
  gaps: dossier.gaps,
  generatedAt,
  limits: dossier.limits,
  model: config.model,
  prompt,
  provider: config.provider,
  reason: config.reason,
  status: "unavailable",
});

const buildProviderAuthUnavailable = (
  config: Extract<ProviderConfig, { readonly configured: true }>,
  dossier: AnalystMemoDossier,
  generatedAt: string,
  prompt: InteractiveSummaryPrompt,
): InteractiveSummaryUnavailable => ({
  configured: false,
  gaps: dossier.gaps,
  generatedAt,
  limits: dossier.limits,
  model: config.model,
  prompt,
  provider: config.provider,
  reason: {
    code: "AI_PROVIDER_AUTH_FAILED",
    message: `${config.provider} credentials were rejected by the provider. Check ${PROVIDER_KEY_ENV[config.provider]} on the REST gateway process.`,
  },
  status: "unavailable",
});

export const generateInteractiveSummary = async (
  params: {
    readonly dossier: AnalystMemoDossier;
    readonly peopleDiscovery?: PeopleDiscoveryForSummary;
    readonly webPresence?: WebPresenceForSummary;
  },
  options: GenerateInteractiveSummaryOptions = {},
): Promise<InteractiveSummaryResponse> => {
  const generatedAt = (options.generatedAt ?? new Date()).toISOString();
  const userPrompt = buildPrompt(params.dossier, {
    ...(params.peopleDiscovery === undefined ? {} : { peopleDiscovery: params.peopleDiscovery }),
    ...(params.webPresence === undefined ? {} : { webPresence: params.webPresence }),
  });
  const prompt = buildCopyablePrompt(userPrompt);
  const config = resolveAiProviderConfig(options.env);
  if (!config.configured) {
    return buildUnavailable(config, params.dossier, generatedAt, prompt);
  }

  let result: GenerateResult;
  try {
    result = await (options.generate ?? generateText)({
      maxTokens: 500,
      prompt: userPrompt,
      responseFormat: "json_object",
      system: SYSTEM_PROMPT,
      temperature: 0.1,
    }, config);
  } catch (error) {
    if (error instanceof ProviderRequestError && (error.status === 401 || error.status === 403)) {
      return buildProviderAuthUnavailable(config, params.dossier, generatedAt, prompt);
    }

    return {
      configured: true,
      gaps: params.dossier.gaps,
      generatedAt,
      limits: params.dossier.limits,
      model: config.model,
      prompt,
      provider: config.provider,
      reason: {
        code: "AI_PROVIDER_FAILED",
        message: error instanceof Error ? error.message : "AI provider request failed.",
      },
      status: "error",
    };
  }

  const modelSummary = parseJsonObject(result.text);
  if (modelSummary === null) {
    return {
      configured: true,
      gaps: params.dossier.gaps,
      generatedAt,
      limits: params.dossier.limits,
      model: result.model,
      prompt,
      provider: result.provider,
      reason: {
        code: "AI_OUTPUT_INVALID",
        message: "AI provider returned output that was not valid summary JSON.",
      },
      status: "error",
    };
  }

  const segments = groundSegments(modelSummary, params.dossier);
  return {
    configured: true,
    gaps: params.dossier.gaps,
    generatedAt,
    limits: params.dossier.limits,
    model: result.model,
    prompt,
    provider: result.provider,
    segments,
    sentence: sentenceFromSegments(segments),
    status: "ready",
  };
};
