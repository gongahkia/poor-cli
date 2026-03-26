import type { CivicDirectoryRecord, EcdaVacancyStatus, GeoFeature } from "@sg-apis/shared";

export type DirectoryFilterParams = {
  readonly name?: string | undefined;
  readonly postalCode?: string | undefined;
  readonly lat?: number | undefined;
  readonly lng?: number | undefined;
  readonly radiusKm?: number | undefined;
  readonly limit?: number | undefined;
};

export const DEFAULT_CIVIC_RADIUS_KM = 3;

const EARTH_RADIUS_KM = 6371;

const toRadians = (value: number): number => (value * Math.PI) / 180;

export const toNumberOrNull = (value: unknown): number | null => {
  const number = typeof value === "number" ? value : Number(value);
  return Number.isFinite(number) ? number : null;
};

export const toNullableString = (value: unknown): string | null => {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed === "" || trimmed.toLowerCase() === "na" ? null : trimmed;
};

export const normalizeLookupKey = (value: string | null | undefined): string => {
  return (value ?? "")
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/[^a-z0-9]/g, "");
};

export const normalizePostalCode = (value: string | null | undefined): string | null => {
  if (value === null || value === undefined) {
    return null;
  }
  const digits = value.replace(/\D/g, "");
  return digits.length === 6 ? digits : null;
};

export const buildAddress = (...parts: Array<string | null | undefined>): string => {
  const cleaned = parts
    .map((part) => part?.trim())
    .filter((part): part is string => part !== undefined && part !== null && part !== "");
  return cleaned.join(", ");
};

export const parseFmelTimestamp = (value: unknown): string | null => {
  const raw = typeof value === "number" ? String(value) : typeof value === "string" ? value.trim() : "";
  if (!/^\d{14}$/.test(raw)) {
    return null;
  }

  const year = raw.slice(0, 4);
  const month = raw.slice(4, 6);
  const day = raw.slice(6, 8);
  const hour = raw.slice(8, 10);
  const minute = raw.slice(10, 12);
  const second = raw.slice(12, 14);
  return `${year}-${month}-${day}T${hour}:${minute}:${second}+08:00`;
};

export const haversineKm = (
  startLat: number,
  startLng: number,
  endLat: number,
  endLng: number,
): number => {
  const latDelta = toRadians(endLat - startLat);
  const lngDelta = toRadians(endLng - startLng);
  const startLatRad = toRadians(startLat);
  const endLatRad = toRadians(endLat);

  const a =
    Math.sin(latDelta / 2) ** 2
    + Math.cos(startLatRad) * Math.cos(endLatRad) * Math.sin(lngDelta / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return EARTH_RADIUS_KM * c;
};

const roundDistanceKm = (value: number): number => Math.round(value * 1000) / 1000;

export const applyDirectoryFilters = <TRecord extends CivicDirectoryRecord>(
  records: readonly TRecord[],
  params: DirectoryFilterParams,
): readonly TRecord[] => {
  const normalizedName = normalizeLookupKey(params.name);
  const normalizedPostalCode = normalizePostalCode(params.postalCode);
  const useDistance =
    typeof params.lat === "number"
    && typeof params.lng === "number";
  const radiusKm = params.radiusKm ?? DEFAULT_CIVIC_RADIUS_KM;

  const filtered = records
    .filter((record) => {
      if (normalizedName !== "" && !normalizeLookupKey(record.name).includes(normalizedName)) {
        return false;
      }
      if (normalizedPostalCode !== null && record.postalCode !== normalizedPostalCode) {
        return false;
      }
      if (!useDistance) {
        return true;
      }
      if (record.lat === null || record.lng === null) {
        return false;
      }
      return haversineKm(params.lat!, params.lng!, record.lat, record.lng) <= radiusKm;
    })
    .map((record) => {
      if (!useDistance || record.lat === null || record.lng === null) {
        return record;
      }
      return {
        ...record,
        distanceKm: roundDistanceKm(haversineKm(params.lat!, params.lng!, record.lat, record.lng)),
      };
    })
    .sort((left, right) => {
      if (left.distanceKm !== undefined && right.distanceKm !== undefined) {
        if (left.distanceKm !== right.distanceKm) {
          return left.distanceKm - right.distanceKm;
        }
      }
      return left.name.localeCompare(right.name);
    });

  return filtered.slice(0, Math.min(params.limit ?? 50, 200));
};

export const toDirectoryGeoFeatures = (
  records: readonly CivicDirectoryRecord[],
): readonly GeoFeature[] => {
  return records
    .filter((record) => record.lat !== null && record.lng !== null)
    .map((record) => ({
      type: "Feature",
      geometry: {
        type: "Point",
        coordinates: [record.lng!, record.lat!],
      },
      properties: Object.fromEntries(
        Object.entries(record).filter(([key]) => key !== "lat" && key !== "lng"),
      ),
    }));
};

export const normalizeVacancyStatus = (value: string | null | undefined): EcdaVacancyStatus | null => {
  const normalized = (value ?? "").trim().toLowerCase();
  if (normalized === "") return null;
  if (normalized === "available") return "available";
  if (normalized === "limited") return "limited";
  if (normalized === "full") return "full";
  if (normalized === "not applicable") return "not_applicable";
  return "unknown";
};
