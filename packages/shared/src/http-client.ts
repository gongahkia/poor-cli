import { ApiError } from "./errors.js";
import { getRateLimiter } from "./rate-limiter.js";
import { createLogger } from "./logger.js";
import { getTimeout } from "./config/index.js";
import { HARD_CAP_TIMEOUT } from "./config/timeouts.js";

const logger = createLogger("http-client");

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

export const httpGet = async <T>(url: string, options: HttpOptions): Promise<T> => {
  const retries = options.retries ?? DEFAULT_RETRIES;
  const apiTimeout = options.timeout ?? getTimeout(options.apiName);
  const timeout = Math.min(apiTimeout, HARD_CAP_TIMEOUT);

  await getRateLimiter(options.apiName).acquire();

  for (let attempt = 0; attempt <= retries; attempt++) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);

    try {
      logger.debug("request", { url, attempt, apiName: options.apiName });

      const fetchInit: RequestInit = { signal: controller.signal };
      if (options.headers !== undefined) {
        fetchInit.headers = options.headers as Record<string, string>;
      }
      const response = await fetch(url, fetchInit);

      clearTimeout(timer);

      if (response.ok) {
        return (await response.json()) as T;
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
      throw new ApiError({
        apiName: options.apiName,
        statusCode: response.status,
        message: `${options.apiName} request failed: ${response.statusText}`,
        retryable: RETRYABLE_STATUSES.has(response.status),
        details: body,
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
          statusCode: 408,
          message: `${options.apiName} request timed out after ${timeout}ms`,
          retryable: true,
        });
      }

      if (attempt < retries) {
        const jitter = Math.random() * MAX_JITTER;
        const waitMs = Math.min(BASE_DELAY * Math.pow(2, attempt) + jitter, MAX_DELAY);
        await new Promise<void>((resolve) => setTimeout(resolve, waitMs));
        continue;
      }

      throw new ApiError({
        apiName: options.apiName,
        statusCode: 0,
        message: `${options.apiName} request failed: ${error instanceof Error ? error.message : String(error)}`,
        retryable: true,
      });
    }
  }

  throw new ApiError({
    apiName: options.apiName,
    statusCode: 0,
    message: `${options.apiName} request failed after ${retries} retries`,
    retryable: true,
  });
};
