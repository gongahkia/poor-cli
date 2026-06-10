import { queryDatastore } from "../datagov/client.js";
import { haversineKm } from "../civic/utils.js";

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
  readonly distanceKm?: number;
};

type HawkerFilterParams = {
  readonly name?: string | undefined;
  readonly lat?: number | undefined;
  readonly lng?: number | undefined;
  readonly radiusKm?: number | undefined;
  readonly limit?: number | undefined;
};

const DEFAULT_RADIUS_KM = 3;

const normalize = (r: HawkerRawRecord): HawkerNormalizedRecord => ({
  name: r.name,
  address: r.address_myenv,
  lat: Number.isFinite(Number(r.latitude_hc)) ? Number(r.latitude_hc) : null,
  lng: Number.isFinite(Number(r.longitude_hc)) ? Number(r.longitude_hc) : null,
  totalStalls: Number.isFinite(Number(r.no_of_stalls)) ? Number(r.no_of_stalls) : null,
  cookedFoodStalls: Number.isFinite(Number(r.no_of_cooked_food_stalls)) ? Number(r.no_of_cooked_food_stalls) : null,
  description: r.description_myenv ?? "",
});

const roundKm = (v: number): number => Math.round(v * 1000) / 1000;

export const getHawkerCentres = async (
  params: HawkerFilterParams,
): Promise<readonly HawkerNormalizedRecord[]> => {
  const useProximity = typeof params.lat === "number" && typeof params.lng === "number";
  const filters: Record<string, string> = {};
  if (!useProximity && params.name !== undefined) filters["name"] = params.name; // server-side when no proximity
  const rows = await queryDatastore<HawkerRawRecord>(HAWKER_RESOURCE_ID, {
    limit: useProximity ? 200 : Math.min(params.limit ?? 50, 200),
    filters,
  });
  let results = rows.map(normalize);
  if (useProximity) {
    const radiusKm = params.radiusKm ?? DEFAULT_RADIUS_KM;
    results = results
      .filter((r) => r.lat !== null && r.lng !== null && haversineKm(params.lat!, params.lng!, r.lat, r.lng) <= radiusKm)
      .map((r) => ({ ...r, distanceKm: roundKm(haversineKm(params.lat!, params.lng!, r.lat!, r.lng!)) }))
      .sort((a, b) => (a.distanceKm ?? 0) - (b.distanceKm ?? 0));
    if (params.name !== undefined) { // client-side name filter when combined with proximity
      const lower = params.name.toLowerCase();
      results = results.filter((r) => r.name.toLowerCase().includes(lower));
    }
  }
  return results.slice(0, Math.min(params.limit ?? 50, 200));
};
