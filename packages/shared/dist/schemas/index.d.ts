import { z } from "zod";
import type { ZodSchema } from "zod";
export declare const SingStatSearchSchema: z.ZodObject<{
    keyword: z.ZodString;
    limit: z.ZodOptional<z.ZodNumber>;
}, "strip", z.ZodTypeAny, {
    keyword: string;
    limit?: number | undefined;
}, {
    keyword: string;
    limit?: number | undefined;
}>;
export declare const SingStatTableSchema: z.ZodObject<{
    tableId: z.ZodString;
    timeFilter: z.ZodOptional<z.ZodString>;
    variables: z.ZodOptional<z.ZodArray<z.ZodString, "many">>;
    format: z.ZodOptional<z.ZodEnum<["json", "markdown", "csv", "geojson"]>>;
}, "strip", z.ZodTypeAny, {
    tableId: string;
    timeFilter?: string | undefined;
    variables?: string[] | undefined;
    format?: "json" | "markdown" | "csv" | "geojson" | undefined;
}, {
    tableId: string;
    timeFilter?: string | undefined;
    variables?: string[] | undefined;
    format?: "json" | "markdown" | "csv" | "geojson" | undefined;
}>;
export declare const SingStatBrowseSchema: z.ZodObject<{
    category: z.ZodOptional<z.ZodString>;
}, "strip", z.ZodTypeAny, {
    category?: string | undefined;
}, {
    category?: string | undefined;
}>;
export declare const SingStatTimeseriesSchema: z.ZodObject<{
    tableId: z.ZodString;
    indicator: z.ZodString;
    startYear: z.ZodNumber;
    endYear: z.ZodNumber;
    format: z.ZodOptional<z.ZodEnum<["json", "markdown", "csv", "geojson"]>>;
}, "strip", z.ZodTypeAny, {
    tableId: string;
    indicator: string;
    startYear: number;
    endYear: number;
    format?: "json" | "markdown" | "csv" | "geojson" | undefined;
}, {
    tableId: string;
    indicator: string;
    startYear: number;
    endYear: number;
    format?: "json" | "markdown" | "csv" | "geojson" | undefined;
}>;
export declare const SingStatCompareSchema: z.ZodObject<{
    queries: z.ZodArray<z.ZodObject<{
        tableId: z.ZodString;
        indicator: z.ZodString;
        label: z.ZodString;
    }, "strip", z.ZodTypeAny, {
        tableId: string;
        indicator: string;
        label: string;
    }, {
        tableId: string;
        indicator: string;
        label: string;
    }>, "many">;
    startYear: z.ZodOptional<z.ZodNumber>;
    endYear: z.ZodOptional<z.ZodNumber>;
    format: z.ZodOptional<z.ZodEnum<["json", "markdown", "csv", "geojson"]>>;
}, "strip", z.ZodTypeAny, {
    queries: {
        tableId: string;
        indicator: string;
        label: string;
    }[];
    format?: "json" | "markdown" | "csv" | "geojson" | undefined;
    startYear?: number | undefined;
    endYear?: number | undefined;
}, {
    queries: {
        tableId: string;
        indicator: string;
        label: string;
    }[];
    format?: "json" | "markdown" | "csv" | "geojson" | undefined;
    startYear?: number | undefined;
    endYear?: number | undefined;
}>;
export declare const MasExchangeRateSchema: z.ZodObject<{
    currency: z.ZodOptional<z.ZodString>;
    startDate: z.ZodOptional<z.ZodString>;
    endDate: z.ZodOptional<z.ZodString>;
    format: z.ZodOptional<z.ZodEnum<["json", "markdown", "csv", "geojson"]>>;
}, "strip", z.ZodTypeAny, {
    format?: "json" | "markdown" | "csv" | "geojson" | undefined;
    currency?: string | undefined;
    startDate?: string | undefined;
    endDate?: string | undefined;
}, {
    format?: "json" | "markdown" | "csv" | "geojson" | undefined;
    currency?: string | undefined;
    startDate?: string | undefined;
    endDate?: string | undefined;
}>;
export declare const MasInterestRateSchema: z.ZodObject<{
    rateType: z.ZodOptional<z.ZodEnum<["sora", "prime", "fixed_deposit"]>>;
    startDate: z.ZodOptional<z.ZodString>;
    endDate: z.ZodOptional<z.ZodString>;
    format: z.ZodOptional<z.ZodEnum<["json", "markdown", "csv", "geojson"]>>;
}, "strip", z.ZodTypeAny, {
    format?: "json" | "markdown" | "csv" | "geojson" | undefined;
    startDate?: string | undefined;
    endDate?: string | undefined;
    rateType?: "sora" | "prime" | "fixed_deposit" | undefined;
}, {
    format?: "json" | "markdown" | "csv" | "geojson" | undefined;
    startDate?: string | undefined;
    endDate?: string | undefined;
    rateType?: "sora" | "prime" | "fixed_deposit" | undefined;
}>;
export declare const MasFinancialStatsSchema: z.ZodObject<{
    category: z.ZodEnum<["banking", "insurance", "monetary"]>;
    startDate: z.ZodOptional<z.ZodString>;
    endDate: z.ZodOptional<z.ZodString>;
    format: z.ZodOptional<z.ZodEnum<["json", "markdown", "csv", "geojson"]>>;
}, "strip", z.ZodTypeAny, {
    category: "banking" | "insurance" | "monetary";
    format?: "json" | "markdown" | "csv" | "geojson" | undefined;
    startDate?: string | undefined;
    endDate?: string | undefined;
}, {
    category: "banking" | "insurance" | "monetary";
    format?: "json" | "markdown" | "csv" | "geojson" | undefined;
    startDate?: string | undefined;
    endDate?: string | undefined;
}>;
export declare const OneMapGeocodeSchema: z.ZodObject<{
    searchVal: z.ZodString;
    limit: z.ZodOptional<z.ZodNumber>;
}, "strip", z.ZodTypeAny, {
    searchVal: string;
    limit?: number | undefined;
}, {
    searchVal: string;
    limit?: number | undefined;
}>;
export declare const OneMapReverseGeocodeSchema: z.ZodObject<{
    lat: z.ZodNumber;
    lng: z.ZodNumber;
    buffer: z.ZodOptional<z.ZodNumber>;
}, "strip", z.ZodTypeAny, {
    lat: number;
    lng: number;
    buffer?: number | undefined;
}, {
    lat: number;
    lng: number;
    buffer?: number | undefined;
}>;
export declare const OneMapRouteSchema: z.ZodObject<{
    startLat: z.ZodNumber;
    startLng: z.ZodNumber;
    endLat: z.ZodNumber;
    endLng: z.ZodNumber;
    routeType: z.ZodEnum<["walk", "drive", "pt", "cycle"]>;
    date: z.ZodOptional<z.ZodString>;
    time: z.ZodOptional<z.ZodString>;
}, "strip", z.ZodTypeAny, {
    startLat: number;
    startLng: number;
    endLat: number;
    endLng: number;
    routeType: "walk" | "drive" | "pt" | "cycle";
    date?: string | undefined;
    time?: string | undefined;
}, {
    startLat: number;
    startLng: number;
    endLat: number;
    endLng: number;
    routeType: "walk" | "drive" | "pt" | "cycle";
    date?: string | undefined;
    time?: string | undefined;
}>;
export declare const OneMapPopulationSchema: z.ZodObject<{
    planningArea: z.ZodString;
    year: z.ZodOptional<z.ZodString>;
    dataType: z.ZodOptional<z.ZodEnum<["getEconomicStatus", "getEthnicGroup", "getHouseholdMonthlyIncomeWork", "getPopulationAgeGroup", "getSpokenAtHome", "getTenantHouseholdSize", "getTypeOfDwellingHousehold"]>>;
    format: z.ZodOptional<z.ZodEnum<["json", "markdown", "csv", "geojson"]>>;
}, "strip", z.ZodTypeAny, {
    planningArea: string;
    format?: "json" | "markdown" | "csv" | "geojson" | undefined;
    year?: string | undefined;
    dataType?: "getEconomicStatus" | "getEthnicGroup" | "getHouseholdMonthlyIncomeWork" | "getPopulationAgeGroup" | "getSpokenAtHome" | "getTenantHouseholdSize" | "getTypeOfDwellingHousehold" | undefined;
}, {
    planningArea: string;
    format?: "json" | "markdown" | "csv" | "geojson" | undefined;
    year?: string | undefined;
    dataType?: "getEconomicStatus" | "getEthnicGroup" | "getHouseholdMonthlyIncomeWork" | "getPopulationAgeGroup" | "getSpokenAtHome" | "getTenantHouseholdSize" | "getTypeOfDwellingHousehold" | undefined;
}>;
export declare const OneMapConvertCoordsSchema: z.ZodObject<{
    from: z.ZodEnum<["SVY21", "WGS84"]>;
    x: z.ZodNumber;
    y: z.ZodNumber;
}, "strip", z.ZodTypeAny, {
    from: "SVY21" | "WGS84";
    x: number;
    y: number;
}, {
    from: "SVY21" | "WGS84";
    x: number;
    y: number;
}>;
export declare const UraPropertyTransactionsSchema: z.ZodObject<{
    propertyType: z.ZodOptional<z.ZodEnum<["residential", "commercial", "industrial"]>>;
    area: z.ZodOptional<z.ZodString>;
    period: z.ZodOptional<z.ZodString>;
    format: z.ZodOptional<z.ZodEnum<["json", "markdown", "csv", "geojson"]>>;
}, "strip", z.ZodTypeAny, {
    format?: "json" | "markdown" | "csv" | "geojson" | undefined;
    propertyType?: "residential" | "commercial" | "industrial" | undefined;
    area?: string | undefined;
    period?: string | undefined;
}, {
    format?: "json" | "markdown" | "csv" | "geojson" | undefined;
    propertyType?: "residential" | "commercial" | "industrial" | undefined;
    area?: string | undefined;
    period?: string | undefined;
}>;
export declare const UraPlanningAreaSchema: z.ZodObject<{
    lat: z.ZodOptional<z.ZodNumber>;
    lng: z.ZodOptional<z.ZodNumber>;
    planningArea: z.ZodOptional<z.ZodString>;
}, "strip", z.ZodTypeAny, {
    lat?: number | undefined;
    lng?: number | undefined;
    planningArea?: string | undefined;
}, {
    lat?: number | undefined;
    lng?: number | undefined;
    planningArea?: string | undefined;
}>;
export declare const UraDevChargesSchema: z.ZodObject<{
    useGroup: z.ZodOptional<z.ZodString>;
    sector: z.ZodOptional<z.ZodString>;
}, "strip", z.ZodTypeAny, {
    useGroup?: string | undefined;
    sector?: string | undefined;
}, {
    useGroup?: string | undefined;
    sector?: string | undefined;
}>;
export declare const DatagovSearchSchema: z.ZodObject<{
    keyword: z.ZodString;
    limit: z.ZodOptional<z.ZodNumber>;
}, "strip", z.ZodTypeAny, {
    keyword: string;
    limit?: number | undefined;
}, {
    keyword: string;
    limit?: number | undefined;
}>;
export declare const DatagovGetSchema: z.ZodObject<{
    datasetId: z.ZodString;
    resourceIndex: z.ZodOptional<z.ZodNumber>;
    limit: z.ZodOptional<z.ZodNumber>;
    offset: z.ZodOptional<z.ZodNumber>;
    filters: z.ZodOptional<z.ZodRecord<z.ZodString, z.ZodString>>;
    format: z.ZodOptional<z.ZodEnum<["json", "markdown", "csv", "geojson"]>>;
}, "strip", z.ZodTypeAny, {
    datasetId: string;
    limit?: number | undefined;
    format?: "json" | "markdown" | "csv" | "geojson" | undefined;
    resourceIndex?: number | undefined;
    offset?: number | undefined;
    filters?: Record<string, string> | undefined;
}, {
    datasetId: string;
    limit?: number | undefined;
    format?: "json" | "markdown" | "csv" | "geojson" | undefined;
    resourceIndex?: number | undefined;
    offset?: number | undefined;
    filters?: Record<string, string> | undefined;
}>;
export declare const DatagovBrowseSchema: z.ZodObject<{
    collection: z.ZodOptional<z.ZodString>;
}, "strip", z.ZodTypeAny, {
    collection?: string | undefined;
}, {
    collection?: string | undefined;
}>;
export declare const HealthCheckSchema: z.ZodOptional<z.ZodObject<{}, "strip", z.ZodTypeAny, {}, {}>>;
export declare const KeySetSchema: z.ZodObject<{
    apiName: z.ZodString;
    key: z.ZodString;
}, "strip", z.ZodTypeAny, {
    apiName: string;
    key: string;
}, {
    apiName: string;
    key: string;
}>;
export declare const KeyListSchema: z.ZodOptional<z.ZodObject<{}, "strip", z.ZodTypeAny, {}, {}>>;
export declare const KeyDeleteSchema: z.ZodObject<{
    apiName: z.ZodString;
}, "strip", z.ZodTypeAny, {
    apiName: string;
}, {
    apiName: string;
}>;
export declare const CacheStatsSchema: z.ZodOptional<z.ZodObject<{}, "strip", z.ZodTypeAny, {}, {}>>;
export declare const CacheClearSchema: z.ZodObject<{
    api: z.ZodOptional<z.ZodString>;
}, "strip", z.ZodTypeAny, {
    api?: string | undefined;
}, {
    api?: string | undefined;
}>;
export declare const ConfigGetSchema: z.ZodOptional<z.ZodObject<{}, "strip", z.ZodTypeAny, {}, {}>>;
export declare const ConfigSetSchema: z.ZodObject<{
    key: z.ZodString;
    value: z.ZodString;
}, "strip", z.ZodTypeAny, {
    key: string;
    value: string;
}, {
    key: string;
    value: string;
}>;
export declare const QuerySchema: z.ZodObject<{
    query: z.ZodString;
    format: z.ZodOptional<z.ZodEnum<["json", "markdown", "csv", "geojson"]>>;
}, "strip", z.ZodTypeAny, {
    query: string;
    format?: "json" | "markdown" | "csv" | "geojson" | undefined;
}, {
    query: string;
    format?: "json" | "markdown" | "csv" | "geojson" | undefined;
}>;
export declare const validateInput: <T>(schema: ZodSchema<T>, input: unknown) => T;
//# sourceMappingURL=index.d.ts.map