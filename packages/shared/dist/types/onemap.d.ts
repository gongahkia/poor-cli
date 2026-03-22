export type OneMapSearchResponse = {
    readonly found: number;
    readonly totalNumPages: number;
    readonly pageNum: number;
    readonly results: readonly OneMapSearchResult[];
};
export type OneMapSearchResult = {
    readonly SEARCHVAL: string;
    readonly BLK_NO: string;
    readonly ROAD_NAME: string;
    readonly BUILDING: string;
    readonly ADDRESS: string;
    readonly POSTAL: string;
    readonly X: string;
    readonly Y: string;
    readonly LATITUDE: string;
    readonly LONGITUDE: string;
};
export type GeocodeResult = {
    readonly address: string;
    readonly building: string;
    readonly postal: string | null;
    readonly lat: number;
    readonly lng: number;
    readonly x: number;
    readonly y: number;
};
export type GeocodeOptions = {
    readonly returnGeom?: boolean;
    readonly getAddrDetails?: boolean;
    readonly pageNum?: number;
};
export type ReverseGeocodeResponse = {
    readonly GeocodeInfo: readonly ReverseGeocodeEntry[];
};
export type ReverseGeocodeEntry = {
    readonly BUILDINGNAME: string;
    readonly BLOCK: string;
    readonly ROAD: string;
    readonly POSTALCODE: string;
    readonly XCOORD: string;
    readonly YCOORD: string;
    readonly LATITUDE: string;
    readonly LONGITUDE: string;
    readonly LONGTITUDE: string;
};
export type ReverseGeocodeResult = {
    readonly building: string;
    readonly address: string;
    readonly postal: string | null;
    readonly lat: number;
    readonly lng: number;
};
export type ReverseGeocodeOptions = {
    readonly buffer?: number;
    readonly addressType?: "All" | "HDB";
};
export type RouteType = "walk" | "drive" | "pt" | "cycle";
export type RouteOptions = {
    readonly date?: string;
    readonly time?: string;
    readonly mode?: "TRANSIT" | "BUS" | "RAIL";
};
export type RouteResult = {
    readonly totalDistance: number;
    readonly totalTime: number;
    readonly instructions: readonly RouteStep[];
    readonly routeName: readonly string[];
};
export type RouteStep = {
    readonly instruction: string;
    readonly road: string;
    readonly distance: number;
};
export type PopulationDataType = "getEconomicStatus" | "getEthnicGroup" | "getHouseholdMonthlyIncomeWork" | "getPopulationAgeGroup" | "getSpokenAtHome" | "getTenantHouseholdSize" | "getTypeOfDwellingHousehold";
export type PopulationData = {
    readonly planningArea: string;
    readonly year: string;
    readonly data: readonly Readonly<Record<string, string>>[];
};
//# sourceMappingURL=onemap.d.ts.map