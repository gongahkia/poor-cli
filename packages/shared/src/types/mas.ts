export type MasRecord = {
  readonly end_of_day: string;
  readonly preliminary?: string;
  readonly timestamp?: string;
  readonly [key: string]: unknown;
};

export type MasQueryParams = {
  readonly limit?: number;
  readonly date?: string;
  readonly startDate?: string;
  readonly endDate?: string;
};

export const MasDataset = {
  EXCHANGE_RATES: "exchange_rates",
  INTEREST_RATES_SORA: "interest_rates_sora",
  BANKING_STATS: "banking_stats",
} as const;

export type MasDatasetKey = keyof typeof MasDataset;

export type NormalizedMasRecord = {
  readonly date: string;
  readonly [key: string]: string | number;
};
