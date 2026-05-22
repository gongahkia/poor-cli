import { formatResponse, VisualizeInputSchema, VisualizeSchema, CrossDatasetSchema, resolveOutputFormat } from "@swee-sg/shared";
import type { OutputFormat, ToolResult } from "@swee-sg/shared";
import { getTimeSeries } from "../apis/singstat/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const SPARK_CHARS = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"] as const;

const renderSparkline = (values: readonly number[], width?: number): string => {
  const cap = width === undefined ? values.length : Math.min(values.length, width);
  const slice = values.slice(-cap);
  const min = Math.min(...slice);
  const max = Math.max(...slice);
  const range = max - min;
  if (range === 0 || !Number.isFinite(range)) {
    return SPARK_CHARS[Math.floor(SPARK_CHARS.length / 2)]!.repeat(slice.length);
  }
  return slice
    .map((v) => {
      const idx = Math.min(SPARK_CHARS.length - 1, Math.max(0, Math.round(((v - min) / range) * (SPARK_CHARS.length - 1))));
      return SPARK_CHARS[idx]!;
    })
    .join("");
};

const summarizeSeries = (values: readonly number[]): {
  readonly count: number;
  readonly min: number;
  readonly max: number;
  readonly mean: number;
  readonly first: number;
  readonly last: number;
  readonly deltaPercent: number | null;
} => {
  const first = values[0]!;
  const last = values[values.length - 1]!;
  const sum = values.reduce((s, v) => s + v, 0);
  const deltaPercent = first === 0 ? null : Math.round(((last - first) / Math.abs(first)) * 10000) / 100;
  return {
    count: values.length,
    min: Math.min(...values),
    max: Math.max(...values),
    mean: Math.round((sum / values.length) * 10000) / 10000,
    first,
    last,
    deltaPercent,
  };
};

export const handleVisualize = async (
  params: Readonly<{
    values?: readonly number[] | undefined;
    labels?: readonly string[] | undefined;
    tableId?: string | undefined;
    indicator?: string | undefined;
    startYear?: number | undefined;
    endYear?: number | undefined;
    width?: number | undefined;
    format?: "json" | "markdown" | undefined;
  }>,
): Promise<ToolResult> => {
  let values: readonly number[];
  let labels: readonly string[] | undefined = params.labels;
  let source: string;

  if (params.values !== undefined) {
    values = params.values;
    source = "inline";
  } else {
    const startYear = params.startYear ?? new Date().getFullYear() - 5;
    const endYear = params.endYear ?? new Date().getFullYear();
    const rows = await getTimeSeries(params.tableId!, params.indicator!, startYear, endYear);
    const numeric = rows
      .map((r) => ({ period: String(r["period"] ?? ""), value: Number(r["value"]) }))
      .filter((r) => Number.isFinite(r.value));
    if (numeric.length < 2) {
      throw new Error(`SingStat time series for ${params.tableId}:${params.indicator} returned fewer than 2 numeric points.`);
    }
    values = numeric.map((r) => r.value);
    labels = numeric.map((r) => r.period);
    source = `singstat:${params.tableId}:${params.indicator}`;
  }

  const sparkline = renderSparkline(values, params.width);
  const stats = summarizeSeries(values);
  const format = resolveOutputFormat(params.format) === "markdown" ? "markdown" : "json";
  const text = format === "markdown"
    ? `# Sparkline\n\n\`${sparkline}\`\n\nSource: ${source}\n\nCount: ${stats.count} | Min: ${stats.min} | Max: ${stats.max} | Mean: ${stats.mean} | Δ: ${stats.deltaPercent ?? "n/a"}%`
    : formatResponse({ sparkline, stats, source } as unknown as Record<string, unknown>, "json");

  return {
    content: [{ type: "text", text }],
    structuredContent: {
      sparkline,
      stats,
      source,
      ...(labels === undefined ? {} : { labels }),
      values,
    },
  };
};

const pearsonCorrelation = (a: readonly number[], b: readonly number[]): number | null => {
  if (a.length !== b.length || a.length < 2) return null;
  const n = a.length;
  const meanA = a.reduce((s, v) => s + v, 0) / n;
  const meanB = b.reduce((s, v) => s + v, 0) / n;
  let num = 0;
  let denA = 0;
  let denB = 0;
  for (let i = 0; i < n; i++) {
    const da = a[i]! - meanA;
    const db = b[i]! - meanB;
    num += da * db;
    denA += da * da;
    denB += db * db;
  }
  const den = Math.sqrt(denA * denB);
  if (den === 0) return null;
  return Math.round((num / den) * 10000) / 10000;
};

export const handleCrossDataset = async (
  params: Readonly<{
    leftTableId: string;
    leftIndicator: string;
    leftLabel: string;
    rightTableId: string;
    rightIndicator: string;
    rightLabel: string;
    startYear?: number | undefined;
    endYear?: number | undefined;
    format?: OutputFormat | undefined;
  }>,
): Promise<ToolResult> => {
  const startYear = params.startYear ?? new Date().getFullYear() - 5;
  const endYear = params.endYear ?? new Date().getFullYear();

  const [left, right] = await Promise.all([
    getTimeSeries(params.leftTableId, params.leftIndicator, startYear, endYear),
    getTimeSeries(params.rightTableId, params.rightIndicator, startYear, endYear),
  ]);

  const leftByPeriod = new Map(left.map((r) => [String(r["period"] ?? ""), Number(r["value"])]));
  const rightByPeriod = new Map(right.map((r) => [String(r["period"] ?? ""), Number(r["value"])]));
  const periods = Array.from(leftByPeriod.keys()).filter((p) => rightByPeriod.has(p)).sort();

  const rows = periods.map((period) => ({
    period,
    [params.leftLabel]: leftByPeriod.get(period) ?? null,
    [params.rightLabel]: rightByPeriod.get(period) ?? null,
  }));

  const leftValues: number[] = [];
  const rightValues: number[] = [];
  for (const period of periods) {
    const lv = leftByPeriod.get(period);
    const rv = rightByPeriod.get(period);
    if (typeof lv === "number" && Number.isFinite(lv) && typeof rv === "number" && Number.isFinite(rv)) {
      leftValues.push(lv);
      rightValues.push(rv);
    }
  }
  const correlation = pearsonCorrelation(leftValues, rightValues);
  const leftSpark = leftValues.length >= 2 ? renderSparkline(leftValues) : null;
  const rightSpark = rightValues.length >= 2 ? renderSparkline(rightValues) : null;

  const format = resolveOutputFormat(params.format);
  const text = formatResponse(rows as unknown as Record<string, unknown>[], format);
  return {
    content: [{ type: "text", text }],
    structuredContent: {
      records: rows,
      pairedCount: leftValues.length,
      correlation,
      leftSparkline: leftSpark,
      rightSparkline: rightSpark,
      leftLabel: params.leftLabel,
      rightLabel: params.rightLabel,
    },
  };
};

export const visualizeToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_visualize",
    description: "Deterministic ASCII sparkline over a numeric array or a SingStat time series (tableId + indicator).",
    surface: "canonical",
    inputSchema: VisualizeInputSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => handleVisualize(VisualizeSchema.parse(input)),
  },
  {
    name: "sg_cross_dataset",
    description: "Bounded two-SingStat-series comparison with joined period table, pairwise Pearson correlation, and sparklines.",
    surface: "canonical",
    inputSchema: CrossDatasetSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => handleCrossDataset(CrossDatasetSchema.parse(input)),
  },
];
