import { getHdbResalePrices } from "../apis/hdb/client.js";
import type { HdbNormalizedResaleRecord } from "@dude/shared";

export type ResaleCompareInput = {
  readonly town: string;
  readonly flatType: string;
  readonly askingPriceSgd: number;
  readonly storeyBand?: string | undefined;
  readonly remainingLeaseYears?: number | undefined;
  readonly lookbackMonths?: number | undefined;
};

export type ResaleStats = {
  readonly count: number;
  readonly medianSgd: number | null;
  readonly p25Sgd: number | null;
  readonly p75Sgd: number | null;
  readonly meanSgd: number | null;
  readonly minSgd: number | null;
  readonly maxSgd: number | null;
};

export type ResaleCompareResult = {
  readonly target: ResaleCompareInput;
  readonly observedAt: string;
  readonly windowStart: string;
  readonly stats: ResaleStats;
  readonly variancePercent: number | null;
  readonly verdict: "below_market" | "at_market" | "above_market" | "insufficient_data";
  readonly comparables: readonly HdbNormalizedResaleRecord[];
  readonly assumptions: readonly string[];
};

const monthsAgo = (n: number): string => {
  const d = new Date();
  d.setUTCMonth(d.getUTCMonth() - n);
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
};

const percentile = (values: readonly number[], p: number): number | null => {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const idx = Math.min(sorted.length - 1, Math.max(0, Math.floor(p * (sorted.length - 1))));
  return sorted[idx] ?? null;
};

const filterByStorey = (
  records: readonly HdbNormalizedResaleRecord[],
  storeyBand: string | undefined,
): readonly HdbNormalizedResaleRecord[] => {
  if (storeyBand === undefined) return records;
  const target = storeyBand.trim().toUpperCase();
  return records.filter((r) => (r.storeyRange ?? "").trim().toUpperCase() === target);
};

const filterByLeaseRemaining = (
  records: readonly HdbNormalizedResaleRecord[],
  targetYears: number | undefined,
  toleranceYears: number = 5,
): readonly HdbNormalizedResaleRecord[] => {
  if (targetYears === undefined) return records;
  return records.filter((r) => {
    const lease = r.remainingLease ?? "";
    const match = /(\d+)\s*year/.exec(lease);
    if (match === null || match[1] === undefined) return true;
    const years = Number(match[1]);
    return Math.abs(years - targetYears) <= toleranceYears;
  });
};

export const compareResalePrice = async (input: ResaleCompareInput): Promise<ResaleCompareResult> => {
  const lookback = input.lookbackMonths ?? 12;
  const startMonth = monthsAgo(lookback);
  const observedAt = new Date().toISOString();

  const raw = await getHdbResalePrices({
    town: input.town,
    flatType: input.flatType,
    startMonth,
    limit: 200,
  });

  const filtered = filterByLeaseRemaining(filterByStorey(raw, input.storeyBand), input.remainingLeaseYears);
  const prices = filtered
    .map((r) => r.resalePrice)
    .filter((p): p is number => typeof p === "number" && Number.isFinite(p));

  const median = percentile(prices, 0.5);
  const p25 = percentile(prices, 0.25);
  const p75 = percentile(prices, 0.75);
  const mean = prices.length === 0 ? null : prices.reduce((a, b) => a + b, 0) / prices.length;
  const min = prices.length === 0 ? null : Math.min(...prices);
  const max = prices.length === 0 ? null : Math.max(...prices);

  const variancePercent = median === null
    ? null
    : Math.round(((input.askingPriceSgd - median) / median) * 10000) / 100;

  let verdict: ResaleCompareResult["verdict"] = "insufficient_data";
  if (prices.length < 3) {
    verdict = "insufficient_data";
  } else if (variancePercent === null) {
    verdict = "insufficient_data";
  } else if (variancePercent < -3) {
    verdict = "below_market";
  } else if (variancePercent > 3) {
    verdict = "above_market";
  } else {
    verdict = "at_market";
  }

  return {
    target: input,
    observedAt,
    windowStart: startMonth,
    stats: {
      count: prices.length,
      medianSgd: median === null ? null : Math.round(median),
      p25Sgd: p25 === null ? null : Math.round(p25),
      p75Sgd: p75 === null ? null : Math.round(p75),
      meanSgd: mean === null ? null : Math.round(mean),
      minSgd: min === null ? null : Math.round(min),
      maxSgd: max === null ? null : Math.round(max),
    },
    variancePercent,
    verdict,
    comparables: filtered.slice(0, 20),
    assumptions: [
      "Sample is curated from data.gov.sg HDB resale dataset over the lookback window.",
      "Storey filter is exact-match; lease filter uses ±5y tolerance.",
      "At-market threshold is ±3% from median; verdict requires >=3 samples.",
      "Floor area normalization, COV, and renovation premia are not modelled.",
    ],
  };
};
