import { Keystore, ApiError, createLogger } from "@swee-sg/shared";

const logger = createLogger("onemap-auth");

let cachedToken: { token: string; expiresAt: number } | null = null;
let keystoreInstance: Keystore | null = null;

const getKeystore = (): Keystore => {
  if (keystoreInstance === null) {
    keystoreInstance = new Keystore();
  }
  return keystoreInstance;
};

export const getToken = async (): Promise<string> => {
  if (cachedToken !== null && Date.now() < cachedToken.expiresAt) {
    return cachedToken.token;
  }

  const keystore = getKeystore();
  const email = process.env["SG_API_ONEMAP_EMAIL"] ?? keystore.getKey("onemap_email");
  const password = process.env["SG_API_ONEMAP_PASSWORD"] ?? keystore.getKey("onemap_password");

  if (email === null || password === null) {
    throw new ApiError({
      apiName: "onemap",
      source: "OneMap",
      statusCode: 401,
      code: "AUTH_MISSING",
      message: "OneMap credentials not configured. Run sg_key_set.",
      retryable: false,
      suggestedAction: "Set SG_API_ONEMAP_EMAIL and SG_API_ONEMAP_PASSWORD, or run sg_key_set for onemap_email/onemap_password.",
    });
  }

  const response = await fetch("https://www.onemap.gov.sg/api/auth/post/getToken", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  if (!response.ok) {
    throw new ApiError({
      apiName: "onemap",
      statusCode: response.status,
      message: "OneMap authentication failed",
      retryable: response.status >= 500,
    });
  }

  const body = await response.json() as { access_token: string; expiry_timestamp: string };
  const TOKEN_TTL = 259200; // WHY: OneMap token TTL is 3 days (259200 seconds)
  cachedToken = {
    token: body.access_token,
    expiresAt: Date.now() + TOKEN_TTL * 1000,
  };

  logger.info("OneMap token acquired");
  return cachedToken.token;
};

export const authenticatedFetch = async (url: string, options?: RequestInit): Promise<Response> => {
  const token = await getToken();
  const headers = { ...(options?.headers as Record<string, string> ?? {}), Authorization: token };

  let response = await fetch(url, { ...options, headers });

  if (response.status === 401) {
    cachedToken = null;
    const newToken = await getToken();
    headers.Authorization = newToken;
    response = await fetch(url, { ...options, headers });
  }

  return response;
};
