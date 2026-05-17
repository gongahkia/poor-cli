const DEFAULT_REST_GATEWAY_URL = import.meta.env.PROD ? "" : "http://localhost:3000";

type ErrorPayload = {
  error?: unknown;
  message?: unknown;
};

type ToolResponse<T> = {
  content?: unknown;
  data?: {
    record?: T;
  };
};

type CallToolOptions = {
  signal?: AbortSignal;
};

export type GatewayHealth = {
  status: "ok" | "degraded" | string;
  readiness?: "ready" | "degraded" | "failing" | string;
  tools: number;
  runtime?: {
    startedAt?: string;
    uptimeSeconds?: number;
    observedAt?: string;
  };
  services?: {
    gateway?: GatewayServiceReadiness;
    datagovDatastore?: GatewayServiceReadiness;
    acraLookup?: GatewayServiceReadiness;
    tinyfish?: {
      status?: "ready" | "unconfigured" | "failing" | string;
      configured: boolean;
      mode: string;
    } & GatewayServiceReadiness;
  };
};

export type GatewayServiceReadiness = {
  status?: "ready" | "unconfigured" | "failing" | string;
  message?: string;
  observedAt?: string;
  latencyMs?: number;
  configured?: boolean;
  errorCode?: string;
  retryable?: boolean;
  details?: Record<string, string | number | boolean>;
};

export type ApiSearchSuggestion = {
  id: string;
  label: string;
  description: string;
  uen: string;
  entityName: string;
  status: string;
  entityTypeDescription: string;
};

export type WebPresenceResult = {
  title: string;
  snippet: string;
  url: string;
  siteName: string | null;
  position: number;
};

export type WebPresence = {
  query: string;
  configured: boolean;
  results: WebPresenceResult[];
  possibleOfficialWebsite: string | null;
  limits: string[];
};

export type BackendLogEntry = {
  ts: string;
  level: "debug" | "info" | "warn" | "error" | string;
  module: string;
  msg: string;
  [key: string]: unknown;
};

export type DebugLogsResponse = {
  enabled: boolean;
  observedAt: string;
  entries: BackendLogEntry[];
  totalEntries: number;
  maxEntries: number;
  logPath?: string;
  limits: string[];
};

const getGatewayBaseUrl = () => {
  const configuredUrl = import.meta.env.VITE_REST_GATEWAY_URL?.trim();
  return (configuredUrl || DEFAULT_REST_GATEWAY_URL).replace(/\/+$/, "");
};

const buildGatewayUrl = (path: string, params: Record<string, string> = {}): string => {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const baseUrl = getGatewayBaseUrl();
  const url = baseUrl === ""
    ? new URL(normalizedPath, window.location.origin)
    : new URL(`${baseUrl}${normalizedPath}`);

  for (const [key, value] of Object.entries(params)) {
    if (value.trim() !== "") {
      url.searchParams.set(key, value);
    }
  }

  return baseUrl === "" ? `${url.pathname}${url.search}` : url.toString();
};

const readJson = async <T>(response: Response): Promise<T> => {
  const body = await response.text();
  if (!body) {
    return undefined as T;
  }

  return JSON.parse(body) as T;
};

const getErrorPayloadMessage = (payload: ErrorPayload): string | null => {
  if (typeof payload.error === "string") {
    return payload.error;
  }
  if (
    payload.error !== null
    && typeof payload.error === "object"
    && "message" in payload.error
    && typeof payload.error.message === "string"
  ) {
    return payload.error.message;
  }
  if (typeof payload.message === "string") {
    return payload.message;
  }

  return null;
};

export async function callTool<T>(
  toolName: string,
  params: object,
  options: CallToolOptions = {},
): Promise<T> {
  const normalizedToolName = toolName.trim();
  if (!normalizedToolName) {
    throw new Error("Tool name is required.");
  }

  const response = await fetch(
    buildGatewayUrl(`/api/v1/${encodeURIComponent(normalizedToolName)}`),
    {
      body: JSON.stringify(params),
      headers: {
        "Content-Type": "application/json",
      },
      method: "POST",
      signal: options.signal,
    },
  );

  if (!response.ok) {
    const payload = await readJson<ErrorPayload>(response).catch(
      (): ErrorPayload => ({}),
    );
    const message = getErrorPayloadMessage(payload)
      ?? `REST gateway request failed with status ${response.status}.`;
    throw new Error(message);
  }

  const payload = await readJson<ToolResponse<T> | T>(response);
  if (
    payload !== null
    && typeof payload === "object"
    && "data" in payload
    && payload.data !== undefined
    && typeof payload.data === "object"
    && payload.data !== null
    && "record" in payload.data
  ) {
    return payload.data.record as T;
  }

  return payload as T;
}

export async function getGatewayJson<T>(
  path: string,
  params: Record<string, string> = {},
  options: CallToolOptions = {},
): Promise<T> {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = buildGatewayUrl(normalizedPath, params);

  const response = await fetch(url, {
    method: "GET",
    signal: options.signal,
  });

  if (!response.ok) {
    const payload = await readJson<ErrorPayload>(response).catch(
      (): ErrorPayload => ({}),
    );
    const message = getErrorPayloadMessage(payload)
      ?? `REST gateway request failed with status ${response.status}.`;
    throw new Error(message);
  }

  return readJson<T>(response);
}

export async function postGatewayJson<T>(
  path: string,
  body: object,
  options: CallToolOptions = {},
): Promise<T> {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const response = await fetch(buildGatewayUrl(normalizedPath), {
    body: JSON.stringify(body),
    headers: {
      "Content-Type": "application/json",
    },
    method: "POST",
    signal: options.signal,
  });

  if (!response.ok) {
    const payload = await readJson<ErrorPayload>(response).catch(
      (): ErrorPayload => ({}),
    );
    const message = getErrorPayloadMessage(payload)
      ?? `REST gateway request failed with status ${response.status}.`;
    throw new Error(message);
  }

  return readJson<T>(response);
}
