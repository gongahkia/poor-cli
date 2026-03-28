import { beforeEach, describe, expect, it, vi } from "vitest";
import { MasDataset } from "@sg-apis/shared";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

vi.mock("@sg-apis/shared", async () => {
  const actual = await vi.importActual<typeof import("@sg-apis/shared")>("@sg-apis/shared");
  return {
    ...actual,
    getRateLimiter: () => ({ acquire: vi.fn().mockResolvedValue(undefined) }),
  };
});

vi.mock("../../../middleware/cache-middleware.js", () => ({
  withCache: vi.fn(async (_key: string, _ttl: number, fetcher: () => Promise<unknown>) => ({
    data: await fetcher(),
    cached: false,
  })),
  buildCacheKey: vi.fn((...args: unknown[]) => args.join(":")),
}));

import { getResourceId, query } from "../client.js";

const htmlResponse = (body: string, cookie = "MASCOOKIE=abc; Path=/") => ({
  ok: true,
  text: async () => body,
  headers: new Headers({
    "content-type": "text/html",
    "set-cookie": cookie,
  }),
});

const csvResponse = (body: string) => ({
  ok: true,
  text: async () => body,
  headers: new Headers({
    "content-type": "text/csv; charset=utf-8",
  }),
});

const EXCHANGE_HTML = `
  <input id="__VIEWSTATE" value="vs" />
  <input id="__EVENTVALIDATION" value="ev" />
  <input id="__VIEWSTATEGENERATOR" value="vg" />
  <select id="ContentPlaceHolder1_StartYearDropDownList"><option value="2025">2025</option></select>
  <select id="ContentPlaceHolder1_EndYearDropDownList"><option value="2026">2026</option></select>
  <select id="ContentPlaceHolder1_StartMonthDropDownList"><option value="1">1</option></select>
  <select id="ContentPlaceHolder1_EndMonthDropDownList"><option value="12">12</option></select>
  <select id="ContentPlaceHolder1_FrequencyDropDownList"><option value="M">M</option></select>
  <input name="ctl00$ContentPlaceHolder1$EndOfPeriodPerUnitCheckBoxList$0" type="checkbox" />
`;

const INTEREST_HTML = `
  <input id="__VIEWSTATE" value="vs" />
  <input id="__EVENTVALIDATION" value="ev" />
  <input id="__VIEWSTATEGENERATOR" value="vg" />
  <select id="ContentPlaceHolder1_StartYearDropDownList"><option value="2025">2025</option></select>
  <select id="ContentPlaceHolder1_EndYearDropDownList"><option value="2026">2026</option></select>
  <select id="ContentPlaceHolder1_StartMonthDropDownList"><option value="1">1</option></select>
  <select id="ContentPlaceHolder1_EndMonthDropDownList"><option value="12">12</option></select>
`;

const BANKING_HTML = `
  <input id="__VIEWSTATE" value="vs" />
  <input id="__EVENTVALIDATION" value="ev" />
  <input id="__VIEWSTATEGENERATOR" value="vg" />
  <select id="ctl00_ContentPlaceHolder1_StartYearDropDownList"><option value="2025">2025</option></select>
  <select id="ctl00_ContentPlaceHolder1_EndYearDropDownList"><option value="2026">2026</option></select>
  <select id="ctl00_ContentPlaceHolder1_StartMonthDropDownList"><option value="1">1</option></select>
  <select id="ctl00_ContentPlaceHolder1_EndMonthDropDownList"><option value="12">12</option></select>
`;

describe("MAS client", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("downloads and parses exchange-rate CSV data", async () => {
    mockFetch
      .mockResolvedValueOnce(htmlResponse(EXCHANGE_HTML))
      .mockResolvedValueOnce(csvResponse([
        "Exchange Rates (Monthly)",
        "End of Period,,,S$ Per Unit of US Dollar",
        "2026,Mar,,1.35",
        "2026,Feb,,1.34",
      ].join("\n")));

    const records = await query(MasDataset.EXCHANGE_RATES, { limit: 1 });

    expect(records).toEqual([
      expect.objectContaining({
        end_of_day: "2026-03-01",
        usd_sgd: 1.35,
      }),
    ]);
    expect(mockFetch).toHaveBeenNthCalledWith(
      2,
      "https://eservices.mas.gov.sg/statistics/msb/exchangerates.aspx",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining("ctl00%24ContentPlaceHolder1%24DownloadButton=Download"),
      }),
    );
  });

  it("downloads and parses SORA CSV data", async () => {
    mockFetch
      .mockResolvedValueOnce(htmlResponse(INTEREST_HTML))
      .mockResolvedValueOnce(csvResponse([
        "Domestic Interest Rates (Daily)",
        "SORA Value Date,,,SORA Publication Date,SORA,Compound SORA - 3 month",
        "2026,Mar,26,26 Mar 2026,2.55,2.75",
      ].join("\n")));

    const records = await query(MasDataset.INTEREST_RATES_SORA, { date: "2026-03-26" });

    expect(records).toEqual([
      expect.objectContaining({
        end_of_day: "2026-03-26",
        sora: 2.55,
        sora_3m: 2.75,
      }),
    ]);
    expect(mockFetch).toHaveBeenNthCalledWith(
      2,
      "https://eservices.mas.gov.sg/statistics/dir/DomesticInterestRates.aspx",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining("ctl00%24ContentPlaceHolder1%24Button2=Download"),
      }),
    );
  });

  it("downloads and parses banking CSV data", async () => {
    mockFetch
      .mockResolvedValueOnce(htmlResponse(BANKING_HTML))
      .mockResolvedValueOnce(csvResponse([
        "\"END OF PERIOD\",\"TOTAL ASSETS/LIABILITIES\",\"ASSETS - LOANS AND ADVANCES INCLUDING BILLS FINANCING @\",\"LIABILITIES - DEPOSITS AND BALANCES OF NON-BANK CUSTOMERS #\"",
        "\"2026 Mar\",3012125.5,1306480.9,1529980.9",
      ].join("\n")));

    const records = await query(MasDataset.BANKING_STATS, { limit: 1 });

    expect(records).toEqual([
      expect.objectContaining({
        end_of_day: "2026-03-01",
        total_assets: 3012125.5,
        total_loans: 1306480.9,
        total_deposits: 1529980.9,
      }),
    ]);
  });

  it("accepts both MAS dataset keys and dataset values", () => {
    expect(getResourceId("EXCHANGE_RATES")).toBe(MasDataset.EXCHANGE_RATES);
    expect(getResourceId(MasDataset.EXCHANGE_RATES)).toBe(MasDataset.EXCHANGE_RATES);
  });

  it("throws on unknown dataset", () => {
    expect(() => getResourceId("UNKNOWN_DATASET")).toThrow("Unknown MAS dataset");
  });

  it("fails when MAS does not return CSV content", async () => {
    mockFetch
      .mockResolvedValueOnce(htmlResponse(EXCHANGE_HTML))
      .mockResolvedValueOnce({
        ok: true,
        text: async () => "<html>not csv</html>",
        headers: new Headers({ "content-type": "text/html" }),
      });

    await expect(query(MasDataset.EXCHANGE_RATES)).rejects.toThrow("MAS download did not return CSV content");
  });
});
