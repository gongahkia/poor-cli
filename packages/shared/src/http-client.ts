import { ApiError } from "./errors.js";
import { CircuitBreaker } from "./circuit-breaker.js";
import { getRateLimiter } from "./rate-limiter.js";
import { createLogger } from "./logger.js";
import { getTimeout } from "./config/index.js";
import { HARD_CAP_TIMEOUT } from "./config/timeouts.js";

const logger = createLogger("http-client");

const breakers = new Map<string, CircuitBreaker>();
const getBreaker = (apiName: string): CircuitBreaker => {
  let breaker = breakers.get(apiName);
  if (breaker === undefined) {
    breaker = new CircuitBreaker(apiName);
    breakers.set(apiName, breaker);
  }
  return breaker;
};
export const resetCircuitBreakers = (): void => { breakers.clear(); };

export type HttpOptions = {
  readonly headers?: Readonly<Record<string, string>>;
  readonly timeout?: number;
  readonly retries?: number;
  readonly apiName: string;
};

const BASE_DELAY = 1000; // WHY: 1s base avoids hammering a recovering API
const MAX_DELAY = 15000; // WHY: 15s cap prevents unreasonable waits
const MAX_JITTER = 500; // WHY: 500ms jitter window spreads retries
const DEFAULT_RETRIES = 3; // WHY: covers transient failures without excessive delay

const RETRYABLE_STATUSES = new Set([429, 500, 502, 503, 504]);

const parseErrorPayload = (
  body: string,
): { readonly message?: string; readonly code?: string; readonly details?: unknown } => {
  if (body.trim() === "") {
    return {};
  }

  try {
    const parsed = JSON.parse(body) as Record<string, unknown>;
    const message =
      typeof parsed["errorMsg"] === "string"
        ? parsed["errorMsg"]
        : typeof parsed["message"] === "string"
          ? parsed["message"]
          : typeof parsed["error"] === "string"
            ? parsed["error"]
            : undefined;
    const code = typeof parsed["name"] === "string" ? parsed["name"] : undefined;
    return {
      ...(message === undefined ? {} : { message }),
      ...(code === undefined ? {} : { code }),
      details: parsed,
    };
  } catch {
    return { details: body };
  }
};

const suggestedActionForStatus = (status: number): string | undefined => {
  if (status === 401 || status === 403) {
    return "Check the required credentials or API key configuration, then retry.";
  }
  if (status === 404) {
    return "Check the requested endpoint or identifier and retry with a supported value.";
  }
  if (status === 429) {
    return "Wait for the upstream rate limit window to reset, then retry.";
  }
  if (status >= 500) {
    return "Retry later. The upstream service appears to be unavailable.";
  }
  return undefined;
};

const httpGetWithReader = async <T>(
  url: string,
  options: HttpOptions,
  readBody: (response: Response) => Promise<T>,
): Promise<T> => {
  const breaker = getBreaker(options.apiName);
  return breaker.execute(async () => {
    const retries = options.retries ?? DEFAULT_RETRIES;
    const apiTimeout = options.timeout ?? getTimeout(options.apiName);
    const timeout = Math.min(apiTimeout, HARD_CAP_TIMEOUT);

    await getRateLimiter(options.apiName).acquire();

    for (let attempt = 0; attempt <= retries; attempt++) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeout);
      const startedAt = Date.now();

      try {
        logger.debug("request", { url, attempt, apiName: options.apiName });

        const fetchInit: RequestInit = { signal: controller.signal };
        if (options.headers !== undefined) {
          fetchInit.headers = options.headers as Record<string, string>;
        }
        const response = await fetch(url, fetchInit);

        clearTimeout(timer);

        if (response.ok) {
          logger.debug("response", {
            url,
            apiName: options.apiName,
            attempt,
            status: response.status,
            latencyMs: Date.now() - startedAt,
          });
          return await readBody(response);
        }

        if (RETRYABLE_STATUSES.has(response.status) && attempt < retries) {
          const retryAfter = response.headers.get("Retry-After");
          let waitMs: number;

          if (retryAfter !== null) {
            waitMs = parseInt(retryAfter, 10) * 1000;
          } else {
            const jitter = Math.random() * MAX_JITTER;
            waitMs = Math.min(BASE_DELAY * Math.pow(2, attempt) + jitter, MAX_DELAY);
          }

          logger.warn("retrying", { url, status: response.status, waitMs, attempt });
          await new Promise<void>((resolve) => setTimeout(resolve, waitMs));
          await getRateLimiter(options.apiName).acquire();
          continue;
        }

        const body = await response.text();
        const parsedError = parseErrorPayload(body);
        logger.error("request failed", {
          url,
          apiName: options.apiName,
          attempt,
          status: response.status,
          latencyMs: Date.now() - startedAt,
          code: parsedError.code ?? `HTTP_${response.status}`,
        });
        throw new ApiError({
          apiName: options.apiName,
          source: options.apiName,
          statusCode: response.status,
          code: parsedError.code ?? `HTTP_${response.status}`,
          message: parsedError.message ?? `${options.apiName} request failed: ${response.statusText}`,
          retryable: RETRYABLE_STATUSES.has(response.status),
          ...(suggestedActionForStatus(response.status) === undefined
            ? {}
            : { suggestedAction: suggestedActionForStatus(response.status)! }),
          details: parsedError.details ?? body,
        });
      } catch (error) {
        clearTimeout(timer);

        if (error instanceof ApiError) {
          throw error;
        }

        if (error instanceof DOMException && error.name === "AbortError") {
          if (attempt < retries) {
            logger.warn("timeout, retrying", { url, timeout, attempt });
            continue;
          }
          throw new ApiError({
            apiName: options.apiName,
            source: options.apiName,
            statusCode: 408,
            code: "TIMEOUT",
            message: `${options.apiName} request timed out after ${timeout}ms`,
            retryable: true,
            suggestedAction: "Retry later or increase the configured timeout for this API.",
          });
        }

        if (attempt < retries) {
          logger.warn("network error, retrying", {
            url,
            apiName: options.apiName,
            attempt,
            error,
          });
          const jitter = Math.random() * MAX_JITTER;
          const waitMs = Math.min(BASE_DELAY * Math.pow(2, attempt) + jitter, MAX_DELAY);
          await new Promise<void>((resolve) => setTimeout(resolve, waitMs));
          continue;
        }

        logger.error("network error, giving up", {
          url,
          apiName: options.apiName,
          attempt,
          error,
        });
        throw new ApiError({
          apiName: options.apiName,
          source: options.apiName,
          statusCode: 0,
          code: "NETWORK_ERROR",
          message: `${options.apiName} request failed: ${error instanceof Error ? error.message : String(error)}`,
          retryable: true,
          suggestedAction: "Check network connectivity or the upstream service status, then retry.",
        });
      }
    }

    throw new ApiError({
      apiName: options.apiName,
      source: options.apiName,
      statusCode: 0,
      code: "RETRY_EXHAUSTED",
      message: `${options.apiName} request failed after ${retries} retries`,
      retryable: true,
      suggestedAction: "Retry later. The upstream service did not recover within the retry budget.",
    });
  });
};

export const httpGet = async <T>(url: string, options: HttpOptions): Promise<T> =>
  httpGetWithReader(url, options, async (response) => (await response.json()) as T);

export const httpGetText = async (url: string, options: HttpOptions): Promise<string> =>
  httpGetWithReader(url, options, async (response) => response.text());

export const httpGetBuffer = async (url: string, options: HttpOptions): Promise<Buffer> =>
  httpGetWithReader(url, options, async (response) => Buffer.from(await response.arrayBuffer()));
