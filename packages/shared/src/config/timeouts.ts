export const TIMEOUTS: Readonly<Record<string, number>> = {
  singstat: 15000, // WHY: SingStat can be slow for large tables
  mas: 10000, // WHY: MAS is generally responsive
  onemap: 10000, // WHY: OneMap is generally responsive
  ura: 20000, // WHY: URA is the slowest API, especially for transaction data
  lta: 10000, // WHY: live transport endpoints should respond quickly
  nea: 10000, // WHY: realtime environmental endpoints are typically responsive
  datagov: 10000, // WHY: CKAN is generally responsive
} as const;

export const HARD_CAP_TIMEOUT = 30000; // WHY: no API call should ever take more than 30 seconds
