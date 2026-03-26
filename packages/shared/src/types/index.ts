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

export type ToolErrorPayload = {
  readonly source: string;
  readonly tool: string;
  readonly code: string;
  readonly retryable: boolean;
  readonly message: string;
  readonly suggestedAction?: string;
  readonly statusCode?: number;
  readonly details?: unknown;
};

export type ToolResult = {
  readonly content: readonly { readonly type: "text"; readonly text: string }[];
  readonly isError?: boolean;
  readonly structuredContent?: Readonly<Record<string, unknown>>;
};

export type OutputFormat = "json" | "markdown" | "csv" | "geojson";

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
  readonly reachable: boolean;
  readonly latencyMs: number;
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
  readonly confidence: "exact" | "name-fuzzy" | "no-match";
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

export type {
  CivicDirectoryRecord,
  EcdaChildcareCentreRecord,
  EcdaVacancyStatus,
  PaCommunityOutletRecord,
  PaResidentNetworkCentreRecord,
  SportSgFacilityRecord,
  SportSgFacilityType,
} from "./civic.js";
