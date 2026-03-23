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
