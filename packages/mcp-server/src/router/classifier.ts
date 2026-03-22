import { resolveAlias } from "./aliases.js";

export type IntentResult = {
  readonly intent: string;
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
  const match = query.match(/\b([A-Z]{3})\b/);
  if (match !== null && match[1] !== "GDP" && match[1] !== "CPI" && match[1] !== "MRT" && match[1] !== "HDB") {
    return match[1] ?? null;
  }
  return null;
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

export const classifyIntent = (query: string): IntentResult => {
  const lower = query.toLowerCase();
  const params: Record<string, unknown> = {};

  const postalCode = extractPostalCode(query);
  if (postalCode !== null) params["postalCode"] = postalCode;

  const planningArea = extractPlanningArea(query);
  if (planningArea !== null) params["planningArea"] = planningArea;

  const currency = extractCurrency(query);
  if (currency !== null) params["currency"] = currency;

  const yearRange = extractYearRange(query);
  if (yearRange.startYear !== undefined) params["startYear"] = yearRange.startYear;
  if (yearRange.endYear !== undefined) params["endYear"] = yearRange.endYear;

  // Check alias first
  const aliasedTool = resolveAlias(lower);

  // Financial intent
  if (aliasedTool?.includes("mas") || /exchange\s*rate|forex|sgd|currency\s*rate|sora|interest\s*rate/i.test(lower)) {
    return { intent: "financial", apis: ["mas"], confidence: 0.9, extractedParams: params };
  }

  // Property intent
  if (aliasedTool?.includes("ura") || /property|resale|rental|condo|transaction|plot\s*ratio|zoning/i.test(lower)) {
    return { intent: "property", apis: ["ura"], confidence: 0.85, extractedParams: params };
  }

  // Geospatial intent
  if (postalCode !== null || aliasedTool?.includes("onemap_geocode") || aliasedTool?.includes("onemap_route") || /address|geocode|directions|route|nearest|where\s*is|how\s*to\s*get/i.test(lower)) {
    return { intent: "geospatial", apis: ["onemap"], confidence: 0.9, extractedParams: params };
  }

  // Demographic intent
  if ((planningArea !== null && /population|demographic|age|income|ethnic|dwelling/i.test(lower)) || aliasedTool?.includes("onemap_population")) {
    return { intent: "demographic", apis: ["onemap"], confidence: 0.85, extractedParams: params };
  }

  // Economic intent
  if (aliasedTool?.includes("singstat") || /gdp|cpi|inflation|unemployment|trade|export|import|economy|economic/i.test(lower)) {
    return { intent: "economic", apis: ["singstat"], confidence: 0.85, extractedParams: params };
  }

  // Fallback to data.gov.sg
  return { intent: "general", apis: ["datagov"], confidence: 0.5, extractedParams: params };
};

export const resolveTools = (intent: IntentResult): { tool: string; input: Record<string, unknown> }[] => {
  const tools: { tool: string; input: Record<string, unknown> }[] = [];
  const params = intent.extractedParams;

  switch (intent.intent) {
    case "financial":
      tools.push({
        tool: "sg_mas_exchange_rates",
        input: {
          ...(params["currency"] !== undefined ? { currency: params["currency"] } : {}),
        },
      });
      break;
    case "property":
      tools.push({
        tool: "sg_ura_property_transactions",
        input: {
          ...(params["planningArea"] !== undefined ? { area: params["planningArea"] } : {}),
        },
      });
      break;
    case "geospatial":
      tools.push({
        tool: "sg_onemap_geocode",
        input: { searchVal: (params["postalCode"] ?? params["planningArea"] ?? "") as string },
      });
      break;
    case "demographic":
      tools.push({
        tool: "sg_onemap_population",
        input: {
          planningArea: (params["planningArea"] ?? "") as string,
        },
      });
      break;
    case "economic":
      tools.push({
        tool: "sg_singstat_search",
        input: { keyword: "GDP" },
      });
      break;
    default:
      tools.push({
        tool: "sg_datagov_search",
        input: { keyword: "Singapore" },
      });
  }

  return tools;
};
