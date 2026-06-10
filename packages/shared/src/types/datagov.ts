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

export type DatagovColumnMetadata = {
  readonly key: string;
  readonly name: string;
  readonly title: string;
  readonly dataType: string;
  readonly index: number | null;
  readonly isCategorical: boolean;
};

export type DatagovDatasetResource = {
  readonly resourceId: string;
  readonly datasetId: string;
  readonly name: string;
  readonly format: string;
  readonly machineReadable: boolean;
  readonly columns: readonly DatagovColumnMetadata[];
};

export type DatagovDatasetMetadata = DatagovDataset & {
  readonly collectionIds: readonly string[];
  readonly managedByAgencyName: string;
  readonly contactEmails: readonly string[];
  readonly datasetSize: number | null;
  readonly resources: readonly DatagovDatasetResource[];
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

export type DatagovMetadataResponse = {
  readonly code: number;
  readonly data: {
    readonly datasetId: string;
    readonly createdAt: string;
    readonly name: string;
    readonly collectionIds?: readonly string[];
    readonly status?: string;
    readonly description?: string;
    readonly format: string;
    readonly lastUpdatedAt: string;
    readonly managedBy?: string;
    readonly managedByAgencyName?: string;
    readonly coverageStart?: string;
    readonly coverageEnd?: string;
    readonly contactEmails?: readonly string[];
    readonly datasetSize?: number;
    readonly columnMetadata?: {
      readonly order?: readonly string[];
      readonly map?: Readonly<Record<string, string>>;
      readonly metaMapping?: Readonly<Record<string, {
        readonly name?: string;
        readonly columnTitle?: string;
        readonly dataType?: string;
        readonly index?: string;
        readonly isCategorical?: boolean;
      }>>;
    };
  };
  readonly errorMsg: string;
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
