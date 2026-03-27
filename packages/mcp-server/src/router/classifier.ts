import { resolveAlias } from "./aliases.js";
import type { BusinessDossierModule, BusinessSectorHint } from "../diligence/entity-resolution.js";

const BUSINESS_DILIGENCE_PATTERN = /\bdiligence\b|regulatory|registration\s*check|registry\s*check|registry\s*diligence|business\s*diligence|counterparty\s*diligence|licen[cs]e\s*check|business\s*dossier|company\s*dossier/i;

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

const CURRENCY_STOPWORDS = new Set(["GDP", "CPI", "MRT", "HDB", "LTA", "NEA", "CEA", "BCA", "ACRA"]);
const REGIONS = ["north", "south", "east", "west", "central"] as const;
const SINGSTAT_CATEGORY_MATCHERS = [
  { category: "Economy & Prices", pattern: /\beconomy|prices|gdp|cpi|inflation|national accounts\b/i },
  { category: "Population & Land Area", pattern: /\bpopulation|land area|demographic\b/i },
  { category: "Labour & Productivity", pattern: /\blabou?r|employment|wages|productivity\b/i },
  { category: "Society", pattern: /\bsociety|education|health|housing|social\b/i },
  { category: "Transport", pattern: /\btransport|traffic|vehicle|mrt|bus\b/i },
  { category: "Services", pattern: /\bservices|retail|tourism|accommodation|food\b/i },
  { category: "Manufacturing & Construction", pattern: /\bmanufacturing|construction|industrial production\b/i },
  { category: "Finance & Insurance", pattern: /\bfinance|banking|insurance|capital markets\b/i },
  { category: "International Trade", pattern: /\binternational trade|imports|exports|trade partners\b/i },
] as const;

const extractPostalCode = (query: string): string | null => {
  const match = query.match(/\b(\d{6})\b/);
  return match?.[1] ?? null;
};

const extractPostalCodes = (query: string): readonly string[] => {
  return Array.from(query.matchAll(/\b(\d{6})\b/g), (match) => match[1] ?? "");
};

const extractCoordinatePairs = (
  query: string,
): readonly { lat: number; lng: number }[] => {
  return Array.from(
    query.matchAll(/(-?\d{1,2}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)/g),
    (match) => ({
      lat: Number(match[1]),
      lng: Number(match[2]),
    }),
  ).filter(({ lat, lng }) =>
    Number.isFinite(lat)
    && Number.isFinite(lng)
    && Math.abs(lat) <= 90
    && Math.abs(lng) <= 180);
};

const extractSvy21Pair = (query: string): { x: number; y: number } | null => {
  const explicit = query.match(
    /\b(?:svy21|easting|northing)\b.*?(?:x|easting)?\s*[:=]?\s*(\d{4,6})\D+(?:y|northing)?\s*[:=]?\s*(\d{4,6})/i,
  );
  if (explicit === null) {
    return null;
  }
  return {
    x: Number(explicit[1]),
    y: Number(explicit[2]),
  };
};

const extractRouteType = (query: string): "walk" | "drive" | "pt" | "cycle" | null => {
  if (/\bwalk|walking\b/i.test(query)) return "walk";
  if (/\bdrive|driving\b/i.test(query)) return "drive";
  if (/\bcycle|cycling\b/i.test(query)) return "cycle";
  if (/\bpublic transport|train|mrt|bus\b/i.test(query)) return "pt";
  return null;
};

const extractTableId = (query: string): string | null => {
  const match = query.match(/\b([A-Z]\d{6}[A-Z]?)\b/i);
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

const extractDatasetId = (query: string): string | null => {
  const match = query.match(/\b(d_[a-f0-9]{32})\b/i);
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

const extractLocationPhrase = (query: string): string | null => {
  const match = query.match(
    /\b(?:near|around|by|at|in)\s+(.+?)(?=\s+(?:with|for|called|named)\b|[?.!,]|$)/i,
  );
  return match?.[1]?.trim() ?? null;
};

const extractQuotedTerm = (query: string): string | null => {
  const match = query.match(/["“”'`]\s*([^"“”'`]{2,}?)\s*["“”'`]/);
  return match?.[1]?.trim() ?? null;
};

const extractIndicator = (query: string): string | null => {
  const explicit = query.match(/\bindicator\s+(.+?)(?=\s+(?:from|table|for|between)\b|[?.!,]|$)/i);
  if (explicit?.[1] !== undefined) {
    return explicit[1].trim();
  }
  return extractQuotedTerm(query);
};

const extractFlatType = (query: string): string | null => {
  const match = query.match(/\b(STUDIO APARTMENT|MULTI-GENERATION|EXECUTIVE|[1-5]\s*ROOM)\b/i);
  return match?.[1]?.replace(/\s+/g, " ").toUpperCase() ?? null;
};

const extractNamedFacility = (query: string): string | null => {
  return extractNamedSubject(query, [
    /\b(?:named|called)\s+(.+?)(?=\s+(?:near|around|by|at|in|with|for)\b|[?.!,]|$)/i,
  ]) ?? (
    /(community\s+club|passion\s*wave|resident(?:s')?\s*(?:committee|network)|sportsg|sports?\s+facility|child\s*care|childcare|preschool|kindergarten|family\s+service\s+cent(?:re|er)|student\s+care|social\s+service\s+office)/i.test(query)
      ? extractQuotedTerm(query)
      : null
  );
};

const extractSportSgFacilityType = (query: string): string | null => {
  if (/\bswim(?:ming)?|pool\b/i.test(query)) return "swimming_complex";
  if (/\btennis\b/i.test(query)) return "tennis_centre";
  if (/\bsquash\b/i.test(query)) return "squash_centre";
  if (/\bstadium\b/i.test(query)) return "stadium";
  if (/\bsports?\s+hall\b/i.test(query)) return "sports_hall";
  if (/\bhockey\b/i.test(query)) return "hockey_centre";
  if (/\barchery\b/i.test(query)) return "archery_centre";
  if (/\bsport(?:s)?\s+centre\b/i.test(query)) return "sport_centre";
  return null;
};

const extractChildcareCentreType = (query: string): string | null => {
  if (/\bkindergarten\b/i.test(query)) return "KN";
  if (/\bchild\s*care|childcare|preschool\b/i.test(query)) return "CC";
  return null;
};

const extractAuditStatus = (query: string): string | null => {
  const match = query.match(/\bgrade\s*([abc])\b/i);
  return match?.[1] === undefined ? null : `Grade ${match[1].toUpperCase()}`;
};

const detectCivicTool = (query: string): string | null => {
  if (/\bfamily\s+service\s+cent(?:re|er)s?\b|\bfsc\b/i.test(query)) {
    return "sg_msf_family_services";
  }
  if (/\bstudent\s+care\b|\bscfa\b/i.test(query)) {
    return "sg_msf_student_care_services";
  }
  if (/\bsocial\s+service\s+offices?\b|\bsso\b/i.test(query)) {
    return "sg_msf_social_service_offices";
  }
  if (/\bcommunity\s+club\b|\bpassion\s*wave\b/i.test(query)) {
    return "sg_pa_community_outlets";
  }
  if (/\bresident(?:s')?\s*(?:committee|network(?:\s+centre)?|network centre)|\brn\b|\brc\b/i.test(query)) {
    return "sg_pa_resident_network_centres";
  }
  if (/\bsportsg\b|\bsports?\s+facility\b|\bswimming\b|\btennis\b|\bsquash\b|\bstadium\b|\bsports?\s+hall\b|\bsport(?:s)?\s+centre\b/i.test(query)) {
    return "sg_sportsg_facilities";
  }
  if (/\bchild\s*care\b|\bchildcare\b|\bpreschool\b|\bkindergarten\b/i.test(query)) {
    return "sg_ecda_childcare_centres";
  }
  return null;
};

const extractSingStatCategory = (query: string): string | null => {
  for (const matcher of SINGSTAT_CATEGORY_MATCHERS) {
    if (matcher.pattern.test(query)) {
      return matcher.category;
    }
  }
  return null;
};

const extractCollection = (query: string): string | null => {
  const explicit = query.match(/\bcollection\s+(.+?)(?=\s+(?:datasets?|data|resources?|rows?)\b|[?.!,]|$)/i);
  if (explicit?.[1] !== undefined) {
    return explicit[1].trim();
  }
  return /collection/i.test(query) ? extractQuotedTerm(query) : null;
};

const extractUseGroup = (query: string): string | null => {
  const explicit = query.match(/\buse\s+group\s+(.+?)(?=\s+(?:sector|rate|rates)\b|[?.!,]|$)/i);
  return explicit?.[1]?.trim() ?? null;
};

const extractSector = (query: string): string | null => {
  const explicit = query.match(/\bsector\s+(.+?)(?=\s+(?:use\s+group|rate|rates)\b|[?.!,]|$)/i);
  return explicit?.[1]?.trim() ?? null;
};

const extractCoordinateSource = (query: string): "SVY21" | "WGS84" | null => {
  const lower = query.toLowerCase();
  if (/to\s+svy21|from\s+wgs84|from\s+gps/.test(lower)) {
    return "WGS84";
  }
  if (/to\s+wgs84|to\s+gps|from\s+svy21/.test(lower)) {
    return "SVY21";
  }
  if (/convert\s+svy21/.test(lower)) {
    return "SVY21";
  }
  if (/convert\s+wgs84|convert\s+gps/.test(lower)) {
    return "WGS84";
  }
  return null;
};

const stripTrailingBusinessContext = (value: string): string => {
  return value
    .replace(
      /\s+(?:with|using|under|by|for)\s+(?:uen|registration|reg(?:istration)?|licen[cs]e|grade|workhead|builder\s*class|details|records?).*$/i,
      "",
    )
    .replace(
      /\s+(?:uen(?:\s*(?:number|no\.?))?\s*[:#]?\s*[0-9A-Z]{8,10}|registration(?:\s*(?:number|no\.?))?\s*[:#]?\s*[0-9A-Z-]{5,}|reg(?:istration)?\s*[:#]?\s*[0-9A-Z-]{5,}|licen[cs]e(?:\s*(?:number|no\.?))?\s*[:#]?\s*[0-9A-Z-]{5,}|workhead\s+[A-Z]{2}\d{2}|grade\s+[A-Z]\d|class\s+[A-Z]{2}\d|builder\s*class\s+[A-Z]{2}\d|details?|records?)$/i,
      "",
    )
    .replace(/[.,;:!?]+$/, "")
    .trim();
};

const extractNamedSubject = (
  query: string,
  patterns: readonly RegExp[],
): string | null => {
  for (const pattern of patterns) {
    const match = query.match(pattern);
    const candidate = match?.[1];
    if (candidate !== undefined) {
      const cleaned = stripTrailingBusinessContext(candidate)
        .replace(/^["“”'`]\s*|\s*["“”'`]$/g, "")
        .trim();
      if (cleaned !== "") {
        return cleaned;
      }
    }
  }
  return null;
};

const extractCompanyName = (query: string): string | null => {
  return extractNamedSubject(query, [
    /\b(?:company|entity|business|counterparty)\s+(.+?)(?=\s+(?:with|using|under)\b|[?!,;:]|$)/i,
    /\b(?:builder|contractor|vendor)\s+(.+?)(?=\s+(?:with|using|under)\b|[?!,;:]|$)/i,
    /\b(?:architect|architecture\s+firm|pharmacy|supplier|manufacturer|importer|wholesaler|hotel|hotel\s+operator|keeper|operator)\s+(.+?)(?=\s+(?:with|using|under)\b|[?!,;:]|$)/i,
  ]) ?? extractQuotedTerm(query);
};

const extractSalespersonName = (query: string): string | null => {
  return extractNamedSubject(query, [
    /\bsalesperson\s+(.+?)(?=\s+(?:with|using|under|registration|licen[cs]e|estate\s+agent)\b|[?.!,]|$)/i,
  ]) ?? (/salesperson/i.test(query) ? extractQuotedTerm(query) : null);
};

const extractEstateAgentName = (query: string): string | null => {
  return extractNamedSubject(query, [
    /\bestate\s+agent\s+(.+?)(?=\s+(?:with|using|under|registration|licen[cs]e|salesperson)\b|[?.!,]|$)/i,
  ]) ?? (/estate\s+agent/i.test(query) ? extractQuotedTerm(query) : null);
};

const extractUen = (query: string): string | null => {
  const explicit = query.match(/\buen(?:\s*(?:number|no\.?))?\s*[:#]?\s*([0-9A-Z]{8,10})\b/i);
  return explicit?.[1]?.toUpperCase() ?? null;
};

const extractRegistrationNo = (query: string): string | null => {
  const direct = query.match(/\bR\d{6}[A-Z]\b/i);
  if (direct !== null) {
    return direct[0]?.toUpperCase() ?? null;
  }

  return query
    .match(/\bregistration(?:\s*(?:number|no\.?))?\s*[:#]?\s*([0-9A-Z-]{5,})\b/i)?.[1]
    ?.toUpperCase() ?? null;
};

const extractEstateAgentLicenseNo = (query: string): string | null => {
  const direct = query.match(/\bL\d{7}[A-Z]\b/i);
  if (direct !== null) {
    return direct[0]?.toUpperCase() ?? null;
  }

  return query
    .match(/\blicen[cs]e(?:\s*(?:number|no\.?))?\s*[:#]?\s*([0-9A-Z-]{5,})\b/i)?.[1]
    ?.toUpperCase() ?? null;
};

const extractWorkhead = (query: string): string | null => {
  return query.match(/\bworkhead\s+([A-Z]{2}\d{2})\b/i)?.[1]?.toUpperCase() ?? null;
};

const extractGrade = (query: string): string | null => {
  return query.match(/\bgrade\s+([A-Z]\d)\b/i)?.[1]?.toUpperCase() ?? null;
};

const extractBuilderClassCode = (query: string): string | null => {
  const explicit = query.match(/\b(GB[12])\b/i);
  if (explicit !== null) {
    return explicit[1]?.toUpperCase() ?? null;
  }

  return query.match(/\bclass\s+([A-Z]{2}\d)\b/i)?.[1]?.toUpperCase() ?? null;
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
  if (tool.startsWith("sg_cea_")) return "cea";
  if (tool.startsWith("sg_bca_")) return "bca";
  if (tool.startsWith("sg_boa_")) return "boa";
  if (tool.startsWith("sg_acra_")) return "acra";
  if (tool.startsWith("sg_hsa_")) return "hsa";
  if (tool.startsWith("sg_hlb_")) return "hlb";
  if (tool.startsWith("sg_pa_")) return "pa";
  if (tool.startsWith("sg_sportsg_")) return "sportsg";
  if (tool.startsWith("sg_ecda_")) return "ecda";
  if (tool === "sg_msf_family_services") return "msf_family_services";
  if (tool === "sg_msf_student_care_services") return "msf_student_care_services";
  if (tool === "sg_msf_social_service_offices") return "msf_social_service_offices";
  if (tool === "sg_gebiz_tenders") return "gebiz";
  return "datagov";
};

const extractSectorHints = (query: string): readonly BusinessSectorHint[] => {
  const hints: BusinessSectorHint[] = [];
  if (/\bconstruction|builder|contractor|workhead\b/i.test(query)) hints.push("construction");
  if (/\breal\s*estate|estate\s*agent|salesperson|property\b/i.test(query)) hints.push("real_estate");
  if (/\barchitect|architecture\s+firm|boa\b/i.test(query)) hints.push("architecture");
  if (/\bpharmacy|pharmacies|health\s+product|healthcare|medical\s+device|hsa\b/i.test(query)) hints.push("healthcare");
  if (/\bhotel|hospitality|keeper|hlb\b/i.test(query)) hints.push("hospitality");
  if (/\bprocurement|supplier|tender|gebiz\b/i.test(query)) hints.push("procurement");
  return Array.from(new Set(hints));
};

const extractExplicitModules = (query: string): readonly BusinessDossierModule[] => {
  const modules: BusinessDossierModule[] = [];
  if (/\bacra|company|entity|\buen\b|incorporat/i.test(query)) modules.push("acra");
  if (/\bbca|builder|contractor|workhead|class\s+[a-z]{2}\d/i.test(query)) modules.push("bca");
  if (/\bcea|salesperson|estate\s+agent|real\s*estate/i.test(query)) modules.push("cea");
  if (/\bgebiz|procurement|supplier|tender/i.test(query)) modules.push("gebiz");
  if (/\bboa|architect|architecture\s+firm/i.test(query)) modules.push("boa");
  if (/\bhsa|pharmacy|health\s+product|medical\s+device|wholesale\s+licen[cs]e|manufacture\s+health\s+products/i.test(query)) modules.push("hsa");
  if (/\bhlb|hotel|keeper|hospitality/i.test(query)) modules.push("hlb");
  return Array.from(new Set(modules));
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

  const postalCodes = extractPostalCodes(query);
  if (postalCodes.length >= 2) {
    params["originPostalCode"] = postalCodes[0]!;
    params["destinationPostalCode"] = postalCodes[1]!;
  }

  const coordinatePairs = extractCoordinatePairs(query);
  if (coordinatePairs.length >= 1) {
    params["lat"] = coordinatePairs[0]!.lat;
    params["lng"] = coordinatePairs[0]!.lng;
  }
  if (coordinatePairs.length >= 2) {
    params["startLat"] = coordinatePairs[0]!.lat;
    params["startLng"] = coordinatePairs[0]!.lng;
    params["endLat"] = coordinatePairs[1]!.lat;
    params["endLng"] = coordinatePairs[1]!.lng;
  }

  const svy21Pair = extractSvy21Pair(query);
  if (svy21Pair !== null) {
    params["svy21X"] = svy21Pair.x;
    params["svy21Y"] = svy21Pair.y;
  }

  const busStopCode = extractBusStopCode(query);
  if (busStopCode !== null && /bus|arrival|stop/i.test(lower)) params["busStopCode"] = busStopCode;

  const planningArea = extractPlanningArea(query);
  if (planningArea !== null) params["planningArea"] = planningArea;

  const currency = extractCurrency(query);
  if (currency !== null) params["currency"] = currency;

  const date = extractIsoDate(query);
  if (date !== null) params["date"] = date;

  const datasetId = extractDatasetId(query);
  if (datasetId !== null) params["datasetId"] = datasetId;

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

  const routeType = extractRouteType(query);
  if (routeType !== null) params["routeType"] = routeType;

  const tableId = extractTableId(query);
  if (tableId !== null) params["tableId"] = tableId;

  const indicator = extractIndicator(query);
  if (indicator !== null) params["indicator"] = indicator;

  const flatType = extractFlatType(query);
  if (flatType !== null) params["flatType"] = flatType;

  const facilityName = extractNamedFacility(query);
  if (facilityName !== null) {
    params["name"] = facilityName;
    const extractedPlanningArea = params["planningArea"];
    if (
      typeof extractedPlanningArea === "string"
      && facilityName.toLowerCase().includes(extractedPlanningArea.toLowerCase())
    ) {
      delete params["planningArea"];
    }
  }

  const locationPhrase = extractLocationPhrase(query);
  if (
    locationPhrase !== null
    && (facilityName === null || !facilityName.toLowerCase().includes(locationPhrase.toLowerCase()))
  ) {
    params["address"] = locationPhrase;
  }

  const facilityType = extractSportSgFacilityType(query);
  if (facilityType !== null) params["facilityType"] = facilityType;

  const centreType = extractChildcareCentreType(query);
  if (centreType !== null) params["centreType"] = centreType;

  const auditStatus = extractAuditStatus(query);
  if (auditStatus !== null) params["auditStatus"] = auditStatus;

  if (/\bvacanc(?:y|ies)|available\s+slots?|openings?\b/i.test(lower)) {
    params["hasVacancy"] = true;
  }

  if (/\bscfa(?:\s*approved|-approved)?\b/i.test(lower)) {
    params["scfaOnly"] = true;
  }

  if (/\bpassion\s*wave\b/i.test(lower)) {
    params["type"] = "passion_wave";
  } else if (/\bcommunity\s+club\b/i.test(lower)) {
    params["type"] = "community_club";
  }

  const category = extractSingStatCategory(query);
  if (category !== null) params["category"] = category;

  const collection = extractCollection(query);
  if (collection !== null) params["collection"] = collection;

  const useGroup = extractUseGroup(query);
  if (useGroup !== null) params["useGroup"] = useGroup;

  const sector = extractSector(query);
  if (sector !== null) params["sector"] = sector;

  const coordinateSource = extractCoordinateSource(query);
  if (coordinateSource !== null) params["from"] = coordinateSource;
  if (coordinateSource === "SVY21" && svy21Pair !== null) {
    params["x"] = svy21Pair.x;
    params["y"] = svy21Pair.y;
  }
  if (coordinateSource === "WGS84" && coordinatePairs.length >= 1) {
    params["x"] = coordinatePairs[0]!.lat;
    params["y"] = coordinatePairs[0]!.lng;
  }

  const companyName = extractCompanyName(query);
  if (companyName !== null) {
    params["companyName"] = companyName;
    params["entityName"] = companyName;
  }

  const sectorHints = extractSectorHints(query);
  if (sectorHints.length > 0) {
    params["sectorHints"] = sectorHints;
  }

  const explicitModules = extractExplicitModules(query);
  if (explicitModules.length > 0) {
    params["modules"] = explicitModules;
  }
  const hasExpandedBusinessScope = explicitModules.some((module) => !["acra", "bca", "cea"].includes(module));

  const salespersonName = extractSalespersonName(query);
  if (salespersonName !== null) {
    params["salespersonName"] = salespersonName;
  }

  const estateAgentName = extractEstateAgentName(query);
  if (estateAgentName !== null) {
    params["estateAgentName"] = estateAgentName;
    params["entityName"] ??= estateAgentName;
  }

  const uen = extractUen(query);
  if (uen !== null) {
    params["uen"] = uen;
    params["uenNo"] = uen;
  }

  const registrationNo = extractRegistrationNo(query);
  if (registrationNo !== null) params["registrationNo"] = registrationNo;

  const estateAgentLicenseNo = extractEstateAgentLicenseNo(query);
  if (estateAgentLicenseNo !== null) params["estateAgentLicenseNo"] = estateAgentLicenseNo;

  const workhead = extractWorkhead(query);
  if (workhead !== null) params["workhead"] = workhead;

  const grade = extractGrade(query);
  if (grade !== null) params["grade"] = grade;

  const classCode = extractBuilderClassCode(query);
  if (classCode !== null) params["classCode"] = classCode;

  const aliasedTool = resolveAlias(lower);
  const macroSignals = countMacroSignals(lower);

  if (/macro\s*(snapshot|overview|brief)|economic\s*(snapshot|overview|brief)|macro\s*data/i.test(lower) || macroSignals >= 3) {
    return {
      ...buildIntentResult("macro", "macro_snapshot", 0.92, params),
      apis: ["singstat", "mas"],
    };
  }

  if (
    BUSINESS_DILIGENCE_PATTERN.test(lower)
    && /architect|architecture\s+firm|boa/i.test(lower)
  ) {
    return {
      ...buildIntentResult("business", "architecture_firm_diligence", 0.92, params),
      apis: ["acra", "boa", "gebiz"],
    };
  }

  if (
    BUSINESS_DILIGENCE_PATTERN.test(lower)
    && /pharmacy|health\s+product|healthcare|hsa/i.test(lower)
  ) {
    return {
      ...buildIntentResult("business", "healthcare_supplier_diligence", 0.92, params),
      apis: ["acra", "hsa", "gebiz"],
    };
  }

  if (
    (/lookup|operator\s+lookup|licen[cs]e\s*check/i.test(lower) || BUSINESS_DILIGENCE_PATTERN.test(lower))
    && /hotel|keeper|hlb|hospitality/i.test(lower)
  ) {
    return {
      ...buildIntentResult("business", "hotel_operator_lookup", 0.92, params),
      apis: ["acra", "hlb"],
    };
  }

  if (
    BUSINESS_DILIGENCE_PATTERN.test(lower)
    && /acra|company|entity|uen|salesperson|estate\s*agent|builder|contractor|bca|cea|gebiz|architect|pharmacy|health\s+product|hotel/i.test(lower)
  ) {
    if (!hasExpandedBusinessScope) {
      return {
        ...buildIntentResult("business", "business_registry_diligence", 0.91, params),
        apis: ["acra", "bca", "cea"],
      };
    }

    return {
      ...buildIntentResult("business", "sector_scoped_business_diligence", 0.91, params),
      apis: Array.from(new Set(explicitModules.map((module) => module))),
    };
  }

  if (/due\s*diligence|regulatory|legal|planning\s*review|property\s*overview|property\s*brief|location\s*brief/i.test(lower)) {
    return {
      ...buildIntentResult("property", "property_due_diligence", 0.9, params),
      apis: ["onemap", "ura", "hdb"],
    };
  }

  if (aliasedTool === "sg_datagov_resources" || (datasetId !== null && /resource|resources|column|columns|schema/i.test(lower))) {
    return buildIntentResult("dataset", "direct_tool", 0.91, params, "sg_datagov_resources");
  }

  if (aliasedTool === "sg_datagov_rows" || (datasetId !== null && /\b(row|rows|record|records)\b/i.test(lower))) {
    return buildIntentResult("dataset", "direct_tool", 0.91, params, "sg_datagov_rows");
  }

  if (/demographic\s*(overview|profile)|population\s*(overview|profile)|income\s*profile|age\s*distribution/i.test(lower)) {
    return {
      ...buildIntentResult("demographic", "demographic_profile", 0.88, params),
      apis: ["onemap", "ura"],
    };
  }

  if (aliasedTool === "sg_singstat_browse" || /browse\s+singstat|singstat\s+(?:categories|category|browse)/i.test(lower)) {
    return buildIntentResult("economic", "direct_tool", 0.87, params, "sg_singstat_browse");
  }

  if (
    aliasedTool === "sg_singstat_timeseries"
    || /singstat.*(?:time\s*series|timeseries)|(?:time\s*series|timeseries).*(?:singstat|table\b)/i.test(lower)
  ) {
    return buildIntentResult("economic", "direct_tool", 0.88, params, "sg_singstat_timeseries");
  }

  if (
    aliasedTool === "sg_singstat_table"
    || /singstat\s+table|tablebuilder\s+table|show\s+me\s+the\s+singstat\s+table/i.test(lower)
    || (tableId !== null && /singstat|tablebuilder|table\s+[a-z]\d{6}/i.test(lower))
  ) {
    return buildIntentResult("economic", "direct_tool", 0.88, params, "sg_singstat_table");
  }

  if (/dataset|data\s*set|open\s*data|discover|browse.*dataset|find.*dataset/i.test(lower)) {
    return {
      ...buildIntentResult("dataset", "dataset_discovery", 0.82, params),
      apis: ["datagov"],
    };
  }

  if (
    aliasedTool === "sg_onemap_route"
    || /\b(directions|how\s+to\s+get|travel\s+from|walk\s+from|drive\s+from|cycle\s+from|route\s+from)\b/i.test(lower)
  ) {
    return {
      ...buildIntentResult("geospatial", "route_plan", 0.89, params),
      apis: ["onemap"],
    };
  }

  if (
    aliasedTool === "sg_onemap_reverse_geocode"
    || /reverse\s*geocode|address\s+from\s+coordinates?|what\s+is\s+at\s+[-\d.]+\s*,\s*[-\d.]+/i.test(lower)
  ) {
    return buildIntentResult("geospatial", "direct_tool", 0.9, params, "sg_onemap_reverse_geocode");
  }

  if (
    aliasedTool === "sg_onemap_convert_coords"
    || /coordinate\s*conversion|convert\s+coordinates|convert\s+svy21|convert\s+wgs84|convert\s+gps/i.test(lower)
  ) {
    return buildIntentResult("geospatial", "direct_tool", 0.88, params, "sg_onemap_convert_coords");
  }

  if (
    (
      aliasedTool === "sg_transport_brief"
      || /transport\s*(status|snapshot|brief|ops|operations)|network\s*status|commute\s*status|mrt\s*status|road\s*status/i.test(lower)
    )
    && busStopCode === null
    && serviceNo === null
    && !/bus\s*arrival|train\s*alert|traffic\s*incident/i.test(lower)
  ) {
    return {
      ...buildIntentResult("transport", "transport_brief", 0.9, params),
      apis: ["lta"],
    };
  }

  if (
    (
      aliasedTool === "sg_environment_brief"
      || /environment\s*(status|snapshot|brief)|weather\s*(snapshot|brief)|air\s*quality\s*(snapshot|brief)|rainfall\s*(snapshot|brief)/i.test(lower)
    )
    && stationId === null
    && region === null
    && !(planningArea !== null && /forecast|weather/i.test(lower))
    && !/2\s*hour\s*forecast|forecast\s+for|rainfall\s+for|air\s*quality\s+for|psi\s+for|pm2\.?5\s+for/i.test(lower)
  ) {
    return {
      ...buildIntentResult("environment", "environment_brief", 0.89, params),
      apis: ["nea"],
    };
  }

  const civicTool = detectCivicTool(query);
  if (civicTool !== null) {
    return {
      ...buildIntentResult("civic", "civic_discovery", 0.88, params, civicTool),
      apis: Array.from(new Set(["onemap", getApiForTool(civicTool)])),
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

  if (aliasedTool?.includes("cea") || /salesperson|estate\s*agent|real\s*estate/i.test(lower)) {
    return buildIntentResult("business", "direct_tool", 0.9, params, "sg_cea_salespersons");
  }

  if (
    aliasedTool?.includes("bca")
    || /licensed\s*builder|registered\s*contractor|workhead|builder\s*class|contractor\s*grade/i.test(lower)
  ) {
    const tool = /licensed\s*builder|builder\s*class|gb1|gb2/i.test(lower)
      ? "sg_bca_licensed_builders"
      : "sg_bca_registered_contractors";
    return buildIntentResult("business", "direct_tool", 0.9, params, tool);
  }

  if (
    aliasedTool?.includes("boa")
    || /\barchitect|architecture\s+firm|board\s+of\s+architects\b/i.test(lower)
  ) {
    const tool = /architecture\s+firm/i.test(lower) ? "sg_boa_architecture_firms" : "sg_boa_architects";
    return buildIntentResult("business", "direct_tool", 0.9, params, tool);
  }

  if (
    aliasedTool?.includes("acra")
    || /acra|company\s*registration|corporate\s*entity|\buen\b|incorporat/i.test(lower)
  ) {
    return buildIntentResult("business", "direct_tool", 0.9, params, "sg_acra_entities");
  }

  if (
    aliasedTool?.includes("hsa")
    || /pharmacy|health\s+product|healthcare\s+supplier|medical\s+device|wholesale\s+licen[cs]e|manufacture\s+health\s+products/i.test(lower)
  ) {
    const tool = /pharmacy|pharmacies/i.test(lower)
      ? "sg_hsa_licensed_pharmacies"
      : "sg_hsa_health_product_licensees";
    return buildIntentResult("business", "direct_tool", 0.9, params, tool);
  }

  if (
    aliasedTool?.includes("hlb")
    || /hotel|keeper|hotel\s+operator|hospitality/i.test(lower)
  ) {
    return buildIntentResult("business", "direct_tool", 0.89, params, "sg_hlb_hotels");
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

  if (aliasedTool === "sg_ura_dev_charges" || /development\s*charge|dev\s*charge/i.test(lower)) {
    return buildIntentResult("property", "direct_tool", 0.88, params, "sg_ura_dev_charges");
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

  if (aliasedTool === "sg_datagov_browse" || /browse\s+(?:data\.gov|open\s+data)|data\.gov.*collections?|open\s+data.*collections?/i.test(lower)) {
    return buildIntentResult("dataset", "direct_tool", 0.84, params, "sg_datagov_browse");
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
          ...(params["startDate"] !== undefined ? { startDate: params["startDate"] } : {}),
          ...(params["endDate"] !== undefined ? { endDate: params["endDate"] } : {}),
        },
      };
    case "sg_mas_interest_rates":
    case "sg_mas_financial_stats":
      return {
        tool,
        input: {
          ...(params["date"] !== undefined ? { date: params["date"] } : {}),
          ...(params["startDate"] !== undefined ? { startDate: params["startDate"] } : {}),
          ...(params["endDate"] !== undefined ? { endDate: params["endDate"] } : {}),
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
          ...(params["lat"] !== undefined && params["lng"] !== undefined
            ? { lat: params["lat"], lng: params["lng"] }
            : {}),
        },
      };
    case "sg_ura_dev_charges":
      return {
        tool,
        input: {
          ...(params["useGroup"] !== undefined ? { useGroup: params["useGroup"] } : {}),
          ...(params["sector"] !== undefined ? { sector: params["sector"] } : {}),
        },
      };
    case "sg_transport_brief":
      return {
        tool,
        input: {
          ...(params["busStopCode"] !== undefined ? { busStopCode: params["busStopCode"] } : {}),
          ...(params["serviceNo"] !== undefined ? { serviceNo: params["serviceNo"] } : {}),
        },
      };
    case "sg_environment_brief":
      return {
        tool,
        input: {
          ...(params["planningArea"] !== undefined ? { area: params["planningArea"] } : {}),
          ...(params["region"] !== undefined ? { region: params["region"] } : {}),
          ...(params["stationId"] !== undefined ? { stationId: params["stationId"] } : {}),
          ...(params["date"] !== undefined ? { date: params["date"] } : {}),
        },
      };
    case "sg_onemap_geocode":
      return {
        tool,
        input: { searchVal: (params["postalCode"] ?? params["planningArea"] ?? query) as string },
      };
    case "sg_onemap_reverse_geocode":
      return {
        tool,
        input: {
          ...(params["lat"] !== undefined ? { lat: params["lat"] } : {}),
          ...(params["lng"] !== undefined ? { lng: params["lng"] } : {}),
        },
      };
    case "sg_onemap_route":
      return {
        tool,
        input: {
          ...(params["startLat"] !== undefined ? { startLat: params["startLat"] } : {}),
          ...(params["startLng"] !== undefined ? { startLng: params["startLng"] } : {}),
          ...(params["endLat"] !== undefined ? { endLat: params["endLat"] } : {}),
          ...(params["endLng"] !== undefined ? { endLng: params["endLng"] } : {}),
          routeType: (params["routeType"] ?? "pt") as "walk" | "drive" | "pt" | "cycle",
        },
      };
    case "sg_onemap_convert_coords":
      return {
        tool,
        input: {
          ...(params["from"] !== undefined ? { from: params["from"] } : {}),
          ...(params["x"] !== undefined ? { x: params["x"] } : {}),
          ...(params["y"] !== undefined ? { y: params["y"] } : {}),
        },
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
          ...(params["flatType"] !== undefined ? { flatType: params["flatType"] } : {}),
          ...(params["startMonth"] !== undefined ? { startMonth: params["startMonth"] } : {}),
          ...(params["endMonth"] !== undefined ? { endMonth: params["endMonth"] } : {}),
        },
      };
    case "sg_singstat_table":
      return {
        tool,
        input: {
          ...(params["tableId"] !== undefined ? { tableId: params["tableId"] } : {}),
        },
      };
    case "sg_singstat_timeseries":
      return {
        tool,
        input: {
          ...(params["tableId"] !== undefined ? { tableId: params["tableId"] } : {}),
          ...(params["indicator"] !== undefined ? { indicator: params["indicator"] } : {}),
          ...(params["startYear"] !== undefined ? { startYear: params["startYear"] } : {}),
          ...(params["endYear"] !== undefined ? { endYear: params["endYear"] } : {}),
        },
      };
    case "sg_singstat_browse":
      return {
        tool,
        input: {
          ...(params["category"] !== undefined ? { category: params["category"] } : {}),
        },
      };
    case "sg_singstat_search":
      return {
        tool,
        input: { keyword: query },
      };
    case "sg_datagov_resources":
      return {
        tool,
        input: {
          ...(params["datasetId"] !== undefined ? { datasetId: params["datasetId"] } : {}),
        },
      };
    case "sg_datagov_rows":
      return {
        tool,
        input: {
          ...(params["datasetId"] !== undefined ? { datasetId: params["datasetId"] } : {}),
        },
      };
    case "sg_datagov_browse":
      return {
        tool,
        input: {
          ...(params["collection"] !== undefined ? { collection: params["collection"] } : {}),
        },
      };
    case "sg_pa_community_outlets":
      return {
        tool,
        input: {
          ...(params["name"] !== undefined ? { name: params["name"] } : {}),
          ...(params["type"] !== undefined ? { type: params["type"] } : {}),
          ...(params["postalCode"] !== undefined ? { postalCode: params["postalCode"] } : {}),
          ...(params["lat"] !== undefined && params["lng"] !== undefined
            ? { lat: params["lat"], lng: params["lng"] }
            : {}),
          ...(params["radiusKm"] !== undefined ? { radiusKm: params["radiusKm"] } : {}),
        },
      };
    case "sg_pa_resident_network_centres":
      return {
        tool,
        input: {
          ...(params["name"] !== undefined ? { name: params["name"] } : {}),
          ...(params["postalCode"] !== undefined ? { postalCode: params["postalCode"] } : {}),
          ...(params["lat"] !== undefined && params["lng"] !== undefined
            ? { lat: params["lat"], lng: params["lng"] }
            : {}),
          ...(params["radiusKm"] !== undefined ? { radiusKm: params["radiusKm"] } : {}),
        },
      };
    case "sg_sportsg_facilities":
      return {
        tool,
        input: {
          ...(params["name"] !== undefined ? { name: params["name"] } : {}),
          ...(params["facilityType"] !== undefined ? { facilityType: params["facilityType"] } : {}),
          ...(params["postalCode"] !== undefined ? { postalCode: params["postalCode"] } : {}),
          ...(params["lat"] !== undefined && params["lng"] !== undefined
            ? { lat: params["lat"], lng: params["lng"] }
            : {}),
          ...(params["radiusKm"] !== undefined ? { radiusKm: params["radiusKm"] } : {}),
        },
      };
    case "sg_ecda_childcare_centres":
      return {
        tool,
        input: {
          ...(params["name"] !== undefined ? { name: params["name"] } : {}),
          ...(params["postalCode"] !== undefined ? { postalCode: params["postalCode"] } : {}),
          ...(params["centreType"] !== undefined ? { centreType: params["centreType"] } : {}),
          ...(params["operatorType"] !== undefined ? { operatorType: params["operatorType"] } : {}),
          ...(params["hasVacancy"] !== undefined ? { hasVacancy: params["hasVacancy"] } : {}),
          ...(params["lat"] !== undefined && params["lng"] !== undefined
            ? { lat: params["lat"], lng: params["lng"] }
            : {}),
          ...(params["radiusKm"] !== undefined ? { radiusKm: params["radiusKm"] } : {}),
        },
      };
    case "sg_msf_family_services":
      return {
        tool,
        input: {
          ...(params["name"] !== undefined ? { name: params["name"] } : {}),
          ...(params["postalCode"] !== undefined ? { postalCode: params["postalCode"] } : {}),
          ...(params["lat"] !== undefined && params["lng"] !== undefined
            ? { lat: params["lat"], lng: params["lng"] }
            : {}),
          ...(params["radiusKm"] !== undefined ? { radiusKm: params["radiusKm"] } : {}),
        },
      };
    case "sg_msf_student_care_services":
      return {
        tool,
        input: {
          ...(params["name"] !== undefined ? { name: params["name"] } : {}),
          ...(params["postalCode"] !== undefined ? { postalCode: params["postalCode"] } : {}),
          ...(params["auditStatus"] !== undefined ? { auditStatus: params["auditStatus"] } : {}),
          ...(params["scfaOnly"] !== undefined ? { scfaOnly: params["scfaOnly"] } : {}),
          ...(params["lat"] !== undefined && params["lng"] !== undefined
            ? { lat: params["lat"], lng: params["lng"] }
            : {}),
          ...(params["radiusKm"] !== undefined ? { radiusKm: params["radiusKm"] } : {}),
        },
      };
    case "sg_msf_social_service_offices":
      return {
        tool,
        input: {
          ...(params["name"] !== undefined ? { name: params["name"] } : {}),
          ...(params["postalCode"] !== undefined ? { postalCode: params["postalCode"] } : {}),
          ...(params["lat"] !== undefined && params["lng"] !== undefined
            ? { lat: params["lat"], lng: params["lng"] }
            : {}),
          ...(params["radiusKm"] !== undefined ? { radiusKm: params["radiusKm"] } : {}),
        },
      };
    case "sg_cea_salespersons":
      return {
        tool,
        input: {
          ...(params["salespersonName"] !== undefined ? { salespersonName: params["salespersonName"] } : {}),
          ...(params["registrationNo"] !== undefined ? { registrationNo: params["registrationNo"] } : {}),
          ...(params["estateAgentName"] !== undefined ? { estateAgentName: params["estateAgentName"] } : {}),
          ...(params["estateAgentLicenseNo"] !== undefined ? { estateAgentLicenseNo: params["estateAgentLicenseNo"] } : {}),
        },
      };
    case "sg_bca_licensed_builders":
      return {
        tool,
        input: {
          ...(params["companyName"] !== undefined ? { companyName: params["companyName"] } : {}),
          ...(params["uenNo"] !== undefined ? { uenNo: params["uenNo"] } : {}),
          ...(params["classCode"] !== undefined ? { classCode: params["classCode"] } : {}),
        },
      };
    case "sg_bca_registered_contractors":
      return {
        tool,
        input: {
          ...(params["companyName"] !== undefined ? { companyName: params["companyName"] } : {}),
          ...(params["uenNo"] !== undefined ? { uenNo: params["uenNo"] } : {}),
          ...(params["workhead"] !== undefined ? { workhead: params["workhead"] } : {}),
          ...(params["grade"] !== undefined ? { grade: params["grade"] } : {}),
        },
      };
    case "sg_acra_entities":
      return {
        tool,
        input: {
          ...(params["entityName"] !== undefined ? { entityName: params["entityName"] } : {}),
          ...(params["uen"] !== undefined ? { uen: params["uen"] } : {}),
        },
      };
    case "sg_boa_architects":
      return {
        tool,
        input: {
          ...(params["entityName"] !== undefined ? { name: params["entityName"] } : {}),
          ...(params["registrationNo"] !== undefined ? { registrationNo: params["registrationNo"] } : {}),
          ...(params["companyName"] !== undefined ? { firmName: params["companyName"] } : {}),
        },
      };
    case "sg_boa_architecture_firms":
      return {
        tool,
        input: {
          ...(params["companyName"] !== undefined ? { firmName: params["companyName"] } : {}),
        },
      };
    case "sg_hsa_licensed_pharmacies":
      return {
        tool,
        input: {
          ...(params["entityName"] !== undefined ? { pharmacyName: params["entityName"] } : {}),
          ...(params["postalCode"] !== undefined ? { postalCode: params["postalCode"] } : {}),
        },
      };
    case "sg_hsa_health_product_licensees":
      return {
        tool,
        input: {
          ...(params["companyName"] !== undefined ? { companyName: params["companyName"] } : {}),
        },
      };
    case "sg_hlb_hotels":
      return {
        tool,
        input: {
          ...(params["entityName"] !== undefined
            ? (/keeper|operator/i.test(query) ? { keeperName: params["entityName"] } : { name: params["entityName"] })
            : {}),
          ...(params["postalCode"] !== undefined ? { postalCode: params["postalCode"] } : {}),
          ...(params["lat"] !== undefined && params["lng"] !== undefined
            ? { lat: params["lat"], lng: params["lng"] }
            : {}),
          ...(params["radiusKm"] !== undefined ? { radiusKm: params["radiusKm"] } : {}),
        },
      };
    case "sg_business_dossier":
      return {
        tool,
        input: {
          ...(params["entityName"] !== undefined ? { entityName: params["entityName"] } : {}),
          ...(params["uen"] !== undefined ? { uen: params["uen"] } : {}),
          ...(params["salespersonName"] !== undefined ? { salespersonName: params["salespersonName"] } : {}),
          ...(params["registrationNo"] !== undefined ? { registrationNo: params["registrationNo"] } : {}),
          ...(params["estateAgentName"] !== undefined ? { estateAgentName: params["estateAgentName"] } : {}),
          ...(params["estateAgentLicenseNo"] !== undefined ? { estateAgentLicenseNo: params["estateAgentLicenseNo"] } : {}),
          ...(params["classCode"] !== undefined ? { classCode: params["classCode"] } : {}),
          ...(params["workhead"] !== undefined ? { workhead: params["workhead"] } : {}),
          ...(params["grade"] !== undefined ? { grade: params["grade"] } : {}),
          ...(params["modules"] !== undefined ? { modules: params["modules"] } : {}),
          ...(params["sectorHints"] !== undefined ? { sectorHints: params["sectorHints"] } : {}),
        },
      };
    case "sg_property_brief":
      return {
        tool,
        input: {
          ...(params["planningArea"] !== undefined ? { planningArea: params["planningArea"] } : {}),
          ...(params["postalCode"] !== undefined ? { postalCode: params["postalCode"] } : {}),
        },
      };
    case "sg_macro_brief":
      return {
        tool,
        input: {
          ...(params["currency"] !== undefined ? { currency: params["currency"] } : {}),
          ...(params["date"] !== undefined ? { date: params["date"] } : {}),
          ...(params["startDate"] !== undefined ? { startDate: params["startDate"] } : {}),
          ...(params["endDate"] !== undefined ? { endDate: params["endDate"] } : {}),
        },
      };
    default:
      return {
        tool,
        input: { keyword: query },
      };
  }
};
