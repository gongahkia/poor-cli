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

const buildPrompt = (dossier: AnalystMemoDossier): string => JSON.stringify({
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
    records: {
      quality: dossier.records["quality"],
      resolution: dossier.records["resolution"],
    },
    riskFlags: dossier.riskFlags ?? [],
    summary: dossier.summary,
    title: dossier.title,
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

  return [
    { emphasized: false, targetId: "overview.summary", text: "The dossier identifies " },
    { emphasized: true, targetId: "overview.summary", text: entity },
    ...(status === null ? [] : [
      { emphasized: false as const, targetId: "overview.summary" as const, text: " as " },
      { emphasized: true as const, targetId: "overview.snapshot" as const, text: status },
    ]),
    { emphasized: false, targetId: "evidence.records", text: " with " },
    { emphasized: true, targetId: "evidence.records", text: matchedModuleText },
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
  },
  options: GenerateInteractiveSummaryOptions = {},
): Promise<InteractiveSummaryResponse> => {
  const generatedAt = (options.generatedAt ?? new Date()).toISOString();
  const userPrompt = buildPrompt(params.dossier);
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
