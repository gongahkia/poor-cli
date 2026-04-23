import { queryDatastore } from "../datagov/client.js";

// [Unverified] data.gov.sg hawker-centre closure / cleaning schedule resource id.
// Override via SG_API_HAWKER_CLOSURES_RESOURCE_ID if upstream rotates.
const DEFAULT_HAWKER_CLOSURES_RESOURCE_ID = "d_7f6a0baff4e8e5b72a6d7d5c63a1c0d3";

const getResourceId = (): string =>
  process.env["SG_API_HAWKER_CLOSURES_RESOURCE_ID"]?.trim() || DEFAULT_HAWKER_CLOSURES_RESOURCE_ID;

type RawClosure = Readonly<{
  name?: string;
  q1_cleaningstartdate?: string;
  q1_cleaningenddate?: string;
  q2_cleaningstartdate?: string;
  q2_cleaningenddate?: string;
  q3_cleaningstartdate?: string;
  q3_cleaningenddate?: string;
  q4_cleaningstartdate?: string;
  q4_cleaningenddate?: string;
  other_works_startdate?: string;
  other_works_enddate?: string;
  remarks_other_works?: string;
}>;

export type HawkerClosureWindow = {
  readonly centre: string | null;
  readonly period: string;
  readonly startDate: string | null;
  readonly endDate: string | null;
  readonly reason: string;
};

const WINDOWS: readonly [keyof RawClosure, keyof RawClosure, string, string][] = [
  ["q1_cleaningstartdate", "q1_cleaningenddate", "Q1 cleaning", "quarterly cleaning"],
  ["q2_cleaningstartdate", "q2_cleaningenddate", "Q2 cleaning", "quarterly cleaning"],
  ["q3_cleaningstartdate", "q3_cleaningenddate", "Q3 cleaning", "quarterly cleaning"],
  ["q4_cleaningstartdate", "q4_cleaningenddate", "Q4 cleaning", "quarterly cleaning"],
  ["other_works_startdate", "other_works_enddate", "Other works", "other works"],
];

const inRange = (value: string | null, startDate?: string, endDate?: string): boolean => {
  if (value === null) return false;
  if (startDate !== undefined && value < startDate) return false;
  if (endDate !== undefined && value > endDate) return false;
  return true;
};

export const getHawkerClosures = async (
  params: Readonly<{ centre?: string | undefined; startDate?: string | undefined; endDate?: string | undefined; limit?: number | undefined }>,
): Promise<readonly HawkerClosureWindow[]> => {
  const filters: Record<string, string> = {};
  const rows = await queryDatastore<RawClosure>(getResourceId(), {
    limit: Math.min(params.limit ?? 200, 500),
    filters,
  });
  const centreNeedle = params.centre?.trim().toLowerCase();
  const records: HawkerClosureWindow[] = [];
  for (const row of rows) {
    const name = row.name ?? null;
    if (centreNeedle !== undefined && !(name ?? "").toLowerCase().includes(centreNeedle)) continue;
    for (const [startField, endField, label, reason] of WINDOWS) {
      const start = (row[startField] ?? "") || null;
      const end = (row[endField] ?? "") || null;
      if (start === null && end === null) continue;
      if (params.startDate !== undefined || params.endDate !== undefined) {
        if (!inRange(start, params.startDate, params.endDate) && !inRange(end, params.startDate, params.endDate)) continue;
      }
      records.push({
        centre: name,
        period: label,
        startDate: start,
        endDate: end,
        reason: label === "Other works" && typeof row.remarks_other_works === "string"
          ? row.remarks_other_works
          : reason,
      });
    }
  }
  return records;
};
