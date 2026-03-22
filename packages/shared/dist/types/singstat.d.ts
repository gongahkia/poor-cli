export type SingStatSearchResponse = {
    readonly Data: {
        readonly generatedBy: string;
        readonly dateGenerated: string;
        readonly total: number;
        readonly records: readonly SingStatSearchRecord[];
    };
    readonly DataCount: number;
    readonly StatusCode: number;
    readonly Message: string;
};
export type SingStatSearchRecord = {
    readonly theme: string;
    readonly subject: string;
    readonly topic: string;
    readonly id: string;
    readonly title: string;
    readonly tableType: string;
};
export type SingStatTableResponse = {
    readonly Data: {
        readonly theme: string;
        readonly subject: string;
        readonly topic: string;
        readonly id: string;
        readonly title: string;
        readonly footnote: string;
        readonly frequency: string;
        readonly datasource: string;
        readonly generatedBy: string;
        readonly dataLastUpdated: string;
        readonly dateGenerated: string;
        readonly offset: string | null;
        readonly limit: string | null;
        readonly sortBy: string | null;
        readonly timeFilter: string | null;
        readonly between: string | null;
        readonly search: string | null;
        readonly row: readonly SingStatRow[];
    };
    readonly DataCount: number;
    readonly StatusCode: number;
    readonly Message: string;
};
export type SingStatRow = {
    readonly seriesNo: string;
    readonly rowText: string;
    readonly uoM: string;
    readonly footnote: string;
    readonly columns: readonly SingStatColumn[];
};
export type SingStatColumn = {
    readonly key: string;
    readonly value: string;
};
export type Dataset = {
    readonly id: string;
    readonly title: string;
    readonly theme: string;
    readonly subject: string;
    readonly topic: string;
    readonly frequency: string;
};
export type TableData = {
    readonly rows: readonly NormalizedRow[];
    readonly metadata: TableMetadata;
    readonly total: number;
};
export type NormalizedRow = {
    readonly period: string;
    readonly variable: string;
    readonly value: number | string;
    readonly unit: string;
    readonly footnote?: string;
};
export type TableMetadata = {
    readonly title: string;
    readonly frequency: string;
    readonly source: string;
    readonly lastUpdated: string;
};
export type TimeSeriesRow = {
    readonly period: string;
    readonly value: number;
    readonly unit: string;
};
export type IndicatorQuery = {
    readonly tableId: string;
    readonly indicator: string;
    readonly label: string;
};
export type ComparisonResult = {
    readonly periods: readonly string[];
    readonly series: readonly {
        readonly label: string;
        readonly values: readonly (number | null)[];
    }[];
};
export type TableOptions = {
    readonly timeFilter?: string;
    readonly variables?: readonly string[];
    readonly offset?: number;
    readonly limit?: number;
};
//# sourceMappingURL=singstat.d.ts.map