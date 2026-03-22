import type { IndicatorQuery, ComparisonResult } from "@sg-apis/shared";
import { getTimeSeries } from "./client.js";

export const compareIndicators = async (
  queries: readonly IndicatorQuery[],
  startYear?: number,
  endYear?: number,
): Promise<ComparisonResult> => {
  const start = startYear ?? 2010;
  const end = endYear ?? new Date().getFullYear();

  const results = await Promise.allSettled(
    queries.map((q) => getTimeSeries(q.tableId, q.indicator, start, end)),
  );

  const allPeriods = new Set<string>();
  const seriesData: { label: string; data: Map<string, number> }[] = [];

  for (let i = 0; i < queries.length; i++) {
    const query = queries[i]!;
    const result = results[i]!;
    const dataMap = new Map<string, number>();

    if (result.status === "fulfilled") {
      for (const row of result.value) {
        allPeriods.add(row.period);
        dataMap.set(row.period, row.value);
      }
    }

    seriesData.push({ label: query.label, data: dataMap });
  }

  const periods = Array.from(allPeriods).sort();

  return {
    periods,
    series: seriesData.map((s) => ({
      label: s.label,
      values: periods.map((p) => s.data.get(p) ?? null),
    })),
  };
};
