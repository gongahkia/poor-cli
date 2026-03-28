import { ApiError, MasDataset, getRateLimiter, getTimeout } from "@sg-apis/shared";
import type { MasDatasetKey, MasQueryParams, MasRecord } from "@sg-apis/shared";
import { withCache, buildCacheKey } from "../../middleware/cache-middleware.js";

type MasDatasetSlug = typeof MasDataset[MasDatasetKey];

type MasDownloadConfig = Readonly<{
  dataset: MasDatasetSlug;
  pageUrl: string;
  submitName: string;
  selectNames: readonly {
    requestName: string;
    htmlId: string;
    resolveValue: (options: readonly string[]) => string;
  }[];
  resolveCheckboxNames: (html: string) => readonly string[];
  parseCsv: (csvText: string) => readonly MasRecord[];
}>;

const MAS_PAGE_ORIGIN = "https://eservices.mas.gov.sg";
const MONTH_LOOKUP: Readonly<Record<string, string>> = {
  Jan: "01",
  Feb: "02",
  Mar: "03",
  Apr: "04",
  May: "05",
  Jun: "06",
  Jul: "07",
  Aug: "08",
  Sep: "09",
  Oct: "10",
  Nov: "11",
  Dec: "12",
};

export const getResourceId = (dataset: string): string => {
  const id = MasDataset[dataset as keyof typeof MasDataset];
  if (typeof id === "string") {
    return id;
  }
  if (Object.values(MasDataset).includes(dataset as MasDatasetSlug)) {
    return dataset;
  }
  if (id === undefined) {
    throw new ApiError({
      apiName: "mas",
      statusCode: 400,
      message: `Unknown MAS dataset: ${dataset}`,
      retryable: false,
    });
  }
  return id;
};

const toCookieHeader = (headers: Headers): string | null => {
  const nodeHeaders = headers as Headers & { getSetCookie?: () => string[] };
  const cookies = typeof nodeHeaders.getSetCookie === "function"
    ? nodeHeaders.getSetCookie()
    : [];
  if (cookies.length === 0) {
    const singleCookie = headers.get("set-cookie");
    if (singleCookie === null || singleCookie.trim() === "") {
      return null;
    }
    return singleCookie.split(",").map((part) => part.split(";")[0]?.trim() ?? "").filter((part) => part !== "").join("; ");
  }
  return cookies.map((cookie) => cookie.split(";")[0]?.trim() ?? "").filter((cookie) => cookie !== "").join("; ");
};

const fetchMasText = async (
  url: string,
  init: RequestInit,
  errorMessage: string,
): Promise<{ readonly body: string; readonly headers: Headers }> => {
  await getRateLimiter("mas").acquire();

  const controller = new AbortController();
  const timeout = Math.min(getTimeout("mas"), 30000);
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      ...init,
      signal: controller.signal,
    });

    const body = await response.text();
    if (!response.ok) {
      throw new ApiError({
        apiName: "mas",
        statusCode: response.status,
        message: `${errorMessage}: ${response.statusText}`,
        retryable: response.status >= 500,
        details: body,
      });
    }

    return { body, headers: response.headers };
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError({
        apiName: "mas",
        statusCode: 408,
        message: `MAS request timed out after ${timeout}ms`,
        retryable: true,
      });
    }
    throw new ApiError({
      apiName: "mas",
      statusCode: 0,
      message: `${errorMessage}: ${error instanceof Error ? error.message : String(error)}`,
      retryable: true,
    });
  } finally {
    clearTimeout(timer);
  }
};

const readFieldValue = (html: string, fieldId: string): string => {
  const match = html.match(new RegExp(`id="${fieldId}" value="([^"]*)"`, "i"));
  if (match === null) {
    throw new ApiError({
      apiName: "mas",
      statusCode: 500,
      message: `MAS form field ${fieldId} is missing from the statistics page.`,
      retryable: true,
    });
  }
  return match[1] ?? "";
};

const readSelectOptions = (html: string, htmlId: string): readonly string[] => {
  const match = html.match(new RegExp(`<select[^>]+id="${htmlId}"[^>]*>([\\s\\S]*?)</select>`, "i"));
  if (match === null) {
    throw new ApiError({
      apiName: "mas",
      statusCode: 500,
      message: `MAS select ${htmlId} is missing from the statistics page.`,
      retryable: true,
    });
  }

  const optionsHtml = match[1] ?? "";
  return Array.from(optionsHtml.matchAll(/<option value="([^"]*)"/g)).map((option) => option[1] ?? "");
};

const splitCsvLine = (line: string): readonly string[] => {
  const values: string[] = [];
  let current = "";
  let inQuotes = false;

  for (let index = 0; index < line.length; index += 1) {
    const character = line[index]!;
    if (character === "\"") {
      const nextCharacter = line[index + 1];
      if (inQuotes && nextCharacter === "\"") {
        current += "\"";
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }

    if (character === "," && !inQuotes) {
      values.push(current.trim());
      current = "";
      continue;
    }

    current += character;
  }

  values.push(current.trim());
  return values;
};

const parseCsvLines = (csvText: string): readonly (readonly string[])[] => {
  return csvText
    .split(/\r?\n/)
    .map((line) => line.trimEnd())
    .filter((line) => line.trim() !== "")
    .map(splitCsvLine);
};

const monthNameToNumber = (month: string): string => {
  const normalized = month.slice(0, 3);
  const monthNumber = MONTH_LOOKUP[normalized];
  if (monthNumber === undefined) {
    throw new ApiError({
      apiName: "mas",
      statusCode: 500,
      message: `Unsupported MAS month label: ${month}`,
      retryable: true,
    });
  }
  return monthNumber;
};

const toIsoMonthDate = (year: string, month: string): string => {
  return `${year}-${monthNameToNumber(month)}-01`;
};

const parseNumber = (value: string): number | string => {
  if (value === "" || value === "-") {
    return value;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : value;
};

const EXCHANGE_CURRENCY_CODES: Readonly<Record<string, string>> = {
  Euro: "eur",
  "Pound Sterling": "gbp",
  "US Dollar": "usd",
  "Australian Dollar": "aud",
  "Canadian Dollar": "cad",
  "Chinese Renminbi": "cny",
  "Hong Kong Dollar": "hkd",
  "Indian Rupee": "inr",
  "Indonesian Rupiah": "idr",
  "Japanese Yen": "jpy",
  "Korean Won": "krw",
  "Malaysian Ringgit": "myr",
  "New Taiwan Dollar": "twd",
  "New Zealand Dollar": "nzd",
  "Philippine Peso": "php",
  "Qatar Riyal": "qar",
  "Saudi Arabia Riyal": "sar",
  "Swiss Franc": "chf",
  "Thai Baht": "thb",
  "UAE Dirham": "aed",
  "Vietnamese Dong": "vnd",
};

const normalizeExchangeHeader = (header: string): string | null => {
  const perUnitMatch = header.match(/^S\$ Per Unit of (.+)$/);
  if (perUnitMatch !== null) {
    const currencyCode = EXCHANGE_CURRENCY_CODES[perUnitMatch[1] ?? ""];
    return currencyCode === undefined ? null : `${currencyCode}_sgd`;
  }

  const perHundredMatch = header.match(/^S\$ Per 100 Units of (.+)$/);
  if (perHundredMatch !== null) {
    const currencyCode = EXCHANGE_CURRENCY_CODES[perHundredMatch[1] ?? ""];
    return currencyCode === undefined ? null : `${currencyCode}_sgd_100`;
  }

  return null;
};

const parseExchangeCsv = (csvText: string): readonly MasRecord[] => {
  const lines = parseCsvLines(csvText);
  const headerIndex = lines.findIndex((line) => line[0] === "End of Period");
  if (headerIndex === -1) {
    throw new ApiError({
      apiName: "mas",
      statusCode: 500,
      message: "MAS exchange-rate CSV header was not found.",
      retryable: true,
    });
  }

  const header = lines[headerIndex]!;
  const metricHeaders = header.slice(3).map((value) => normalizeExchangeHeader(value));
  let currentYear = "";

  return lines
    .slice(headerIndex + 1)
    .map((row) => {
      if ((row[0] ?? "") !== "") {
        currentYear = row[0]!;
      }
      const month = row[1] ?? "";
      if (currentYear === "" || month === "") {
        return null;
      }

      const record: Record<string, unknown> = {
        end_of_day: toIsoMonthDate(currentYear, month),
      };

      for (let index = 0; index < metricHeaders.length; index += 1) {
        const key = metricHeaders[index];
        if (key === null || key === undefined) {
          continue;
        }
        record[key] = parseNumber(row[index + 3] ?? "");
      }

      return record as MasRecord;
    })
    .filter((record): record is MasRecord => record !== null);
};

const normalizeInterestHeader = (header: string): string | null => {
  switch (header) {
    case "SORA":
      return "sora";
    case "Compound SORA - 1 month":
      return "sora_1m";
    case "Compound SORA - 3 month":
      return "sora_3m";
    case "Compound SORA - 6 month":
      return "sora_6m";
    default:
      return null;
  }
};

const parseInterestCsv = (csvText: string): readonly MasRecord[] => {
  const lines = parseCsvLines(csvText);
  const headerIndex = lines.findIndex((line) => line[0] === "SORA Value Date");
  if (headerIndex === -1) {
    throw new ApiError({
      apiName: "mas",
      statusCode: 500,
      message: "MAS interest-rate CSV header was not found.",
      retryable: true,
    });
  }

  const header = lines[headerIndex]!;
  const metricHeaders = header.slice(4).map((value) => normalizeInterestHeader(value));
  let currentYear = "";
  let currentMonth = "";

  return lines
    .slice(headerIndex + 1)
    .map((row) => {
      if ((row[0] ?? "") !== "") {
        currentYear = row[0]!;
      }
      if ((row[1] ?? "") !== "") {
        currentMonth = row[1]!;
      }
      const day = row[2] ?? "";
      if (currentYear === "" || currentMonth === "" || day === "") {
        return null;
      }

      const record: Record<string, unknown> = {
        end_of_day: `${currentYear}-${monthNameToNumber(currentMonth)}-${day.padStart(2, "0")}`,
        preliminary: "0",
      };

      for (let index = 0; index < metricHeaders.length; index += 1) {
        const key = metricHeaders[index];
        if (key === null || key === undefined) {
          continue;
        }
        record[key] = parseNumber(row[index + 4] ?? "");
      }

      return record as MasRecord;
    })
    .filter((record): record is MasRecord => record !== null);
};

const normalizeBankingHeader = (header: string): string | null => {
  switch (header) {
    case "TOTAL ASSETS/LIABILITIES":
      return "total_assets";
    case "ASSETS - LOANS AND ADVANCES INCLUDING BILLS FINANCING @":
      return "total_loans";
    case "LIABILITIES - DEPOSITS AND BALANCES OF NON-BANK CUSTOMERS #":
      return "total_deposits";
    default:
      return null;
  }
};

const parseBankingCsv = (csvText: string): readonly MasRecord[] => {
  const lines = parseCsvLines(csvText);
  const headerIndex = lines.findIndex((line) => line[0] === "END OF PERIOD");
  if (headerIndex === -1) {
    throw new ApiError({
      apiName: "mas",
      statusCode: 500,
      message: "MAS banking-statistics CSV header was not found.",
      retryable: true,
    });
  }

  const header = lines[headerIndex]!;
  const metricHeaders = header.slice(1).map((value) => normalizeBankingHeader(value));

  return lines
    .slice(headerIndex + 1)
    .map((row) => {
      const period = row[0] ?? "";
      if (period === "") {
        return null;
      }

      const [year, month] = period.split(/\s+/);
      if (year === undefined || month === undefined) {
        return null;
      }

      const record: Record<string, unknown> = {
        end_of_day: toIsoMonthDate(year, month),
        preliminary: "0",
      };

      for (let index = 0; index < metricHeaders.length; index += 1) {
        const key = metricHeaders[index];
        if (key === null || key === undefined) {
          continue;
        }
        record[key] = parseNumber(row[index + 1] ?? "");
      }

      return record as MasRecord;
    })
    .filter((record): record is MasRecord => record !== null);
};

const DOWNLOAD_CONFIGS: Readonly<Record<MasDatasetSlug, MasDownloadConfig>> = {
  [MasDataset.EXCHANGE_RATES]: {
    dataset: MasDataset.EXCHANGE_RATES,
    pageUrl: "https://eservices.mas.gov.sg/statistics/msb/exchangerates.aspx",
    submitName: "ctl00$ContentPlaceHolder1$DownloadButton",
    selectNames: [
      {
        requestName: "ctl00$ContentPlaceHolder1$StartYearDropDownList",
        htmlId: "ContentPlaceHolder1_StartYearDropDownList",
        resolveValue: (options) => options[0] ?? "",
      },
      {
        requestName: "ctl00$ContentPlaceHolder1$EndYearDropDownList",
        htmlId: "ContentPlaceHolder1_EndYearDropDownList",
        resolveValue: (options) => options[options.length - 1] ?? "",
      },
      {
        requestName: "ctl00$ContentPlaceHolder1$StartMonthDropDownList",
        htmlId: "ContentPlaceHolder1_StartMonthDropDownList",
        resolveValue: () => "1",
      },
      {
        requestName: "ctl00$ContentPlaceHolder1$EndMonthDropDownList",
        htmlId: "ContentPlaceHolder1_EndMonthDropDownList",
        resolveValue: () => "12",
      },
      {
        requestName: "ctl00$ContentPlaceHolder1$FrequencyDropDownList",
        htmlId: "ContentPlaceHolder1_FrequencyDropDownList",
        resolveValue: () => "M",
      },
    ],
    resolveCheckboxNames: (html) => [
      ...Array.from(html.matchAll(/name="(ctl00\$ContentPlaceHolder1\$EndOfPeriodPerUnitCheckBoxList\$\d+)"/g)).map((match) => match[1] ?? ""),
      ...Array.from(html.matchAll(/name="(ctl00\$ContentPlaceHolder1\$EndOfPeriodPer100UnitsCheckBoxList\$\d+)"/g)).map((match) => match[1] ?? ""),
    ],
    parseCsv: parseExchangeCsv,
  },
  [MasDataset.INTEREST_RATES_SORA]: {
    dataset: MasDataset.INTEREST_RATES_SORA,
    pageUrl: "https://eservices.mas.gov.sg/statistics/dir/DomesticInterestRates.aspx",
    submitName: "ctl00$ContentPlaceHolder1$Button2",
    selectNames: [
      {
        requestName: "ctl00$ContentPlaceHolder1$StartYearDropDownList",
        htmlId: "ContentPlaceHolder1_StartYearDropDownList",
        resolveValue: (options) => options[0] ?? "",
      },
      {
        requestName: "ctl00$ContentPlaceHolder1$EndYearDropDownList",
        htmlId: "ContentPlaceHolder1_EndYearDropDownList",
        resolveValue: (options) => options[options.length - 1] ?? "",
      },
      {
        requestName: "ctl00$ContentPlaceHolder1$StartMonthDropDownList",
        htmlId: "ContentPlaceHolder1_StartMonthDropDownList",
        resolveValue: (options) => options[0] ?? "",
      },
      {
        requestName: "ctl00$ContentPlaceHolder1$EndMonthDropDownList",
        htmlId: "ContentPlaceHolder1_EndMonthDropDownList",
        resolveValue: (options) => options[options.length - 1] ?? "",
      },
    ],
    resolveCheckboxNames: () => [
      "ctl00$ContentPlaceHolder1$ColumnsCheckBoxList$13",
      "ctl00$ContentPlaceHolder1$ColumnsCheckBoxList$15",
      "ctl00$ContentPlaceHolder1$ColumnsCheckBoxList$16",
      "ctl00$ContentPlaceHolder1$ColumnsCheckBoxList$17",
    ],
    parseCsv: parseInterestCsv,
  },
  [MasDataset.BANKING_STATS]: {
    dataset: MasDataset.BANKING_STATS,
    pageUrl: "https://eservices.mas.gov.sg/statistics/msb-xml/Report.aspx?tableID=I.3A&tableSetID=I",
    submitName: "ctl00$ContentPlaceHolder1$DownloadButton",
    selectNames: [
      {
        requestName: "ctl00$ContentPlaceHolder1$StartYearDropDownList",
        htmlId: "ctl00_ContentPlaceHolder1_StartYearDropDownList",
        resolveValue: (options) => options[0] ?? "",
      },
      {
        requestName: "ctl00$ContentPlaceHolder1$EndYearDropDownList",
        htmlId: "ctl00_ContentPlaceHolder1_EndYearDropDownList",
        resolveValue: (options) => options[options.length - 1] ?? "",
      },
      {
        requestName: "ctl00$ContentPlaceHolder1$StartMonthDropDownList",
        htmlId: "ctl00_ContentPlaceHolder1_StartMonthDropDownList",
        resolveValue: (options) => options[0] ?? "",
      },
      {
        requestName: "ctl00$ContentPlaceHolder1$EndMonthDropDownList",
        htmlId: "ctl00_ContentPlaceHolder1_EndMonthDropDownList",
        resolveValue: (options) => options[options.length - 1] ?? "",
      },
    ],
    resolveCheckboxNames: () => [
      "ctl00$ContentPlaceHolder1$OptionsList$1",
      "ctl00$ContentPlaceHolder1$OptionsList$2",
      "ctl00$ContentPlaceHolder1$OptionsList$2.5",
      "ctl00$ContentPlaceHolder1$OptionsList$3",
      "ctl00$ContentPlaceHolder1$OptionsList$3.1",
    ],
    parseCsv: parseBankingCsv,
  },
};

const downloadMasCsv = async (dataset: MasDatasetSlug): Promise<readonly MasRecord[]> => {
  const config = DOWNLOAD_CONFIGS[dataset];
  if (config === undefined) {
    throw new ApiError({
      apiName: "mas",
      statusCode: 400,
      message: `Unknown MAS dataset: ${dataset}`,
      retryable: false,
    });
  }

  const initialPage = await fetchMasText(config.pageUrl, {
    method: "GET",
    headers: {
      Origin: MAS_PAGE_ORIGIN,
      Referer: config.pageUrl,
    },
  }, "Failed to load MAS statistics page");

  const cookieHeader = toCookieHeader(initialPage.headers);
  const form = new URLSearchParams();
  for (const fieldId of ["__VIEWSTATE", "__EVENTVALIDATION", "__VIEWSTATEGENERATOR"]) {
    form.set(fieldId, readFieldValue(initialPage.body, fieldId));
  }

  for (const select of config.selectNames) {
    form.set(select.requestName, select.resolveValue(readSelectOptions(initialPage.body, select.htmlId)));
  }

  for (const checkboxName of config.resolveCheckboxNames(initialPage.body)) {
    form.append(checkboxName, "on");
  }
  form.set(config.submitName, "Download");

  const download = await fetchMasText(config.pageUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      Origin: MAS_PAGE_ORIGIN,
      Referer: config.pageUrl,
      ...(cookieHeader === null ? {} : { Cookie: cookieHeader }),
    },
    body: form.toString(),
  }, "Failed to download MAS statistics CSV");

  const contentType = download.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().includes("text/csv")) {
    throw new ApiError({
      apiName: "mas",
      statusCode: 500,
      message: "MAS download did not return CSV content.",
      retryable: true,
      details: download.body.slice(0, 500),
    });
  }

  return config.parseCsv(download.body);
};

const filterMasRecords = (
  records: readonly MasRecord[],
  params: MasQueryParams = {},
): readonly MasRecord[] => {
  const filtered = records.filter((record) => {
    const date = record.end_of_day;
    if (params.date !== undefined && date !== params.date) {
      return false;
    }
    if (params.startDate !== undefined && date < params.startDate) {
      return false;
    }
    if (params.endDate !== undefined && date > params.endDate) {
      return false;
    }
    return true;
  });

  return params.limit === undefined ? filtered : filtered.slice(0, params.limit);
};

export const query = async (
  dataset: string,
  params?: MasQueryParams,
): Promise<readonly MasRecord[]> => {
  const resourceId = getResourceId(dataset);

  const cacheKey = buildCacheKey("mas", "query", {
    resourceId,
    limit: params?.limit,
    date: params?.date,
    startDate: params?.startDate,
    endDate: params?.endDate,
  });
  const { data } = await withCache(cacheKey, "NEAR_REALTIME", async () => {
    const allRecords = await downloadMasCsv(resourceId as MasDatasetSlug);
    return filterMasRecords(
      [...allRecords].sort((left, right) => right.end_of_day.localeCompare(left.end_of_day)),
      params,
    );
  });
  return [...data];
};
