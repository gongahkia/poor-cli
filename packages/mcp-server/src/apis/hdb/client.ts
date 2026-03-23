import type {
  HdbNormalizedRentalRecord,
  HdbNormalizedResaleRecord,
  HdbRentalRecord,
  HdbResaleRecord,
} from "@sg-apis/shared";
import { queryDatastore } from "../datagov/client.js";

const RESALE_RESOURCE_ID = "d_8b84c4ee58e3cfc0ece0d773c8ca6abc";
const RENTAL_RESOURCE_ID = "d_c9f57187485a850908655db0e8cfe651";

type HdbFilterParams = {
  readonly town?: string | undefined;
  readonly flatType?: string | undefined;
  readonly startMonth?: string | undefined;
  readonly endMonth?: string | undefined;
  readonly limit?: number | undefined;
};

const normalizeStringFilter = (value: string | undefined): string | undefined => {
  if (value === undefined) {
    return undefined;
  }
  return value.trim().toUpperCase();
};

const withinMonthRange = (
  value: string,
  startMonth: string | undefined,
  endMonth: string | undefined,
): boolean => {
  if (startMonth !== undefined && value < startMonth) {
    return false;
  }
  if (endMonth !== undefined && value > endMonth) {
    return false;
  }
  return true;
};

const parseNullableNumber = (value: string): number | null => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const buildDatastoreFilters = (
  params: HdbFilterParams,
  keys: Readonly<{ town: string; flatType: string }>,
): Readonly<Record<string, string>> => ({
  ...(params.town === undefined ? {} : { [keys.town]: normalizeStringFilter(params.town)! }),
  ...(params.flatType === undefined ? {} : { [keys.flatType]: normalizeStringFilter(params.flatType)! }),
});

const getQueryLimit = (limit?: number): number => {
  return Math.min(Math.max(limit ?? 50, 50), 200);
};

export const getHdbResalePrices = async (
  params: HdbFilterParams,
): Promise<readonly HdbNormalizedResaleRecord[]> => {
  const rows = await queryDatastore<HdbResaleRecord>(RESALE_RESOURCE_ID, {
    limit: getQueryLimit(params.limit),
    sort: "month desc",
    filters: buildDatastoreFilters(params, { town: "town", flatType: "flat_type" }),
  });

  return rows
    .filter((row) => withinMonthRange(row.month, params.startMonth, params.endMonth))
    .map((row) => ({
      month: row.month,
      town: row.town,
      flatType: row.flat_type,
      block: row.block,
      streetName: row.street_name,
      storeyRange: row.storey_range,
      floorAreaSqm: parseNullableNumber(row.floor_area_sqm),
      flatModel: row.flat_model,
      leaseCommenceDate: parseNullableNumber(row.lease_commence_date),
      remainingLease: row.remaining_lease,
      resalePrice: parseNullableNumber(row.resale_price),
    }))
    .slice(0, params.limit ?? 50);
};

export const getHdbRentalPrices = async (
  params: HdbFilterParams,
): Promise<readonly HdbNormalizedRentalRecord[]> => {
  const rows = await queryDatastore<HdbRentalRecord>(RENTAL_RESOURCE_ID, {
    limit: getQueryLimit(params.limit),
    sort: "rent_approval_date desc",
    filters: buildDatastoreFilters(params, { town: "town", flatType: "flat_type" }),
  });

  return rows
    .filter((row) => withinMonthRange(row.rent_approval_date, params.startMonth, params.endMonth))
    .map((row) => ({
      approvalMonth: row.rent_approval_date,
      town: row.town,
      block: row.block,
      streetName: row.street_name,
      flatType: row.flat_type,
      monthlyRent: parseNullableNumber(row.monthly_rent),
    }))
    .slice(0, params.limit ?? 50);
};
