export type UraTransactionResponse = {
    readonly Status: string;
    readonly Result: readonly UraRawTransaction[];
};
export type UraRawTransaction = {
    readonly project: string;
    readonly street: string;
    readonly x: string;
    readonly y: string;
    readonly marketSegment: string;
    readonly area: string;
    readonly floorRange: string;
    readonly noOfUnits: string;
    readonly contractDate: string;
    readonly typeOfSale: string;
    readonly price: string;
    readonly propertyType: string;
    readonly district: string;
    readonly typeOfArea: string;
    readonly tenure: string;
    readonly nettPrice: string;
};
export type NormalizedTransaction = {
    readonly project: string;
    readonly street: string;
    readonly lat: number;
    readonly lng: number;
    readonly marketSegment: string;
    readonly areaSqm: string;
    readonly floorRange: string;
    readonly units: number;
    readonly contractDate: string;
    readonly saleType: string;
    readonly price: number;
    readonly propertyType: string;
    readonly district: string;
    readonly areaType: string;
    readonly tenure: string;
};
export type UraPlanningResponse = {
    readonly Status: string;
    readonly Result: readonly UraPlanningResult[];
};
export type UraPlanningResult = {
    readonly pln_area_n: string;
    readonly region: string;
};
export type UraDevChargeResponse = {
    readonly Status: string;
    readonly Result: readonly UraDevCharge[];
};
export type UraDevCharge = {
    readonly use_grp: string;
    readonly sector: string;
    readonly rate: string;
    readonly effDate: string;
};
//# sourceMappingURL=ura.d.ts.map