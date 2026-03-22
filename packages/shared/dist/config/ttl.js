export const TTL = {
    REALTIME: 30, // WHY: live data like taxi availability, stale after 30s
    NEAR_REALTIME: 300, // WHY: exchange rates update every few minutes, 5-min cache balances freshness vs. rate limits
    DAILY: 3600, // WHY: SingStat/URA data updates at most daily, 1-hour cache is safe
    STATIC: 86400, // WHY: planning area boundaries, coordinate conversions — data changes quarterly at most
    ARCHIVAL: 604800, // WHY: historical time series never change, cache for 7 days
};
//# sourceMappingURL=ttl.js.map