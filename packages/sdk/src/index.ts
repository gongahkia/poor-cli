import { z } from "zod";
import type {
  PulseSignal,
  PulseSnapshot,
  PulseSourceHealth,
  ShieldAuditRecord,
  ShieldReplayMetadata,
  ShieldScannerFinding,
} from "@swee-sg/shared";
import type { GatewayHealth } from "./types.js";

export type {
  EvidenceGap,
  GatewayHealth,
  PulseFreshness,
  PulseFreshnessStatus,
  PulseProvenanceItem,
  PulseSignal,
  PulseSignalCategory,
  PulseSignalSeverity,
  PulseSnapshot,
  PulseSourceHealth,
  ShieldAuditRecord,
  ShieldAuditStatus,
  ShieldPolicyDecision,
  ShieldReplayMetadata,
  ShieldScannerFinding,
  ShieldRiskLevel,
  ToolErrorPayload,
} from "./types.js";

const PulseInputSchema = z.object({
  area: z.string().optional(),
  region: z.string().optional(),
  stationId: z.string().optional(),
  focus: z.enum(["mobility", "weather", "all"]).optional(),
});

const ShieldAuditLookupSchema = z.object({
  auditId: z.string().optional(),
  traceId: z.string().optional(),
  requestId: z.string().optional(),
  toolName: z.string().optional(),
  limit: z.number().int().min(1).max(100).optional(),
});

export type PulseInput = z.input<typeof PulseInputSchema>;
export type ShieldAuditLookupInput = z.input<typeof ShieldAuditLookupSchema>;

export type PulseSignalSet = {
  readonly signals: readonly PulseSignal[];
  readonly sourceHealth: readonly PulseSourceHealth[];
  readonly gaps: PulseSnapshot["gaps"];
};

export type PulseExplainResponse = {
  readonly snapshot: PulseSnapshot;
  readonly explanation: string;
  readonly aiUsed: boolean;
};

export type ShieldAuditLookupResponse = {
  readonly records?: readonly ShieldAuditRecord[];
  readonly record?: ShieldAuditRecord | null;
  readonly replay?: ShieldReplayMetadata | null;
};

export type ShieldScanResponse = {
  readonly findings: readonly ShieldScannerFinding[];
  readonly scannedTools: number;
};

export type SweeClientHeaders =
  | HeadersInit
  | (() => HeadersInit | Promise<HeadersInit>);

export type SweeClientOptions = {
  readonly baseUrl?: string;
  readonly fetch?: typeof fetch;
  readonly token?: string;
  readonly headers?: SweeClientHeaders;
  readonly timeoutMs?: number;
};

export type RequestOptions = {
  readonly signal?: AbortSignal;
  readonly headers?: HeadersInit;
  readonly timeoutMs?: number;
};

export type SweeToolSummary = {
  readonly name: string;
  readonly description?: string;
  readonly inputSchema?: unknown;
};

export type SweeGatewayToolEnvelope<T> = {
  readonly content?: unknown;
  readonly data?: T | {
    readonly record?: T;
    readonly records?: readonly T[];
  };
  readonly structuredContent?: unknown;
  readonly shield?: unknown;
  readonly _meta?: Readonly<Record<string, unknown>>;
};

export class SweeApiError extends Error {
  readonly status: number;
  readonly payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = "SweeApiError";
    this.status = status;
    this.payload = payload;
  }
}

const DEFAULT_BASE_URL = "http://localhost:3000";

const normalizeBaseUrl = (baseUrl: string | undefined): string => {
  const value = (baseUrl ?? DEFAULT_BASE_URL).trim();
  if (value === "") {
    throw new Error("SweeClient baseUrl cannot be empty.");
  }
  return value.replace(/\/+$/, "");
};

const resolveHeaders = async (
  headers: SweeClientHeaders | undefined,
): Promise<HeadersInit> => {
  if (headers === undefined) {
    return {};
  }
  if (typeof headers === "function") {
    return headers();
  }
  return headers;
};

const readJson = async <T>(response: Response): Promise<T> => {
  const body = await response.text();
  if (body.trim() === "") {
    return undefined as T;
  }
  return JSON.parse(body) as T;
};

const errorMessageFromPayload = (payload: unknown): string | null => {
  if (payload === null || typeof payload !== "object") {
    return null;
  }

  const record = payload as Record<string, unknown>;
  if (typeof record["message"] === "string") {
    return record["message"];
  }
  if (typeof record["error"] === "string") {
    return record["error"];
  }
  if (
    record["error"] !== null
    && typeof record["error"] === "object"
    && typeof (record["error"] as Record<string, unknown>)["message"] === "string"
  ) {
    return (record["error"] as Record<string, unknown>)["message"] as string;
  }

  return null;
};

const mergeSignals = (
  signal: AbortSignal | undefined,
  timeoutMs: number | undefined,
): { readonly signal: AbortSignal | undefined; readonly cleanup: () => void } => {
  if (timeoutMs === undefined) {
    return { signal, cleanup: () => undefined };
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const abort = () => controller.abort();
  signal?.addEventListener("abort", abort, { once: true });

  return {
    signal: controller.signal,
    cleanup: () => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
    },
  };
};

const unwrapToolEnvelope = <T>(payload: SweeGatewayToolEnvelope<T> | T): T => {
  if (
    payload !== null
    && typeof payload === "object"
    && "data" in payload
    && payload.data !== undefined
    && payload.data !== null
  ) {
    if (
      typeof payload.data === "object"
      && "record" in payload.data
      && payload.data.record !== undefined
    ) {
      return payload.data.record as T;
    }
    return payload.data as T;
  }

  return payload as T;
};

export class SweeClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private readonly token: string | undefined;
  private readonly headers: SweeClientHeaders | undefined;
  private readonly timeoutMs: number | undefined;

  constructor(options: SweeClientOptions = {}) {
    this.baseUrl = normalizeBaseUrl(options.baseUrl);
    this.fetchImpl = options.fetch ?? fetch;
    this.token = options.token;
    this.headers = options.headers;
    this.timeoutMs = options.timeoutMs;
  }

  async health(options: RequestOptions = {}): Promise<GatewayHealth> {
    return this.get<GatewayHealth>("/api/v1/health", options);
  }

  async listTools(options: RequestOptions = {}): Promise<readonly SweeToolSummary[]> {
    return this.get<readonly SweeToolSummary[]>("/api/v1/tools", options);
  }

  async callTool<T>(
    toolName: string,
    input: Readonly<Record<string, unknown>>,
    options: RequestOptions = {},
  ): Promise<T> {
    const normalizedToolName = toolName.trim();
    if (normalizedToolName === "") {
      throw new Error("Tool name is required.");
    }

    const payload = await this.post<SweeGatewayToolEnvelope<T> | T>(
      `/api/v1/${encodeURIComponent(normalizedToolName)}`,
      input,
      options,
    );
    return unwrapToolEnvelope<T>(payload);
  }

  async pulseSnapshot(input: PulseInput = {}, options: RequestOptions = {}): Promise<PulseSnapshot> {
    const parsed = PulseInputSchema.parse(input);
    const payload = await this.callTool<{ readonly snapshot: PulseSnapshot }>("swee_pulse_snapshot", parsed, options);
    return payload.snapshot;
  }

  async pulseMobility(options: RequestOptions = {}): Promise<PulseSignalSet> {
    return this.callTool<PulseSignalSet>("swee_pulse_mobility", {}, options);
  }

  async pulseWeather(input: PulseInput = {}, options: RequestOptions = {}): Promise<PulseSignalSet> {
    const parsed = PulseInputSchema.parse(input);
    return this.callTool<PulseSignalSet>("swee_pulse_weather", parsed, options);
  }

  async pulseExplain(input: PulseInput = {}, options: RequestOptions = {}): Promise<PulseExplainResponse> {
    const parsed = PulseInputSchema.parse(input);
    return this.callTool<PulseExplainResponse>("swee_pulse_explain", parsed, options);
  }

  async shieldAudits(input: ShieldAuditLookupInput = {}, options: RequestOptions = {}): Promise<ShieldAuditLookupResponse> {
    const parsed = ShieldAuditLookupSchema.parse(input);
    return this.callTool<ShieldAuditLookupResponse>("swee_shield_audit_lookup", parsed, options);
  }

  async shieldScan(options: RequestOptions = {}): Promise<ShieldScanResponse> {
    return this.callTool<ShieldScanResponse>("swee_shield_scan_tools", {}, options);
  }

  private async get<T>(path: string, options: RequestOptions): Promise<T> {
    return this.request<T>(path, { method: "GET" }, options);
  }

  private async post<T>(
    path: string,
    body: Readonly<Record<string, unknown>>,
    options: RequestOptions,
  ): Promise<T> {
    return this.request<T>(
      path,
      {
        body: JSON.stringify(body),
        headers: { "Content-Type": "application/json" },
        method: "POST",
      },
      options,
    );
  }

  private async request<T>(
    path: string,
    init: RequestInit,
    options: RequestOptions,
  ): Promise<T> {
    const url = new URL(path, `${this.baseUrl}/`).toString();
    const baseHeaders = await resolveHeaders(this.headers);
    const headers = new Headers(baseHeaders);

    if (this.token !== undefined && this.token.trim() !== "") {
      headers.set("Authorization", `Bearer ${this.token}`);
    }

    if (init.headers !== undefined) {
      const requestHeaders = new Headers(init.headers);
      requestHeaders.forEach((value, key) => headers.set(key, value));
    }

    if (options.headers !== undefined) {
      const requestHeaders = new Headers(options.headers);
      requestHeaders.forEach((value, key) => headers.set(key, value));
    }

    const { signal, cleanup } = mergeSignals(
      options.signal,
      options.timeoutMs ?? this.timeoutMs,
    );

    try {
      const requestInit: RequestInit = {
        ...init,
        headers,
      };
      if (signal !== undefined) {
        requestInit.signal = signal;
      }

      const response = await this.fetchImpl(url, requestInit);
      const payload = await readJson<T | unknown>(response);

      if (!response.ok) {
        const message =
          errorMessageFromPayload(payload)
          ?? `Swee SG gateway request failed with status ${response.status}.`;
        throw new SweeApiError(message, response.status, payload);
      }

      return payload as T;
    } finally {
      cleanup();
    }
  }
}

export const createSweeClient = (options: SweeClientOptions = {}): SweeClient =>
  new SweeClient(options);
