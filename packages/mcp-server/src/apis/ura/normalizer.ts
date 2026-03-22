import type { UraRawTransaction, NormalizedTransaction } from "@sg-apis/shared";

const SALE_TYPE_MAP: Readonly<Record<string, string>> = {
  "1": "New Sale",
  "2": "Sub Sale",
  "3": "Resale",
};

export const normalizeTransactions = (raw: readonly UraRawTransaction[]): NormalizedTransaction[] => {
  return raw.map((t) => ({
    project: t.project,
    street: t.street,
    lat: parseFloat(t.y) || 0,
    lng: parseFloat(t.x) || 0,
    marketSegment: t.marketSegment,
    areaSqm: t.area,
    floorRange: t.floorRange,
    units: parseInt(t.noOfUnits, 10) || 1,
    contractDate: normalizeContractDate(t.contractDate),
    saleType: SALE_TYPE_MAP[t.typeOfSale] ?? t.typeOfSale,
    price: parseInt(t.price, 10) || 0,
    propertyType: t.propertyType,
    district: t.district,
    areaType: t.typeOfArea,
    tenure: t.tenure,
  }));
};

const normalizeContractDate = (mmyy: string): string => {
  if (mmyy.length !== 4) return mmyy;
  const month = mmyy.slice(0, 2);
  const year = `20${mmyy.slice(2, 4)}`;
  return `${year}-${month}`;
};

export const normalizePlanningData = (raw: { pln_area_n: string; region: string }): { planningArea: string; region: string } => {
  return {
    planningArea: raw.pln_area_n,
    region: raw.region,
  };
};
