const DEFAULT_REST_GATEWAY_URL = "http://localhost:3000";

type ErrorPayload = {
  error?: unknown;
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
  status: "ok" | string;
  tools: number;
  services?: {
    gateway?: string;
    acra?: string;
    tinyfish?: {
      configured: boolean;
      mode: string;
    };
  };
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

const getGatewayBaseUrl = () => {
  const configuredUrl = import.meta.env.VITE_REST_GATEWAY_URL?.trim();
  return (configuredUrl || DEFAULT_REST_GATEWAY_URL).replace(/\/+$/, "");
};

const readJson = async <T>(response: Response): Promise<T> => {
  const body = await response.text();
  if (!body) {
    return undefined as T;
  }

  return JSON.parse(body) as T;
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
    `${getGatewayBaseUrl()}/api/v1/${encodeURIComponent(normalizedToolName)}`,
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
    const message =
      typeof payload.error === "string"
        ? payload.error
        : `REST gateway request failed with status ${response.status}.`;
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
  const url = new URL(`${getGatewayBaseUrl()}${normalizedPath}`);
  for (const [key, value] of Object.entries(params)) {
    if (value.trim() !== "") {
      url.searchParams.set(key, value);
    }
  }

  const response = await fetch(url.toString(), {
    method: "GET",
    signal: options.signal,
  });

  if (!response.ok) {
    const payload = await readJson<ErrorPayload>(response).catch(
      (): ErrorPayload => ({}),
    );
    const message =
      typeof payload.error === "string"
        ? payload.error
        : `REST gateway request failed with status ${response.status}.`;
    throw new Error(message);
  }

  return readJson<T>(response);
}
