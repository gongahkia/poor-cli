import { httpGet, ApiError, Keystore, createLogger } from "@dude/shared";
import type { UraTransactionResponse, UraRawTransaction } from "@dude/shared";
import { withCache, buildCacheKey } from "../../middleware/cache-middleware.js";

const logger = createLogger("ura-client");

const BASE_URL = "https://www.ura.gov.sg/uraDataService";

let keystoreInstance: Keystore | null = null;
const getKeystore = (): Keystore => {
  if (keystoreInstance === null) keystoreInstance = new Keystore();
  return keystoreInstance;
};

let cachedDailyToken: { token: string; date: string } | null = null;

const getApiKey = (): string => {
  const envKey = process.env["SG_API_URA_KEY"];
  if (envKey !== undefined && envKey !== "") return envKey;
  const key = getKeystore().getKey("ura");
  if (key === null) {
    throw new ApiError({
      apiName: "ura",
      source: "URA",
      statusCode: 401,
      code: "AUTH_MISSING",
      message: "URA API key not configured. Run sg_key_set.",
      retryable: false,
      suggestedAction: "Set SG_API_URA_KEY, or run sg_key_set with apiName=ura.",
    });
  }
  return key;
};

const getTodayStr = (): string => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
};

export const getDailyToken = async (): Promise<string> => {
  const today = getTodayStr();
  if (cachedDailyToken !== null && cachedDailyToken.date === today) {
    return cachedDailyToken.token;
  }

  const apiKey = getApiKey();
  const response = await fetch(`${BASE_URL}/insertNewToken.action`, {
    headers: { AccessKey: apiKey },
  });

  if (!response.ok) {
    throw new ApiError({
      apiName: "ura",
      statusCode: response.status,
      message: "Failed to get URA daily token",
      retryable: response.status >= 500,
    });
  }

  const token = response.headers.get("Token");
  if (token === null) {
    const body = await response.json() as Record<string, unknown>;
    const bodyToken = body["Result"] as string | undefined;
    if (bodyToken === undefined) {
      throw new ApiError({
        apiName: "ura",
        statusCode: 500,
        message: "URA daily token not found in response",
        retryable: true,
      });
    }
    cachedDailyToken = { token: bodyToken, date: today };
    return bodyToken;
  }

  cachedDailyToken = { token, date: today };
  logger.info("URA daily token acquired");
  return token;
};

export const uraFetch = async <T>(
  service: string,
  params?: Readonly<Record<string, string>>,
): Promise<T> => {
  const apiKey = getApiKey();
  const token = await getDailyToken();

  let url = `${BASE_URL}/invokeUraDS?service=${encodeURIComponent(service)}`;
  if (params !== undefined) {
    for (const [key, value] of Object.entries(params)) {
      url += `&${key}=${encodeURIComponent(value)}`;
    }
  }

  const response = await httpGet<T>(url, {
    apiName: "ura",
    headers: { AccessKey: apiKey, Token: token },
  });
  return response;
};

export const getPropertyTransactions = async (
  propertyType?: string,
  area?: string,
  period?: string,
): Promise<UraRawTransaction[]> => {
  const serviceMap: Record<string, string> = {
    residential: "PMI_Resi_Transaction",
    commercial: "PMI_Comm_Transaction",
    industrial: "PMI_Ind_Transaction",
  };
  const service = serviceMap[propertyType ?? "residential"] ?? "PMI_Resi_Transaction";
  const cacheParams: Record<string, unknown> = { service };
  if (area !== undefined) cacheParams["area"] = area;
  if (period !== undefined) cacheParams["period"] = period;

  const cacheKey = buildCacheKey("ura", "transactions", cacheParams);
  const { data } = await withCache(cacheKey, "DAILY", async () => {
    const response = await uraFetch<UraTransactionResponse>(service);
    let results = [...response.Result];

    if (area !== undefined) {
      const lowerArea = area.toLowerCase();
      results = results.filter(
        (t) =>
          t.street.toLowerCase().includes(lowerArea) ||
          t.project.toLowerCase().includes(lowerArea),
      );
    }

    if (period !== undefined) {
      results = results.filter((t) => t.contractDate === period);
    }

    return results;
  });
  return data;
};
