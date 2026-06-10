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
  readonly severity?: "high" | "medium" | "low";
  readonly category?: string;
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

export type ShieldMode = "observe" | "enforce" | "kiasu";
export type ShieldDecision = "allow" | "warn" | "deny";
export type ShieldRiskLevel = "low" | "medium" | "high" | "critical";

export type ShieldToolMetadata = {
  readonly toolName: string;
  readonly source: string;
  readonly riskLevel: ShieldRiskLevel;
  readonly readOnly: boolean;
  readonly openWorld: boolean;
  readonly authRequired: boolean;
  readonly tags: readonly string[];
};

export type ShieldPolicyDecision = {
  readonly mode: ShieldMode;
  readonly decision: ShieldDecision;
  readonly toolName: string;
  readonly riskLevel: ShieldRiskLevel;
  readonly reasonCodes: readonly string[];
  readonly message: string;
};

export type ShieldAuditStatus = "success" | "error" | "denied";

export type ShieldReplayMetadata = {
  readonly auditId: string;
  readonly toolName: string;
  readonly sanitizedInput: unknown;
  readonly decision: ShieldPolicyDecision;
  readonly status: ShieldAuditStatus;
  readonly outputHash: string | null;
  readonly rawOutputHash: string | null;
  readonly runtimeFindings: readonly ShieldRuntimeFinding[];
  readonly durationMs: number;
};

export type ShieldAuditRecord = {
  readonly auditId: string;
  readonly traceId?: string;
  readonly requestId?: string;
  readonly toolName: string;
  readonly decision: ShieldPolicyDecision;
  readonly status: ShieldAuditStatus;
  readonly startedAt: string;
  readonly finishedAt: string;
  readonly durationMs: number;
  readonly inputHash: string;
  readonly outputHash: string | null;
  readonly rawOutputHash: string | null;
  readonly runtimeFindings: readonly ShieldRuntimeFinding[];
  readonly sanitizedInput: unknown;
  readonly error?: ToolErrorPayload;
};

export type ShieldScannerFinding = {
  readonly toolName: string;
  readonly severity: ShieldRiskLevel;
  readonly code: string;
  readonly message: string;
  readonly evidence: string;
};

export type ShieldRuntimeFinding = {
  readonly severity: ShieldRiskLevel;
  readonly code: string;
  readonly message: string;
  readonly path: string;
  readonly action: "redacted" | "neutralized" | "blocked";
  readonly evidence: string;
};

export type PulseSignalCategory = "mobility" | "weather" | "source_health";
export type PulseSignalSeverity = "info" | "watch" | "disrupted" | "critical";
export type PulseFreshnessStatus = "fresh" | "stale" | "unknown";

export type PulseFreshness = {
  readonly observedAt: string;
  readonly upstreamTimestamp: string | null;
  readonly maxAgeSeconds: number;
  readonly status: PulseFreshnessStatus;
  readonly ageSeconds: number | null;
};

export type PulseProvenanceItem = {
  readonly source: string;
  readonly sourceTool: string;
  readonly observedAt: string;
  readonly upstreamTimestamp: string | null;
  readonly recordCount: number;
  readonly sourceUrl?: string;
  readonly license?: string;
};

export type PulseSignal = {
  readonly id: string;
  readonly category: PulseSignalCategory;
  readonly severity: PulseSignalSeverity;
  readonly title: string;
  readonly description: string;
  readonly source: string;
  readonly sourceTool: string;
  readonly observedAt: string;
  readonly upstreamTimestamp: string | null;
  readonly location?: LatLng;
  readonly area?: string;
  readonly provenance: readonly PulseProvenanceItem[];
  readonly freshness: PulseFreshness;
  readonly gaps: readonly EvidenceGap[];
  readonly recommendedAction: string;
  readonly raw?: Readonly<Record<string, unknown>>;
};

export type PulseSourceHealth = {
  readonly source: string;
  readonly sourceTool: string;
  readonly status: "ready" | "stale" | "gap";
  readonly observedAt: string;
  readonly recordCount: number;
  readonly freshness: PulseFreshness;
  readonly gaps: readonly EvidenceGap[];
  readonly provenance: readonly PulseProvenanceItem[];
};

export type PulseSnapshot = {
  readonly generatedAt: string;
  readonly focus: string | null;
  readonly signals: readonly PulseSignal[];
  readonly sourceHealth: readonly PulseSourceHealth[];
  readonly gaps: readonly EvidenceGap[];
  readonly shieldAuditId?: string;
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
  readonly sourceUrl?: string;
  readonly evidenceType?: "official_registry" | "web_discovery" | "operational_metadata";
};

export type BriefFreshnessItem = {
  readonly source: string;
  readonly observedAt: string;
  readonly upstreamTimestamp: string | null;
};

export type SourceCoverageStatus =
  | "checked"
  | "skipped"
  | "unavailable"
  | "credential_blocked"
  | "not_applicable";

export type SourceCoverageLevel = "full" | "partial" | "none";

export type SourceCoverageItem = {
  readonly family: string;
  readonly label: string;
  readonly tools: readonly string[];
  readonly status: SourceCoverageStatus;
  readonly coverageLevel: SourceCoverageLevel;
  readonly recordCount: number;
  readonly authRequired: boolean;
  readonly reason: string;
  readonly checkedAt?: string | null;
  readonly sourceFreshness?: string | null;
  readonly requiredCredentials?: readonly string[];
  readonly gapCodes?: readonly string[];
  readonly evidenceType?: "official_registry" | "web_discovery" | "operational_metadata";
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

export type AnalystFollowUpPriority = "critical" | "recommended" | "optional";

export type AnalystFollowUpReasonCategory =
  | "identity_confidence"
  | "source_unavailable"
  | "sector_gap"
  | "supplemental_review"
  | "credential_required"
  | "manual_confirmation"
  | "report_quality";

export type AnalystFollowUpEvidenceBasis = {
  readonly kind: "source_gap" | "confidence_blocker" | "skipped_module" | "evidence_limitation";
  readonly ref: string;
  readonly detail: string;
  readonly source?: string | null;
};

export type AnalystFollowUp = {
  readonly id: string;
  readonly priority: AnalystFollowUpPriority;
  readonly category: AnalystFollowUpReasonCategory;
  readonly action: string;
  readonly reason: string;
  readonly whyThisMatters: string;
  readonly evidenceBasis: readonly AnalystFollowUpEvidenceBasis[];
  readonly tool?: string;
  readonly input?: Readonly<Record<string, unknown>>;
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
  readonly sourceCoverage?: readonly SourceCoverageItem[];
  readonly riskFlags?: readonly RiskFlag[];
  readonly matchConfidence?: readonly MatchConfidence[];
  readonly analystFollowUps?: readonly AnalystFollowUp[];
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
