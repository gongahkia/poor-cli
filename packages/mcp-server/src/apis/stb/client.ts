import { queryDatastore } from "../datagov/client.js";

const VISITOR_ARRIVALS_RESOURCE_ID = "d_fce47a3fb4e3e83e6725450f2c8c3c4f";

type VisitorRawRecord = {
  readonly year: string;
  readonly month: string;
  readonly country: string;
  readonly no_of_visitor_arrivals: string;
};

export type VisitorNormalizedRecord = {
  readonly year: string;
  readonly month: string;
  readonly country: string;
  readonly visitorArrivals: number | null;
};

export const getVisitorArrivals = async (
  params: { readonly country?: string | undefined; readonly year?: string | undefined; readonly limit?: number | undefined },
): Promise<readonly VisitorNormalizedRecord[]> => {
  const filters: Record<string, string> = {};
  if (params.country !== undefined) filters["country"] = params.country;
  if (params.year !== undefined) filters["year"] = params.year;
  const rows = await queryDatastore<VisitorRawRecord>(VISITOR_ARRIVALS_RESOURCE_ID, {
    limit: Math.min(params.limit ?? 50, 200),
    sort: "year desc",
    filters,
  });
  return rows.map((r) => ({
    year: r.year,
    month: r.month,
    country: r.country,
    visitorArrivals: Number.isFinite(Number(r.no_of_visitor_arrivals)) ? Number(r.no_of_visitor_arrivals) : null,
  }));
};
