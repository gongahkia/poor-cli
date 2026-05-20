import {
  BusinessDossierSchema,
  QuerySchema,
} from "@dude/shared";
import type {
  BriefArtifact,
  GatewayHealth,
  QueryOutcome,
} from "./types.js";
import type { z } from "zod";

export type {
  BriefArtifact,
  BriefFreshnessItem,
  BriefLimit,
  BriefProvenanceItem,
  BriefSummaryItem,
  EvidenceGap,
  GatewayHealth,
  QueryOutcome,
  ToolErrorPayload,
} from "./types.js";

export type BusinessDossierInput = z.input<typeof BusinessDossierSchema>;
export type QueryInput = z.input<typeof QuerySchema>;

export type CddOrchestratorResponse = {
  readonly dossier: BriefArtifact;
  readonly generatedAt: string;
  readonly memo: unknown;
  readonly orchestration: unknown;
  readonly peopleDiscovery: unknown;
  readonly webPresence: unknown;
};

export type DudeClientHeaders =
  | HeadersInit
  | (() => HeadersInit | Promise<HeadersInit>);

export type DudeClientOptions = {
  readonly baseUrl?: string;
  readonly fetch?: typeof fetch;
  readonly token?: string;
  readonly headers?: DudeClientHeaders;
  readonly timeoutMs?: number;
};

export type RequestOptions = {
  readonly signal?: AbortSignal;
  readonly headers?: HeadersInit;
  readonly timeoutMs?: number;
};

export type DudeToolSummary = {
  readonly name: string;
  readonly description?: string;
  readonly inputSchema?: unknown;
};

export type DudeGatewayToolEnvelope<T> = {
  readonly content?: unknown;
  readonly data?: {
    readonly record?: T;
    readonly records?: readonly T[];
  };
  readonly structuredContent?: unknown;
  readonly _meta?: Readonly<Record<string, unknown>>;
};

export class DudeApiError extends Error {
  readonly status: number;
  readonly payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = "DudeApiError";
    this.status = status;
    this.payload = payload;
  }
}

const DEFAULT_BASE_URL = "http://localhost:3000";

const normalizeBaseUrl = (baseUrl: string | undefined): string => {
  const value = (baseUrl ?? DEFAULT_BASE_URL).trim();
  if (value === "") {
    throw new Error("DudeClient baseUrl cannot be empty.");
  }
  return value.replace(/\/+$/, "");
};

const resolveHeaders = async (
  headers: DudeClientHeaders | undefined,
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

const unwrapToolEnvelope = <T>(payload: DudeGatewayToolEnvelope<T> | T): T => {
  if (
    payload !== null
    && typeof payload === "object"
    && "data" in payload
    && payload.data !== undefined
    && payload.data !== null
    && typeof payload.data === "object"
    && "record" in payload.data
  ) {
    return payload.data.record as T;
  }

  return payload as T;
};

export class DudeClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private readonly token: string | undefined;
  private readonly headers: DudeClientHeaders | undefined;
  private readonly timeoutMs: number | undefined;

  constructor(options: DudeClientOptions = {}) {
    this.baseUrl = normalizeBaseUrl(options.baseUrl);
    this.fetchImpl = options.fetch ?? fetch;
    this.token = options.token;
    this.headers = options.headers;
    this.timeoutMs = options.timeoutMs;
  }

  async health(options: RequestOptions = {}): Promise<GatewayHealth> {
    return this.get<GatewayHealth>("/api/v1/health", options);
  }

  async listTools(options: RequestOptions = {}): Promise<readonly DudeToolSummary[]> {
    return this.get<readonly DudeToolSummary[]>("/api/v1/tools", options);
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

    const payload = await this.post<DudeGatewayToolEnvelope<T> | T>(
      `/api/v1/${encodeURIComponent(normalizedToolName)}`,
      input,
      options,
    );
    return unwrapToolEnvelope<T>(payload);
  }

  async businessDossier(
    input: BusinessDossierInput,
    options: RequestOptions = {},
  ): Promise<BriefArtifact> {
    const parsed = BusinessDossierSchema.parse(input);
    return this.callTool<BriefArtifact>("sg_business_dossier", parsed, options);
  }

  async cddReport(
    input: BusinessDossierInput,
    options: RequestOptions = {},
  ): Promise<CddOrchestratorResponse> {
    const parsed = BusinessDossierSchema.parse(input);
    return this.post<CddOrchestratorResponse>("/api/v1/dude/cdd-orchestrator", parsed, options);
  }

  async query(input: QueryInput, options: RequestOptions = {}): Promise<QueryOutcome> {
    const parsed = QuerySchema.parse(input);
    return this.callTool<QueryOutcome>("sg_query", parsed, options);
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
          ?? `Dude gateway request failed with status ${response.status}.`;
        throw new DudeApiError(message, response.status, payload);
      }

      return payload as T;
    } finally {
      cleanup();
    }
  }
}

export const createDudeClient = (options: DudeClientOptions = {}): DudeClient =>
  new DudeClient(options);
