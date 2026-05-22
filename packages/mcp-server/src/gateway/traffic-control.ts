import type { IncomingMessage } from "node:http";

export type TrafficPolicy = {
  readonly key: string;
  readonly label: string;
  readonly windowMs: number;
  readonly maxRequests: number;
  readonly maxBodyBytes: number;
};

export type TrafficLimitResult =
  | { readonly allowed: true; readonly remaining: number; readonly resetAt: number }
  | {
      readonly allowed: false;
      readonly remaining: 0;
      readonly resetAt: number;
      readonly retryAfterSeconds: number;
    };

export type TrafficLimitResponse = {
  readonly error: {
    readonly code: "RATE_LIMITED";
    readonly message: string;
    readonly limit: number;
    readonly windowSeconds: number;
    readonly retryAfterSeconds: number;
  };
};

type Bucket = {
  count: number;
  resetAt: number;
};

const KiB = 1024;

export const DEFAULT_TRAFFIC_POLICY: TrafficPolicy = {
  key: "public_default",
  label: "public API requests",
  windowMs: 60_000,
  maxRequests: 120,
  maxBodyBytes: 64 * KiB,
};

const PULSE_POLICY: TrafficPolicy = {
  key: "pulse",
  label: "Pulse signal",
  windowMs: 60_000,
  maxRequests: 90,
  maxBodyBytes: 16 * KiB,
};

const SHIELD_POLICY: TrafficPolicy = {
  key: "shield",
  label: "Shield audit",
  windowMs: 60_000,
  maxRequests: 120,
  maxBodyBytes: 16 * KiB,
};

const buckets = new Map<string, Bucket>();

const bucketKey = (clientId: string, policy: TrafficPolicy): string => `${clientId}\u0000${policy.key}`;

const normalizeForwardedAddress = (value: string | undefined): string | undefined => {
  const address = value?.split(",")[0]?.trim();
  return address === "" ? undefined : address;
};

export const getClientId = (req: IncomingMessage): string => {
  const forwardedFor = req.headers["x-forwarded-for"];
  const realIp = req.headers["x-real-ip"];
  if (typeof forwardedFor === "string") {
    const normalized = normalizeForwardedAddress(forwardedFor);
    if (normalized !== undefined) {
      return normalized;
    }
  }
  if (Array.isArray(forwardedFor) && forwardedFor.length > 0) {
    const normalized = normalizeForwardedAddress(forwardedFor[0]);
    if (normalized !== undefined) {
      return normalized;
    }
  }
  if (typeof realIp === "string" && realIp.trim() !== "") {
    return realIp.trim();
  }

  return req.socket.remoteAddress ?? "unknown";
};

export const getTrafficPolicy = (_method: string, pathname: string): TrafficPolicy => {
  const normalizedPath = pathname.toLowerCase().replace(/-/g, "_");
  if (
    normalizedPath.startsWith("/api/v1/pulse/")
    || normalizedPath.includes("swee_pulse_")
  ) {
    return PULSE_POLICY;
  }
  if (
    normalizedPath.startsWith("/api/v1/shield/")
    || normalizedPath.includes("swee_shield_")
  ) {
    return SHIELD_POLICY;
  }

  return DEFAULT_TRAFFIC_POLICY;
};

export const checkTrafficLimit = (params: {
  readonly clientId: string;
  readonly policy: TrafficPolicy;
  readonly now?: number;
}): TrafficLimitResult => {
  const now = params.now ?? Date.now();
  const key = bucketKey(params.clientId, params.policy);
  const existing = buckets.get(key);
  const bucket =
    existing === undefined || existing.resetAt <= now
      ? { count: 0, resetAt: now + params.policy.windowMs }
      : existing;

  if (bucket.count >= params.policy.maxRequests) {
    buckets.set(key, bucket);
    return {
      allowed: false,
      remaining: 0,
      resetAt: bucket.resetAt,
      retryAfterSeconds: Math.max(1, Math.ceil((bucket.resetAt - now) / 1000)),
    };
  }

  bucket.count += 1;
  buckets.set(key, bucket);
  return {
    allowed: true,
    remaining: Math.max(params.policy.maxRequests - bucket.count, 0),
    resetAt: bucket.resetAt,
  };
};

export const buildRateLimitResponse = (
  policy: TrafficPolicy,
  result: Extract<TrafficLimitResult, { readonly allowed: false }>,
): TrafficLimitResponse => ({
  error: {
    code: "RATE_LIMITED",
    message: `Too many ${policy.label} requests. Try again in about ${result.retryAfterSeconds} seconds.`,
    limit: policy.maxRequests,
    windowSeconds: Math.ceil(policy.windowMs / 1000),
    retryAfterSeconds: result.retryAfterSeconds,
  },
});

export const clearTrafficControlStoreForTests = (): void => {
  buckets.clear();
};
