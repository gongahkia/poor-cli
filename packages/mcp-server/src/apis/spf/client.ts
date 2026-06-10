import { queryDatastore } from "../datagov/client.js";

// [Unverified] data.gov.sg SPF annual crime statistics dataset resource id.
// Override via SG_API_SPF_CRIME_RESOURCE_ID if upstream rotates.
const DEFAULT_SPF_CRIME_RESOURCE_ID = "d_af8cf88b5ea24d52c1f4a73f16c94c16";

const getSpfCrimeResourceId = (): string =>
  process.env["SG_API_SPF_CRIME_RESOURCE_ID"]?.trim() || DEFAULT_SPF_CRIME_RESOURCE_ID;

type SpfCrimeRawRecord = Readonly<{
  year?: string;
  offence_category?: string;
  offence?: string;
  cases?: string;
}>;

export type SpfCrimeNormalizedRecord = {
  readonly year: string | null;
  readonly offenceCategory: string | null;
  readonly offence: string | null;
  readonly cases: number | null;
};

export const getSpfCrimeStats = async (
  params: Readonly<{ offenceCategory?: string | undefined; year?: string | undefined; limit?: number | undefined }>,
): Promise<readonly SpfCrimeNormalizedRecord[]> => {
  const filters: Record<string, string> = {};
  if (params.offenceCategory !== undefined) filters["offence_category"] = params.offenceCategory;
  if (params.year !== undefined) filters["year"] = params.year;
  const rows = await queryDatastore<SpfCrimeRawRecord>(getSpfCrimeResourceId(), {
    limit: Math.min(params.limit ?? 50, 200),
    sort: "year desc",
    filters,
  });
  return rows.map((r) => {
    const n = r.cases === undefined ? null : Number(r.cases);
    return {
      year: r.year ?? null,
      offenceCategory: r.offence_category ?? null,
      offence: r.offence ?? null,
      cases: n === null || !Number.isFinite(n) ? null : n,
    };
  });
};
