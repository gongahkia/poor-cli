export type DatagovV2ListResponse = {
  readonly code: number;
  readonly data: {
    readonly datasets: readonly DatagovDataset[];
    readonly pages: number;
    readonly rowCount: number;
    readonly totalRowCount: number;
  };
  readonly errorMsg: string;
};

export type DatagovDataset = {
  readonly datasetId: string;
  readonly createdAt: string;
  readonly name: string;
  readonly status: string;
  readonly description?: string;
  readonly format: string;
  readonly lastUpdatedAt: string;
  readonly managedByAgencyName: string;
  readonly coverageStart?: string;
  readonly coverageEnd?: string;
};

export type DatagovCollection = {
  readonly id: string;
  readonly name: string;
  readonly description: string;
  readonly datasetCount: number;
};

export type DatagovDatastoreField = {
  readonly id: string;
  readonly type: string;
};

export type DatagovDatastoreResult<TRecord extends Readonly<Record<string, unknown>>> = {
  readonly fields: readonly DatagovDatastoreField[];
  readonly records: readonly TRecord[];
  readonly total: number;
  readonly offset?: number;
  readonly limit?: number;
};

export type DatagovDatastoreResponse<TRecord extends Readonly<Record<string, unknown>>> =
  | {
      readonly success: true;
      readonly result: DatagovDatastoreResult<TRecord>;
    }
  | {
      readonly code: number;
      readonly name: string;
      readonly data: null;
      readonly errorMsg: string;
    };
