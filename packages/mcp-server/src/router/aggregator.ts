import type { ApiError } from "@sg-apis/shared";
import { formatResponse } from "@sg-apis/shared";
import type { OutputFormat } from "@sg-apis/shared";

export type StepResult = {
  readonly tool: string;
  readonly data: unknown;
  readonly cached: boolean;
  readonly error?: ApiError;
};

export type AggregatedResult = {
  readonly data: unknown;
  readonly sources: readonly string[];
  readonly cached: readonly boolean[];
  readonly errors: readonly ApiError[];
};

export const aggregateResults = (results: readonly StepResult[]): AggregatedResult => {
  const successful = results.filter((r) => r.error === undefined);
  const errors = results.filter((r) => r.error !== undefined).map((r) => r.error!);
  const sources = successful.map((r) => r.tool);
  const cached = successful.map((r) => r.cached);

  if (successful.length === 0) {
    return { data: null, sources: [], cached: [], errors };
  }

  if (successful.length === 1) {
    return { data: successful[0]!.data, sources, cached, errors };
  }

  // Merge multiple results
  const merged: Record<string, unknown> = {};
  for (const result of successful) {
    merged[result.tool] = result.data;
  }

  return { data: merged, sources, cached, errors };
};

export const formatAggregated = (result: AggregatedResult, format: OutputFormat): string => {
  const parts: string[] = [];

  if (result.sources.length > 0) {
    parts.push(`**Sources:** ${result.sources.join(", ")}`);
  }

  if (result.data !== null) {
    parts.push(formatResponse(result.data as Record<string, unknown>[] | Record<string, unknown>, format));
  }

  for (const error of result.errors) {
    parts.push(`\n> Note: ${error.apiName} query failed: ${error.message}`);
  }

  return parts.join("\n\n");
};
