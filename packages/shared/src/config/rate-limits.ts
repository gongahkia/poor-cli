export type RateLimitConfig = {
  readonly maxTokens: number;
  readonly refillPerSecond: number;
};

export const RATE_LIMITS: Readonly<Record<string, RateLimitConfig>> = {
  singstat: { maxTokens: 10, refillPerSecond: 2 }, // WHY: no published rate limit, conservative default
  mas: { maxTokens: 10, refillPerSecond: 2 }, // WHY: same reasoning as SingStat
  onemap: { maxTokens: 50, refillPerSecond: 4 }, // WHY: OneMap allows ~250/min, 4/s is safe margin
  ura: { maxTokens: 5, refillPerSecond: 1 }, // WHY: URA API is slow, avoid overwhelming it
  lta: { maxTokens: 20, refillPerSecond: 2 }, // WHY: live transport endpoints should be paced but remain responsive
  nea: { maxTokens: 20, refillPerSecond: 2 }, // WHY: public realtime endpoints can be queried regularly without burst abuse
  datagov: { maxTokens: 20, refillPerSecond: 3 }, // WHY: CKAN API is shared infra, be respectful
  govfeeds: { maxTokens: 10, refillPerSecond: 1 }, // WHY: RSS endpoints are public but should be polled conservatively
} as const;
