import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ToolResult } from "@swee-sg/shared";

vi.mock("../../apis/nlb/client.js", () => ({ getNlbLibraries: vi.fn() }));
vi.mock("../../apis/hawker/closures-client.js", () => ({ getHawkerClosures: vi.fn() }));
vi.mock("../../apis/law/client.js", () => ({ searchSingaporeLaw: vi.fn() }));

import { getNlbLibraries } from "../../apis/nlb/client.js";
import { getHawkerClosures } from "../../apis/hawker/closures-client.js";
import { searchSingaporeLaw } from "../../apis/law/client.js";
import { handleNlbLibraries } from "../nlb-tools.js";
import { handleHawkerClosures } from "../hawker-tools.js";
import { handleLawSearch } from "../law-tools.js";

const records = (r: ToolResult): Record<string, unknown>[] =>
  (r.structuredContent as { records: Record<string, unknown>[] }).records;

describe("Bundle E new families", () => {
  beforeEach(() => {
    vi.mocked(getNlbLibraries).mockReset();
    vi.mocked(getHawkerClosures).mockReset();
    vi.mocked(searchSingaporeLaw).mockReset();
  });

  it("sg_nlb_libraries returns library records", async () => {
    vi.mocked(getNlbLibraries).mockResolvedValue([
      { name: "Tampines Regional Library", address: "21 Tampines Walk", postalCode: "528523", region: "East", telephone: "68401510", lat: 1.354, lng: 103.945 },
    ] as never);
    const result = await handleNlbLibraries({ region: "East", format: "json" });
    expect(records(result)[0]).toMatchObject({ name: "Tampines Regional Library", region: "East" });
  });

  it("sg_hawker_closures returns window records", async () => {
    vi.mocked(getHawkerClosures).mockResolvedValue([
      { centre: "Maxwell Food Centre", period: "Q1 cleaning", startDate: "2026-01-15", endDate: "2026-01-20", reason: "quarterly cleaning" },
    ] as never);
    const result = await handleHawkerClosures({ centre: "Maxwell", format: "json" });
    expect(records(result)[0]).toMatchObject({ centre: "Maxwell Food Centre", period: "Q1 cleaning" });
  });

  it("sg_law_search returns search hits with disclaimer", async () => {
    vi.mocked(searchSingaporeLaw).mockResolvedValue([
      { title: "Personal Data Protection Act 2012", url: "https://sso.agc.gov.sg/Act/PDPA2012", snippet: "An Act to govern...", documentType: "Act" },
    ] as never);
    const result = await handleLawSearch({ query: "personal data", format: "json" });
    expect(records(result)[0]).toMatchObject({ title: "Personal Data Protection Act 2012" });
    const sc = result.structuredContent as { disclaimer: string; sourceUrl: string };
    expect(sc.disclaimer).toContain("not legal advice");
    expect(sc.sourceUrl).toBe("https://sso.agc.gov.sg/");
  });
});
