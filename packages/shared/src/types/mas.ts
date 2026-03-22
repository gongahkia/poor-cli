export type MasResponse = {
  readonly success: boolean;
  readonly result: {
    readonly resource_id: string;
    readonly total: number;
    readonly records: readonly MasRecord[];
    readonly limit: number;
    readonly offset: number;
    readonly fields: readonly MasField[];
  };
};

export type MasRecord = {
  readonly _id: number;
  readonly end_of_day: string;
  readonly preliminary: string;
  readonly timestamp?: string;
  readonly [key: string]: unknown;
};

export type MasField = {
  readonly type: string;
  readonly id: string;
};

export type MasQueryParams = {
  readonly limit?: number;
  readonly offset?: number;
  readonly filters?: Readonly<Record<string, string>>;
  readonly sort?: string;
};

export const MasDataset = {
  EXCHANGE_RATES: "95932927-c8bc-4e7a-b484-68a66a24edfe",
  INTEREST_RATES_SORA: "9a0bf149-308c-4bd2-832d-76c8e6cb47ed",
  BANKING_STATS: "5f2b18a8-0883-4e5b-9dc7-990de1383525",
} as const;

export type MasDatasetKey = keyof typeof MasDataset;

export type NormalizedMasRecord = {
  readonly date: string;
  readonly [key: string]: string | number;
};
