import { resolveAlias } from "./aliases.js";

export type IntentResult = {
  readonly intent: string;
  readonly workflow: string;
  readonly tool?: string;
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

const CURRENCY_STOPWORDS = new Set(["GDP", "CPI", "MRT", "HDB", "LTA", "NEA"]);
const REGIONS = ["north", "south", "east", "west", "central"] as const;

const extractPostalCode = (query: string): string | null => {
  const match = query.match(/\b(\d{6})\b/);
  return match?.[1] ?? null;
};

const extractBusStopCode = (query: string): string | null => {
  const match = query.match(/\b(\d{5})\b/);
  return match?.[1] ?? null;
};

const extractPlanningArea = (query: string): string | null => {
  const lower = query.toLowerCase();
  for (const area of PLANNING_AREAS) {
    if (lower.includes(area)) {
      return area.split(" ").map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
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

const extractMonthRange = (
  query: string,
): Readonly<{ startMonth?: string; endMonth?: string }> => {
  const matches = Array.from(query.matchAll(/\b(20\d{2}-\d{2})\b/g), (match) => match[1]!);
  if (matches.length === 0) {
    return {};
  }
  if (matches.length === 1) {
    return { startMonth: matches[0]!, endMonth: matches[0]! };
  }
  return { startMonth: matches[0]!, endMonth: matches[1]! };
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

const extractBusService = (query: string): string | null => {
  const match = query.match(/\b(?:service|bus)\s+([0-9A-Z]{1,5})\b/i);
  return match?.[1]?.toUpperCase() ?? null;
};

const extractRegion = (query: string): string | null => {
  const lower = query.toLowerCase();
  for (const region of REGIONS) {
    if (lower.includes(region)) {
      return region.charAt(0).toUpperCase() + region.slice(1);
    }
  }
  return null;
};

const extractStationId = (query: string): string | null => {
  const match = query.match(/\b(S\d{3})\b/i);
  return match?.[1]?.toUpperCase() ?? null;
};

const countMacroSignals = (lower: string): number => {
  return [
    /gdp/.test(lower),
    /cpi|inflation/.test(lower),
    /exchange\s*rate|forex|currency\s*rate|sgd/.test(lower),
    /sora|interest\s*rate/.test(lower),
    /unemployment|trade|econom/.test(lower),
  ].filter(Boolean).length;
};

const getApiForTool = (tool: string): string => {
  if (tool.startsWith("sg_mas_")) return "mas";
  if (tool.startsWith("sg_onemap_")) return "onemap";
  if (tool.startsWith("sg_ura_")) return "ura";
  if (tool.startsWith("sg_singstat_")) return "singstat";
  if (tool.startsWith("sg_lta_")) return "lta";
  if (tool.startsWith("sg_nea_")) return "nea";
  if (tool.startsWith("sg_hdb_")) return "hdb";
  return "datagov";
};

const buildIntentResult = (
  intent: string,
  workflow: string,
  confidence: number,
  params: Readonly<Record<string, unknown>>,
  tool?: string,
): IntentResult => {
  return {
    intent,
    workflow,
    ...(tool === undefined ? {} : { tool }),
    apis: tool === undefined ? [] : [getApiForTool(tool)],
    confidence,
    extractedParams: params,
  };
};

export const classifyIntent = (query: string): IntentResult => {
  const lower = query.toLowerCase();
  const params: Record<string, unknown> = {};

  const postalCode = extractPostalCode(query);
  if (postalCode !== null) params["postalCode"] = postalCode;

  const busStopCode = extractBusStopCode(query);
  if (busStopCode !== null && /bus|arrival|stop/i.test(lower)) params["busStopCode"] = busStopCode;

  const planningArea = extractPlanningArea(query);
  if (planningArea !== null) params["planningArea"] = planningArea;

  const currency = extractCurrency(query);
  if (currency !== null) params["currency"] = currency;

  const date = extractIsoDate(query);
  if (date !== null) params["date"] = date;

  const { startMonth, endMonth } = extractMonthRange(query);
  if (startMonth !== undefined) params["startMonth"] = startMonth;
  if (endMonth !== undefined) params["endMonth"] = endMonth;

  const yearRange = extractYearRange(query);
  if (yearRange.startYear !== undefined) params["startYear"] = yearRange.startYear;
  if (yearRange.endYear !== undefined) params["endYear"] = yearRange.endYear;

  const serviceNo = extractBusService(query);
  if (serviceNo !== null) params["serviceNo"] = serviceNo;

  const region = extractRegion(query);
  if (region !== null) params["region"] = region;

  const stationId = extractStationId(query);
  if (stationId !== null) params["stationId"] = stationId;

  const aliasedTool = resolveAlias(lower);
  const macroSignals = countMacroSignals(lower);

  if (/macro\s*(snapshot|overview)|economic\s*(snapshot|overview)|macro\s*data/i.test(lower) || macroSignals >= 3) {
    return {
      ...buildIntentResult("macro", "macro_snapshot", 0.92, params),
      apis: ["singstat", "mas"],
    };
  }

  if (/due\s*diligence|regulatory|legal|planning\s*review|property\s*overview/i.test(lower)) {
    return {
      ...buildIntentResult("property", "property_due_diligence", 0.9, params),
      apis: ["onemap", "ura", "hdb"],
    };
  }

  if (/demographic\s*(overview|profile)|population\s*(overview|profile)|income\s*profile|age\s*distribution/i.test(lower)) {
    return {
      ...buildIntentResult("demographic", "demographic_profile", 0.88, params),
      apis: ["onemap", "ura"],
    };
  }

  if (/dataset|data\s*set|open\s*data|discover|browse.*dataset|find.*dataset/i.test(lower)) {
    return {
      ...buildIntentResult("dataset", "dataset_discovery", 0.82, params),
      apis: ["datagov"],
    };
  }

  if (aliasedTool?.includes("lta") || /bus\s*arrival|train\s*alert|traffic\s*incident/i.test(lower)) {
    const tool = aliasedTool
      ?? (/train\s*alert/i.test(lower)
        ? "sg_lta_train_alerts"
        : /traffic\s*incident/i.test(lower)
          ? "sg_lta_traffic_incidents"
          : "sg_lta_bus_arrivals");
    return buildIntentResult("transport", "direct_tool", 0.92, params, tool);
  }

  if (aliasedTool?.includes("nea") || /forecast|weather|rainfall|air\s*quality|pm2\.?5|psi/i.test(lower)) {
    const tool = aliasedTool
      ?? (/rainfall/i.test(lower)
        ? "sg_nea_rainfall"
        : /air\s*quality|pm2\.?5|psi/i.test(lower)
          ? "sg_nea_air_quality"
          : "sg_nea_forecast_2hr");
    return buildIntentResult("environment", "direct_tool", 0.9, params, tool);
  }

  if (aliasedTool?.includes("hdb") || /hdb|flat\s*prices|resale\s*prices|rental\s*prices/i.test(lower)) {
    const tool = /rental/i.test(lower) ? "sg_hdb_rental_prices" : "sg_hdb_resale_prices";
    return buildIntentResult("housing", "direct_tool", 0.88, params, tool);
  }

  if (aliasedTool?.includes("mas") || /exchange\s*rate|forex|sgd|currency\s*rate|sora|interest\s*rate/i.test(lower)) {
    const tool = aliasedTool
      ?? (/sora|interest\s*rate/i.test(lower)
        ? "sg_mas_interest_rates"
        : /banking|bank\s+loan|deposit|financial\s*stat/i.test(lower)
          ? "sg_mas_financial_stats"
          : "sg_mas_exchange_rates");
    return buildIntentResult("financial", "direct_tool", 0.9, params, tool);
  }

  if (aliasedTool?.includes("ura") || /property|condo|transaction|plot\s*ratio|zoning|master\s*plan/i.test(lower)) {
    const tool = aliasedTool
      ?? (/plot\s*ratio|zoning|master\s*plan|planning\s*area/i.test(lower)
        ? "sg_ura_planning_area"
        : "sg_ura_property_transactions");
    return buildIntentResult("property", "direct_tool", 0.86, params, tool);
  }

  if (
    postalCode !== null
    || aliasedTool?.includes("onemap_geocode")
    || aliasedTool?.includes("onemap_route")
    || /address|geocode|directions|route|nearest|where\s*is|how\s*to\s*get/i.test(lower)
  ) {
    const tool = aliasedTool ?? "sg_onemap_geocode";
    return buildIntentResult("geospatial", "direct_tool", 0.9, params, tool);
  }

  if (
    (planningArea !== null && /population|demographic|age|income|ethnic|dwelling/i.test(lower))
    || aliasedTool?.includes("onemap_population")
  ) {
    return buildIntentResult("demographic", "direct_tool", 0.85, params, "sg_onemap_population");
  }

  if (aliasedTool?.includes("singstat") || /gdp|cpi|inflation|unemployment|trade|economy|economic/i.test(lower)) {
    return buildIntentResult("economic", "direct_tool", 0.85, params, "sg_singstat_search");
  }

  return {
    ...buildIntentResult("dataset", "dataset_discovery", 0.55, params),
    apis: ["datagov"],
  };
};

export const resolveToolInput = (
  intent: IntentResult,
  query: string,
): { tool: string; input: Record<string, unknown> } => {
  const params = intent.extractedParams;
  const tool = intent.tool ?? "sg_datagov_search";

  switch (tool) {
    case "sg_mas_exchange_rates":
      return {
        tool,
        input: {
          ...(params["currency"] !== undefined ? { currency: params["currency"] } : {}),
          ...(params["date"] !== undefined ? { date: params["date"] } : {}),
        },
      };
    case "sg_mas_interest_rates":
    case "sg_mas_financial_stats":
      return {
        tool,
        input: {
          ...(params["date"] !== undefined ? { date: params["date"] } : {}),
        },
      };
    case "sg_ura_property_transactions":
      return {
        tool,
        input: {
          ...(params["planningArea"] !== undefined ? { area: params["planningArea"] } : {}),
        },
      };
    case "sg_ura_planning_area":
      return {
        tool,
        input: {
          ...(params["planningArea"] !== undefined ? { planningArea: params["planningArea"] } : {}),
        },
      };
    case "sg_onemap_geocode":
      return {
        tool,
        input: { searchVal: (params["postalCode"] ?? params["planningArea"] ?? query) as string },
      };
    case "sg_onemap_population":
      return {
        tool,
        input: {
          planningArea: (params["planningArea"] ?? "") as string,
        },
      };
    case "sg_lta_bus_arrivals":
      return {
        tool,
        input: {
          ...(params["busStopCode"] !== undefined ? { busStopCode: params["busStopCode"] } : {}),
          ...(params["serviceNo"] !== undefined ? { serviceNo: params["serviceNo"] } : {}),
        },
      };
    case "sg_lta_train_alerts":
    case "sg_lta_traffic_incidents":
      return {
        tool,
        input: {},
      };
    case "sg_nea_forecast_2hr":
      return {
        tool,
        input: {
          ...(params["planningArea"] !== undefined ? { area: params["planningArea"] } : {}),
          ...(params["date"] !== undefined ? { date: params["date"] } : {}),
        },
      };
    case "sg_nea_air_quality":
      return {
        tool,
        input: {
          ...(params["region"] !== undefined ? { region: params["region"] } : {}),
          ...(params["date"] !== undefined ? { date: params["date"] } : {}),
        },
      };
    case "sg_nea_rainfall":
      return {
        tool,
        input: {
          ...(params["stationId"] !== undefined ? { stationId: params["stationId"] } : {}),
          ...(params["date"] !== undefined ? { date: params["date"] } : {}),
        },
      };
    case "sg_hdb_resale_prices":
    case "sg_hdb_rental_prices":
      return {
        tool,
        input: {
          ...(params["planningArea"] !== undefined ? { town: params["planningArea"] } : {}),
          ...(params["startMonth"] !== undefined ? { startMonth: params["startMonth"] } : {}),
          ...(params["endMonth"] !== undefined ? { endMonth: params["endMonth"] } : {}),
        },
      };
    case "sg_singstat_search":
      return {
        tool,
        input: { keyword: query },
      };
    default:
      return {
        tool,
        input: { keyword: query },
      };
  }
};
