import { afterEach, describe, expect, it } from "vitest";
import type { IncomingMessage } from "node:http";

import {
  buildRateLimitResponse,
  checkTrafficLimit,
  clearTrafficControlStoreForTests,
  getClientId,
  getTrafficPolicy,
  type TrafficPolicy,
} from "../traffic-control.js";

const testPolicy: TrafficPolicy = {
  key: "test",
  label: "test route",
  windowMs: 60_000,
  maxRequests: 2,
  maxBodyBytes: 128,
};

afterEach(() => {
  clearTrafficControlStoreForTests();
});

describe("traffic control", () => {
  it("uses route-specific policy buckets for public endpoints", () => {
    expect(getTrafficPolicy("GET", "/api/v1/dude/search-suggestions")).toMatchObject({
      key: "search_suggestions",
      maxRequests: 120,
    });
    expect(getTrafficPolicy("GET", "/api/v1/dude/web-presence")).toMatchObject({
      key: "web_presence",
      maxRequests: 30,
    });
    expect(getTrafficPolicy("GET", "/api/v1/dude/people-discovery")).toMatchObject({
      key: "people_discovery",
      maxRequests: 30,
    });
    expect(getTrafficPolicy("POST", "/api/v1/sg_business_dossier")).toMatchObject({
      key: "business_dossier",
      maxRequests: 40,
    });
    expect(getTrafficPolicy("POST", "/api/v1/dude/bulk")).toMatchObject({
      key: "bulk",
      maxRequests: 8,
    });
    expect(getTrafficPolicy("POST", "/api/v1/dude/memo")).toMatchObject({
      key: "memo",
      maxRequests: 20,
    });
    expect(getTrafficPolicy("POST", "/api/v1/dude/summary")).toMatchObject({
      key: "summary",
      maxRequests: 20,
    });
  });

  it("allows requests until the bucket is exhausted", () => {
    expect(checkTrafficLimit({ clientId: "127.0.0.1", policy: testPolicy, now: 1000 })).toEqual({
      allowed: true,
      remaining: 1,
      resetAt: 61_000,
    });
    expect(checkTrafficLimit({ clientId: "127.0.0.1", policy: testPolicy, now: 1001 })).toEqual({
      allowed: true,
      remaining: 0,
      resetAt: 61_000,
    });
    expect(checkTrafficLimit({ clientId: "127.0.0.1", policy: testPolicy, now: 1002 })).toEqual({
      allowed: false,
      remaining: 0,
      resetAt: 61_000,
      retryAfterSeconds: 60,
    });
  });

  it("returns a readable structured rate-limit response", () => {
    const result = checkTrafficLimit({ clientId: "127.0.0.1", policy: testPolicy, now: 1000 });
    if (!result.allowed) {
      throw new Error("first request should be allowed");
    }
    checkTrafficLimit({ clientId: "127.0.0.1", policy: testPolicy, now: 1001 });
    const limited = checkTrafficLimit({ clientId: "127.0.0.1", policy: testPolicy, now: 1002 });
    if (limited.allowed) {
      throw new Error("third request should be limited");
    }

    expect(buildRateLimitResponse(testPolicy, limited)).toEqual({
      error: {
        code: "RATE_LIMITED",
        message: "Too many test route requests. Try again in about 60 seconds.",
        limit: 2,
        windowSeconds: 60,
        retryAfterSeconds: 60,
      },
    });
  });

  it("normalizes forwarded client addresses", () => {
    const req = {
      headers: { "x-forwarded-for": "203.0.113.10, 10.0.0.1" },
      socket: { remoteAddress: "127.0.0.1" },
    } as unknown as IncomingMessage;

    expect(getClientId(req)).toBe("203.0.113.10");
  });
});
