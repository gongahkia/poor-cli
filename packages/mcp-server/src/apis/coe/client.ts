import { queryDatastore } from "../datagov/client.js";

// [Unverified] data.gov.sg COE bidding results dataset resource id.
// Override via SG_API_COE_RESOURCE_ID when upstream rotates the id.
const DEFAULT_COE_RESOURCE_ID = "d_69b3380ad7e51aff3a7dcc84eba52b8a";

const getCoeResourceId = (): string =>
  process.env["SG_API_COE_RESOURCE_ID"]?.trim() || DEFAULT_COE_RESOURCE_ID;

type CoeRawRecord = Readonly<{
  month?: string;
  bidding_no?: string;
  vehicle_class?: string;
  quota?: string;
  bids_success?: string;
  bids_received?: string;
  premium?: string;
}>;

export type CoeNormalizedRecord = {
  readonly month: string | null;
  readonly biddingNo: string | null;
  readonly vehicleClass: string | null;
  readonly quota: number | null;
  readonly bidsSuccess: number | null;
  readonly bidsReceived: number | null;
  readonly premium: number | null;
};

const toNumber = (value: string | undefined): number | null => {
  if (value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
};

export const getCoeBiddingResults = async (
  params: Readonly<{ category?: string | undefined; biddingNo?: string | undefined; limit?: number | undefined }>,
): Promise<readonly CoeNormalizedRecord[]> => {
  const filters: Record<string, string> = {};
  if (params.category !== undefined) filters["vehicle_class"] = params.category;
  if (params.biddingNo !== undefined) filters["bidding_no"] = params.biddingNo;
  const rows = await queryDatastore<CoeRawRecord>(getCoeResourceId(), {
    limit: Math.min(params.limit ?? 50, 200),
    sort: "month desc",
    filters,
  });
  return rows.map((r) => ({
    month: r.month ?? null,
    biddingNo: r.bidding_no ?? null,
    vehicleClass: r.vehicle_class ?? null,
    quota: toNumber(r.quota),
    bidsSuccess: toNumber(r.bids_success),
    bidsReceived: toNumber(r.bids_received),
    premium: toNumber(r.premium),
  }));
};
