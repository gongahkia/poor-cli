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
//# sourceMappingURL=datagov.d.ts.map