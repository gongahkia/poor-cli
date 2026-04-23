import { queryDatastore } from "../datagov/client.js";

// [Unverified] data.gov.sg NLB library directory resource id.
// Override via SG_API_NLB_LIBRARIES_RESOURCE_ID if upstream rotates.
const DEFAULT_NLB_LIBRARIES_RESOURCE_ID = "d_8d5ff78ad2f0beb4b03c6a4e9f1b2f0c";

const getNlbLibrariesResourceId = (): string =>
  process.env["SG_API_NLB_LIBRARIES_RESOURCE_ID"]?.trim() || DEFAULT_NLB_LIBRARIES_RESOURCE_ID;

type NlbLibraryRaw = Readonly<{
  library_name?: string;
  address?: string;
  postal_code?: string;
  region?: string;
  telephone?: string;
  latitude?: string;
  longitude?: string;
}>;

export type NlbLibraryRecord = {
  readonly name: string | null;
  readonly address: string | null;
  readonly postalCode: string | null;
  readonly region: string | null;
  readonly telephone: string | null;
  readonly lat: number | null;
  readonly lng: number | null;
};

const toNumber = (value: string | undefined): number | null => {
  if (value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
};

export const getNlbLibraries = async (
  params: Readonly<{ name?: string | undefined; region?: string | undefined; postalCode?: string | undefined; limit?: number | undefined }>,
): Promise<readonly NlbLibraryRecord[]> => {
  const filters: Record<string, string> = {};
  if (params.region !== undefined) filters["region"] = params.region;
  if (params.postalCode !== undefined) filters["postal_code"] = params.postalCode;
  const rows = await queryDatastore<NlbLibraryRaw>(getNlbLibrariesResourceId(), {
    limit: Math.min(params.limit ?? 50, 200),
    filters,
  });
  const needle = params.name?.trim().toLowerCase();
  return rows
    .filter((r) => needle === undefined || (r.library_name ?? "").toLowerCase().includes(needle))
    .map((r) => ({
      name: r.library_name ?? null,
      address: r.address ?? null,
      postalCode: r.postal_code ?? null,
      region: r.region ?? null,
      telephone: r.telephone ?? null,
      lat: toNumber(r.latitude),
      lng: toNumber(r.longitude),
    }));
};
