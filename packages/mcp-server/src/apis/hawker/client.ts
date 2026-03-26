import { queryDatastore } from "../datagov/client.js";

const HAWKER_RESOURCE_ID = "d_4a086c0a09247718f93cbd56449fa64e";

type HawkerRawRecord = {
  readonly name: string;
  readonly address_myenv: string;
  readonly latitude_hc: string;
  readonly longitude_hc: string;
  readonly no_of_stalls: string;
  readonly no_of_cooked_food_stalls: string;
  readonly description_myenv: string;
};

export type HawkerNormalizedRecord = {
  readonly name: string;
  readonly address: string;
  readonly lat: number | null;
  readonly lng: number | null;
  readonly totalStalls: number | null;
  readonly cookedFoodStalls: number | null;
  readonly description: string;
};

type HawkerFilterParams = {
  readonly name?: string | undefined;
  readonly limit?: number | undefined;
};

export const getHawkerCentres = async (
  params: HawkerFilterParams,
): Promise<readonly HawkerNormalizedRecord[]> => {
  const filters: Record<string, string> = {};
  if (params.name !== undefined) filters["name"] = params.name;
  const rows = await queryDatastore<HawkerRawRecord>(HAWKER_RESOURCE_ID, {
    limit: Math.min(params.limit ?? 50, 200),
    filters,
  });
  return rows.map((r) => ({
    name: r.name,
    address: r.address_myenv,
    lat: Number.isFinite(Number(r.latitude_hc)) ? Number(r.latitude_hc) : null,
    lng: Number.isFinite(Number(r.longitude_hc)) ? Number(r.longitude_hc) : null,
    totalStalls: Number.isFinite(Number(r.no_of_stalls)) ? Number(r.no_of_stalls) : null,
    cookedFoodStalls: Number.isFinite(Number(r.no_of_cooked_food_stalls)) ? Number(r.no_of_cooked_food_stalls) : null,
    description: r.description_myenv ?? "",
  }));
};
