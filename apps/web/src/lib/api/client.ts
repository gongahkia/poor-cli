const DEFAULT_REST_GATEWAY_URL = "http://localhost:3000";

type ErrorPayload = {
  error?: unknown;
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

export async function callTool<T>(toolName: string, params: object): Promise<T> {
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

  return readJson<T>(response);
}
