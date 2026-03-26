import { queryDatastore } from "../datagov/client.js";

const PARKS_RESOURCE_ID = "d_0e3e8f5918443e82e4210e9e94a684d3";

type ParkRawRecord = {
  readonly name: string;
  readonly description: string;
  readonly hyperlink: string;
};

export type ParkNormalizedRecord = {
  readonly name: string;
  readonly description: string;
  readonly url: string;
};

export const getParks = async (
  params: { readonly name?: string; readonly limit?: number },
): Promise<readonly ParkNormalizedRecord[]> => {
  const filters: Record<string, string> = {};
  if (params.name !== undefined) filters["name"] = params.name;
  const rows = await queryDatastore<ParkRawRecord>(PARKS_RESOURCE_ID, {
    limit: Math.min(params.limit ?? 50, 200),
    filters,
  });
  return rows.map((r) => ({
    name: r.name,
    description: r.description ?? "",
    url: r.hyperlink ?? "",
  }));
};
