export type ApiResponse<T> = {
  readonly data: T;
  readonly source: string;
  readonly cached: boolean;
  readonly timestamp: string;
  readonly errors: readonly ApiErrorInfo[];
};

export type ApiErrorInfo = {
  readonly apiName: string;
  readonly statusCode: number;
  readonly message: string;
  readonly retryable: boolean;
};

export type ContextIds = {
  readonly traceId: string;
  readonly requestId: string;
};

export type ToolErrorPayload = {
  readonly source: string;
  readonly tool: string;
  readonly code: string;
  readonly retryable: boolean;
  readonly message: string;
  readonly suggestedAction?: string;
  readonly statusCode?: number;
  readonly details?: unknown;
  readonly contextIds?: ContextIds;
};

export type ToolResult = {
  readonly content: readonly ToolResultContent[];
  readonly isError?: boolean;
  readonly structuredContent?: Readonly<Record<string, unknown>>;
  readonly _meta?: Readonly<Record<string, unknown>>;
};

export type ToolResultContent =
  | ToolResultTextContent
  | ToolResultResourceLinkContent;

export type ToolResultTextContent = {
  readonly type: "text";
  readonly text: string;
};

export type ToolResultResourceLinkContent = {
  readonly type: "resource_link";
  readonly uri: string;
  readonly name: string;
  readonly title?: string;
  readonly description?: string;
  readonly mimeType?: string;
  readonly annotations?: {
    readonly audience?: ("assistant" | "user")[];
    readonly priority?: number;
    readonly lastModified?: string;
  };
  readonly icons?: {
    readonly src: string;
    readonly mimeType?: string;
    readonly sizes?: string[];
    readonly theme?: "light" | "dark";
  }[];
  readonly _meta?: Readonly<Record<string, unknown>>;
};

export type OutputFormat = "json" | "markdown" | "csv" | "geojson";
export type CredentialSource = "env" | "keystore" | "mixed" | "none" | "not_required";

export type LatLng = {
  readonly lat: number;
  readonly lng: number;
};

export type DateRange = {
  readonly start: string;
  readonly end: string;
};

export type GeoFeature = {
  readonly type: "Feature";
  readonly geometry: {
    readonly type: string;
    readonly coordinates: readonly number[] | readonly (readonly number[])[];
  };
  readonly properties: Readonly<Record<string, unknown>>;
};

export type CacheStats = {
  readonly entries: number;
  readonly hits: number;
  readonly misses: number;
  readonly sizeBytes: number;
};

export type KeyInfo = {
  readonly apiName: string;
  readonly maskedKey: string;
  readonly addedAt: number;
  readonly lastUsed: number | null;
};

export type HealthStatus = {
  readonly api: string;
  readonly authRequired: boolean;
  readonly configured: boolean;
  readonly credentialSource: CredentialSource;
  readonly reachable: boolean;
  readonly latencyMs: number;
  readonly classification?: "live_public" | "live_authenticated" | "shared_datagov_datastore" | "shared_file_download";
  readonly probeMode?: "runtime_client";
  readonly productionUrl?: string;
  readonly representativeTool?: string;
  readonly releaseBlocking?: boolean;
  readonly dependentFamilies?: readonly string[];
  readonly coverageNotes?: readonly string[];
  readonly error?: string;
};

export type EvidenceGap = {
  readonly code: string;
  readonly message: string;
};

export type BriefLimit = {
  readonly code: string;
  readonly message: string;
};

export type BriefSummaryItem = {
  readonly label: string;
  readonly value: string | number | boolean | null;
  readonly source: string;
};

export type BriefProvenanceItem = {
  readonly source: string;
  readonly tool: string;
  readonly coverage: string;
  readonly authRequired: boolean;
  readonly recordCount: number;
};

export type BriefFreshnessItem = {
  readonly source: string;
  readonly observedAt: string;
  readonly upstreamTimestamp: string | null;
};

export type BriefArtifactRecord = Readonly<Record<string, unknown>>;

export type RiskFlag = {
  readonly code: string;
  readonly severity: "high" | "medium" | "low";
  readonly message: string;
  readonly source: string;
};

export type MatchConfidence = {
  readonly source: string;
  readonly confidence: "exact" | "name-exact" | "name-fuzzy" | "no-match";
  readonly matchedOn: string | null;
};

export type NextCheck = {
  readonly tool: string;
  readonly reason: string;
  readonly input: Readonly<Record<string, unknown>>;
};

export type BriefArtifact = {
  readonly title: string;
  readonly summary: readonly BriefSummaryItem[];
  readonly evidence: readonly BriefSummaryItem[];
  readonly records: Readonly<Record<string, unknown>>;
  readonly gaps: readonly EvidenceGap[];
  readonly provenance: readonly BriefProvenanceItem[];
  readonly freshness: readonly BriefFreshnessItem[];
  readonly limits: readonly BriefLimit[];
  readonly riskFlags?: readonly RiskFlag[];
  readonly matchConfidence?: readonly MatchConfidence[];
  readonly nextChecks?: readonly NextCheck[];
};

export type QueryBlocker = {
  readonly field: string;
  readonly reason: string;
  readonly directTool: string;
  readonly exampleInput: Readonly<Record<string, unknown>>;
  readonly suggestedPrompt: string;
};

export type QueryPlannedStep = {
  readonly id: string;
  readonly purpose: string;
  readonly tool: string;
  readonly input: Readonly<Record<string, unknown>>;
  readonly dependsOn?: readonly string[];
};

export type QueryExecutedStep = QueryPlannedStep & {
  readonly status: "completed" | "failed";
  readonly outputText?: string;
  readonly structuredOutput?: Readonly<Record<string, unknown>>;
  readonly error?: ToolErrorPayload;
};

export type QueryResultSummary = {
  readonly level: string;
  readonly headline: string;
};

export type QueryContextIds = ContextIds;

export type QueryPlannedResult = {
  readonly status: "planned";
  readonly mode: "plan";
  readonly workflow: string;
  readonly intent: string;
  readonly apis: readonly string[];
  readonly confidence: number;
  readonly toolsUsed: readonly string[];
  readonly steps: readonly QueryPlannedStep[];
  readonly contextIds?: QueryContextIds;
};

export type QueryCompletedResult = {
  readonly status: "completed";
  readonly mode: "execute";
  readonly workflow: string;
  readonly intent: string;
  readonly apis: readonly string[];
  readonly confidence: number;
  readonly toolsUsed: readonly string[];
  readonly steps: readonly QueryExecutedStep[];
  readonly routingExplanation: string;
  readonly continuationHints?: readonly string[];
  readonly resultSummary?: QueryResultSummary;
  readonly nextActions?: readonly NextCheck[];
  readonly contextIds?: QueryContextIds;
};

export type QueryBlockedResult = {
  readonly status: "blocked";
  readonly mode: "plan" | "execute";
  readonly workflow: string;
  readonly intent: string;
  readonly apis: readonly string[];
  readonly confidence: number;
  readonly toolsUsed: readonly string[];
  readonly steps: readonly QueryPlannedStep[];
  readonly blockers: readonly QueryBlocker[];
  readonly reason: string;
  readonly suggestion: string;
  readonly routingExplanation: string;
  readonly contextIds?: QueryContextIds;
};

export type QueryUnsupportedResult = {
  readonly status: "unsupported";
  readonly mode: "plan" | "execute";
  readonly reason: string;
  readonly suggestion: string;
  readonly workflow?: string;
  readonly intent?: string;
  readonly apis?: readonly string[];
  readonly confidence?: number;
  readonly toolsUsed?: readonly string[];
  readonly steps?: readonly QueryPlannedStep[];
  readonly contextIds?: QueryContextIds;
};

export type QueryFailedResult = {
  readonly status: "failed";
  readonly mode: "execute";
  readonly workflow: string;
  readonly intent: string;
  readonly apis: readonly string[];
  readonly confidence: number;
  readonly toolsUsed: readonly string[];
  readonly steps: readonly QueryExecutedStep[];
  readonly routingExplanation: string;
  readonly resultSummary?: QueryResultSummary;
  readonly nextActions?: readonly NextCheck[];
  readonly failedStep: QueryExecutedStep | null;
  readonly contextIds?: QueryContextIds;
};

export type QueryOutcome =
  | QueryPlannedResult
  | QueryCompletedResult
  | QueryBlockedResult
  | QueryUnsupportedResult
  | QueryFailedResult;

export type {
  CivicDirectoryRecord,
  EcdaChildcareCentreRecord,
  EcdaVacancyStatus,
  MsfFamilyServiceRecord,
  MsfSocialServiceOfficeRecord,
  MsfStudentCareServiceRecord,
  PaCommunityOutletRecord,
  PaResidentNetworkCentreRecord,
  SportSgFacilityRecord,
  SportSgFacilityType,
} from "./civic.js";
export type {
  BoaArchitectRecord,
  BoaArchitectureFirmRecord,
  BoaNormalizedArchitectRecord,
  BoaNormalizedArchitectureFirmRecord,
} from "./boa.js";
export type {
  HsaHealthProductLicenseeRecord,
  HsaLicensedPharmacyRecord,
  HsaNormalizedHealthProductLicenseeRecord,
  HsaNormalizedLicensedPharmacyRecord,
} from "./hsa.js";
export type {
  HlbHotelRecord,
} from "./hlb.js";
