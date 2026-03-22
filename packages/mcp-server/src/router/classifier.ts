import { resolveAlias } from "./aliases.js";

export type IntentResult = {
  readonly intent: string;
  readonly tool: string;
  readonly apis: readonly string[];
  readonly confidence: number;
  readonly extractedParams: Readonly<Record<string, unknown>>;
};

const PLANNING_AREAS = [
  "ang mo kio", "bedok", "bishan", "bukit batok", "bukit merah", "bukit panjang",
  "bukit timah", "central water catchment", "changi", "changi bay", "choa chu kang",
  "clementi", "downtown core", "geylang", "hougang", "jurong east", "jurong west",
  "kallang", "lim chu kang", "mandai", "marine parade", "museum", "newton", "novena",
  "orchard", "outram", "pasir ris", "paya lebar", "pioneer", "punggol", "queenstown",
  "river valley", "rochor", "seletar", "sembawang", "sengkang", "serangoon",
  "simpang", "singapore river", "southern islands", "sungei kadut", "tampines",
  "tanglin", "tengah", "toa payoh", "tuas", "western islands", "western water catchment",
  "woodlands", "yishun",
] as const;

const CURRENCY_STOPWORDS = new Set(["GDP", "CPI", "MRT", "HDB"]);

const extractPostalCode = (query: string): string | null => {
  const match = query.match(/\b(\d{6})\b/);
  return match?.[1] ?? null;
};

const extractPlanningArea = (query: string): string | null => {
  const lower = query.toLowerCase();
  for (const area of PLANNING_AREAS) {
    if (lower.includes(area)) {
      return area.split(" ").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
    }
  }
  return null;
};

const extractCurrency = (query: string): string | null => {
  const upper = query.toUpperCase();
  const directionalMatch = upper.match(/\b(?:TO|AGAINST|VS\.?|VERSUS)\s+([A-Z]{3})\b/);
  if (directionalMatch !== null && !CURRENCY_STOPWORDS.has(directionalMatch[1]!)) {
    return directionalMatch[1] ?? null;
  }

  const codes = Array.from(
    new Set((upper.match(/\b([A-Z]{3})\b/g) ?? []).filter((code) => !CURRENCY_STOPWORDS.has(code))),
  );

  if (codes.length > 1) {
    const nonSgd = codes.find((code) => code !== "SGD");
    if (nonSgd !== undefined) {
      return nonSgd;
    }
  }

  return codes[0] ?? null;
};

const extractIsoDate = (query: string): string | null => {
  const match = query.match(/\b(\d{4}-\d{2}-\d{2})\b/);
  return match?.[1] ?? null;
};

const extractYearRange = (query: string): { startYear?: number; endYear?: number } => {
  const rangeMatch = query.match(/(\d{4})\s*(?:to|-)\s*(\d{4})/);
  if (rangeMatch !== null) {
    return { startYear: parseInt(rangeMatch[1]!, 10), endYear: parseInt(rangeMatch[2]!, 10) };
  }
  const lastNMatch = query.match(/last\s+(\d+)\s+years?/i);
  if (lastNMatch !== null) {
    const n = parseInt(lastNMatch[1]!, 10);
    return { startYear: new Date().getFullYear() - n, endYear: new Date().getFullYear() };
  }
  return {};
};

const getApiForTool = (tool: string): string => {
  if (tool.startsWith("sg_mas_")) return "mas";
  if (tool.startsWith("sg_onemap_")) return "onemap";
  if (tool.startsWith("sg_ura_")) return "ura";
  if (tool.startsWith("sg_singstat_")) return "singstat";
  return "datagov";
};

const buildIntentResult = (
  intent: string,
  tool: string,
  confidence: number,
  params: Readonly<Record<string, unknown>>,
): IntentResult => ({
  intent,
  tool,
  apis: [getApiForTool(tool)],
  confidence,
  extractedParams: params,
});

export const classifyIntent = (query: string): IntentResult => {
  const lower = query.toLowerCase();
  const params: Record<string, unknown> = {};

  const postalCode = extractPostalCode(query);
  if (postalCode !== null) params["postalCode"] = postalCode;

  const planningArea = extractPlanningArea(query);
  if (planningArea !== null) params["planningArea"] = planningArea;

  const currency = extractCurrency(query);
  if (currency !== null) params["currency"] = currency;

  const date = extractIsoDate(query);
  if (date !== null) params["date"] = date;

  const yearRange = extractYearRange(query);
  if (yearRange.startYear !== undefined) params["startYear"] = yearRange.startYear;
  if (yearRange.endYear !== undefined) params["endYear"] = yearRange.endYear;

  // Check alias first
  const aliasedTool = resolveAlias(lower);

  // Financial intent
  if (aliasedTool?.includes("mas") || /exchange\s*rate|forex|sgd|currency\s*rate|sora|interest\s*rate/i.test(lower)) {
    const tool = aliasedTool
      ?? (/sora|interest\s*rate/i.test(lower)
        ? "sg_mas_interest_rates"
        : /banking|bank\s+loan|deposit|financial\s*stat/i.test(lower)
          ? "sg_mas_financial_stats"
          : "sg_mas_exchange_rates");
    return buildIntentResult("financial", tool, 0.9, params);
  }

  // Property intent
  if (aliasedTool?.includes("ura") || /property|resale|rental|condo|transaction|plot\s*ratio|zoning|master\s*plan/i.test(lower)) {
    const tool = aliasedTool
      ?? (/plot\s*ratio|zoning|master\s*plan|planning\s*area/i.test(lower)
        ? "sg_ura_planning_area"
        : "sg_ura_property_transactions");
    return buildIntentResult("property", tool, 0.85, params);
  }

  // Geospatial intent
  if (postalCode !== null || aliasedTool?.includes("onemap_geocode") || aliasedTool?.includes("onemap_route") || /address|geocode|directions|route|nearest|where\s*is|how\s*to\s*get/i.test(lower)) {
    const tool = aliasedTool ?? "sg_onemap_geocode";
    return buildIntentResult("geospatial", tool, 0.9, params);
  }

  // Demographic intent
  if ((planningArea !== null && /population|demographic|age|income|ethnic|dwelling/i.test(lower)) || aliasedTool?.includes("onemap_population")) {
    return buildIntentResult("demographic", "sg_onemap_population", 0.85, params);
  }

  // Economic intent
  if (aliasedTool?.includes("singstat") || /gdp|cpi|inflation|unemployment|trade|export|import|economy|economic/i.test(lower)) {
    return buildIntentResult("economic", "sg_singstat_search", 0.85, params);
  }

  // Fallback to data.gov.sg
  return buildIntentResult("general", "sg_datagov_search", 0.5, params);
};

export const resolveToolInput = (
  intent: IntentResult,
  query: string,
): { tool: string; input: Record<string, unknown> } => {
  const params = intent.extractedParams;

  switch (intent.tool) {
    case "sg_mas_exchange_rates":
      return {
        tool: intent.tool,
        input: {
          ...(params["currency"] !== undefined ? { currency: params["currency"] } : {}),
          ...(params["date"] !== undefined ? { date: params["date"] } : {}),
        },
      };
    case "sg_mas_interest_rates":
    case "sg_mas_financial_stats":
      return {
        tool: intent.tool,
        input: {
          ...(params["date"] !== undefined ? { date: params["date"] } : {}),
        },
      };
    case "sg_ura_property_transactions":
      return {
        tool: intent.tool,
        input: {
          ...(params["planningArea"] !== undefined ? { area: params["planningArea"] } : {}),
        },
      };
    case "sg_ura_planning_area":
      return {
        tool: intent.tool,
        input: {
          ...(params["planningArea"] !== undefined ? { planningArea: params["planningArea"] } : {}),
        },
      };
    case "sg_onemap_geocode":
      return {
        tool: intent.tool,
        input: { searchVal: (params["postalCode"] ?? params["planningArea"] ?? query) as string },
      };
    case "sg_onemap_population":
      return {
        tool: intent.tool,
        input: {
          planningArea: (params["planningArea"] ?? "") as string,
        },
      };
    case "sg_singstat_search":
      return {
        tool: intent.tool,
        input: { keyword: query },
      };
    default:
      return {
        tool: intent.tool,
        input: { keyword: query },
      };
  }
};
