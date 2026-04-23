import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ToolResult } from "@sg-apis/shared";

vi.mock("../../apis/singstat/client.js", () => ({
  getTableData: vi.fn(),
  searchDatasets: vi.fn(),
  getTimeSeries: vi.fn(),
}));

import { getTimeSeries } from "../../apis/singstat/client.js";
import { handleVisualize, handleCrossDataset } from "../visualize-tools.js";

const structured = <T>(r: ToolResult): T =>
  r.structuredContent as unknown as T;

describe("sg_visualize", () => {
  beforeEach(() => {
    vi.mocked(getTimeSeries).mockReset();
  });

  it("renders a sparkline from inline numeric values", async () => {
    const result = await handleVisualize({ values: [1, 2, 3, 4, 5, 6, 7, 8], format: "json" });
    const sc = structured<{ sparkline: string; stats: { count: number; min: number; max: number; deltaPercent: number | null } }>(result);
    expect(sc.sparkline).toHaveLength(8);
    expect(sc.stats.count).toBe(8);
    expect(sc.stats.min).toBe(1);
    expect(sc.stats.max).toBe(8);
    expect(sc.stats.deltaPercent).toBe(700);
  });

  it("fetches a SingStat time series when tableId+indicator supplied", async () => {
    vi.mocked(getTimeSeries).mockResolvedValue([
      { period: "2024", value: 100 },
      { period: "2025", value: 110 },
      { period: "2026", value: 125 },
    ] as never);
    const result = await handleVisualize({ tableId: "M015631", indicator: "GDP", format: "json" });
    const sc = structured<{ source: string; stats: { count: number } }>(result);
    expect(sc.source).toContain("singstat:M015631:GDP");
    expect(sc.stats.count).toBe(3);
    expect(getTimeSeries).toHaveBeenCalledOnce();
  });

  it("renders markdown output with sparkline and summary line", async () => {
    const result = await handleVisualize({ values: [10, 20, 30], format: "markdown" });
    const text = result.content.find((item): item is Extract<ToolResult["content"][number], { type: "text" }> => item.type === "text")?.text ?? "";
    expect(text).toContain("Sparkline");
    expect(text).toMatch(/Count: 3/);
  });
});

describe("sg_cross_dataset", () => {
  beforeEach(() => {
    vi.mocked(getTimeSeries).mockReset();
  });

  it("joins two SingStat series by period and reports correlation", async () => {
    vi.mocked(getTimeSeries)
      .mockResolvedValueOnce([
        { period: "2024", value: 1 },
        { period: "2025", value: 2 },
        { period: "2026", value: 3 },
      ] as never)
      .mockResolvedValueOnce([
        { period: "2024", value: 10 },
        { period: "2025", value: 20 },
        { period: "2026", value: 30 },
      ] as never);
    const result = await handleCrossDataset({
      leftTableId: "M_A",
      leftIndicator: "A",
      leftLabel: "A",
      rightTableId: "M_B",
      rightIndicator: "B",
      rightLabel: "B",
      startYear: 2024,
      endYear: 2026,
      format: "json",
    });
    const sc = structured<{ records: Record<string, unknown>[]; correlation: number | null; pairedCount: number }>(result);
    expect(sc.records).toHaveLength(3);
    expect(sc.pairedCount).toBe(3);
    expect(sc.correlation).toBe(1); // perfectly linear
  });
});
