import type { BusinessDossierModule, BusinessSectorHint } from "../diligence/entity-resolution.js";
import { PLANNING_AREAS, REGIONS, ROUTE_MODES, toTitleCase } from "./domain-constants.js";

export type IntentResult = {
  readonly intent: string;
  readonly workflow: string;
  readonly tool?: string;
  readonly apis: readonly string[];
  readonly confidence: number;
  readonly extractedParams: Readonly<Record<string, unknown>>;
};

export const BUSINESS_DILIGENCE_PATTERN = /\bdiligence\b|regulatory|registration\s*check|registry\s*check|registry\s*diligence|business\s*diligence|counterparty\s*diligence|licen[cs]e\s*check|business\s*dossier|company\s*dossier/i;

const CURRENCY_STOPWORDS = new Set(["GDP", "CPI", "MRT", "HDB", "LTA", "NEA", "CEA", "BCA", "ACRA"]);
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

export const extractPostalCode = (query: string): string | null => {
  const match = query.match(/\b(\d{6})\b/);
  return match?.[1] ?? null;
};

export const extractPostalCodes = (query: string): readonly string[] => {
  return Array.from(query.matchAll(/\b(\d{6})\b/g), (match) => match[1] ?? "");
};

export const extractCoordinatePairs = (
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

export const extractSvy21Pair = (query: string): { x: number; y: number } | null => {
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

export const extractRouteType = (query: string): "walk" | "drive" | "pt" | "cycle" | null => {
  if (/\bwalk|walking\b/i.test(query)) return ROUTE_MODES[0];
  if (/\bdrive|driving\b/i.test(query)) return ROUTE_MODES[1];
  if (/\bcycle|cycling\b/i.test(query)) return ROUTE_MODES[3];
  if (/\bpublic transport|train|mrt|bus\b/i.test(query)) return ROUTE_MODES[2];
  return null;
};

export const extractTableId = (query: string): string | null => {
  const match = query.match(/\b([A-Z]\d{6}[A-Z]?)\b/i);
  return match?.[1] ?? null;
};

export const extractBusStopCode = (query: string): string | null => {
  const match = query.match(/\b(\d{5})\b/);
  return match?.[1] ?? null;
};

export const extractPlanningArea = (query: string): string | null => {
  const lower = query.toLowerCase();
  for (const area of PLANNING_AREAS) {
    if (lower.includes(area)) {
      return toTitleCase(area);
    }
  }
  return null;
};

export const extractCurrency = (query: string): string | null => {
  if (!/\b(currency|exchange\s*rate|forex|fx|against|versus|vs\.?|to\s+[A-Z]{3}\b|in\s+[A-Z]{3}\b)\b/i.test(query)) {
    return null;
  }

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

export const extractIsoDate = (query: string): string | null => {
  const match = query.match(/\b(\d{4}-\d{2}-\d{2})\b/);
  return match?.[1] ?? null;
};

export const extractDatasetId = (query: string): string | null => {
  const match = query.match(/\b(d_[a-f0-9]{32})\b/i);
  return match?.[1] ?? null;
};

export const extractMonthRange = (
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

export const extractYearRange = (query: string): { startYear?: number; endYear?: number } => {
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

export const extractBusService = (query: string): string | null => {
  const match = query.match(/\b(?:service|bus)\s+([0-9A-Z]{1,5})\b/i);
  return match?.[1]?.toUpperCase() ?? null;
};

export const extractRegion = (query: string): string | null => {
  const lower = query.toLowerCase();
  for (const region of REGIONS) {
    if (lower.includes(region)) {
      return toTitleCase(region);
    }
  }
  return null;
};

export const extractStationId = (query: string): string | null => {
  const match = query.match(/\b(S\d{3})\b/i);
  return match?.[1]?.toUpperCase() ?? null;
};

export const extractLocationPhrase = (query: string): string | null => {
  const match = query.match(
    /\b(?:near|around|by|at|in)\s+(.+?)(?=\s+(?:with|for|called|named)\b|[?.!,]|$)/i,
  );
  return match?.[1]?.trim() ?? null;
};

export const extractQuotedTerm = (query: string): string | null => {
  const match = query.match(/["""'`]\s*([^"""'`]{2,}?)\s*["""'`]/);
  return match?.[1]?.trim() ?? null;
};

export const extractIndicator = (query: string): string | null => {
  const explicit = query.match(/\bindicator\s+(.+?)(?=\s+(?:from|table|for|between)\b|[?.!,]|$)/i);
  if (explicit?.[1] !== undefined) {
    return explicit[1].trim();
  }
  return extractQuotedTerm(query);
};

export const extractFlatType = (query: string): string | null => {
  const match = query.match(/\b(STUDIO APARTMENT|MULTI-GENERATION|EXECUTIVE|[1-5]\s*ROOM)\b/i);
  return match?.[1]?.replace(/\s+/g, " ").toUpperCase() ?? null;
};

const GENERIC_BUSINESS_IDENTIFIER_VALUES = new Set([
  "architect",
  "architecture firm",
  "builder",
  "business",
  "business diligence",
  "business dossier",
  "company",
  "contractor",
  "counterparty",
  "diligence",
  "entity",
  "hotel",
  "hotel operator",
  "importer",
  "keeper",
  "manufacturer",
  "operator",
  "pharmacy",
  "supplier",
  "vendor",
  "wholesaler",
]);

const normalizeBusinessIdentifier = (value: string): string => {
  return value
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
};

const trimTrailingBusinessPunctuation = (value: string): string => {
  const withoutSentencePunctuation = value.replace(/[,;:!?]+$/, "").trim();
  if (!withoutSentencePunctuation.endsWith(".")) {
    return withoutSentencePunctuation;
  }

  return /\b(?:bhd|co|corp|inc|llc|llp|ltd|plc|pte)\.$/i.test(withoutSentencePunctuation)
    ? withoutSentencePunctuation
    : withoutSentencePunctuation.replace(/\.+$/, "");
};

const isGenericBusinessIdentifier = (value: string): boolean => {
  const normalized = normalizeBusinessIdentifier(value).replace(/^(?:a|an|the)\s+/, "");
  return normalized === "" || GENERIC_BUSINESS_IDENTIFIER_VALUES.has(normalized);
};

const stripTrailingBusinessContext = (value: string): string => {
  return value
    .replace(
      /^(?:architecture\s+firm\s+diligence|healthcare\s+supplier\s+diligence|hotel\s+operator\s+lookup|sector[-\s]*scoped\s+business\s+diligence|business\s+diligence|business\s+dossier|registry\s+diligence|counterparty\s+diligence|diligence|lookup|check)\s+for\s+/i,
      "",
    )
    .replace(
      /\s+(?:with|using|under|by|for)\s+(?:uen|registration|reg(?:istration)?|licen[cs]e|grade|workhead|builder\s*class|details|records?).*$/i,
      "",
    )
    .replace(
      /\s+in\s+(?:construction|procurement|healthcare|hospitality|architecture|real\s*estate)(?:\s+\w+)*$/i,
      "",
    )
    .replace(
      /\s+(?:uen(?:\s*(?:number|no\.?))?\s*[:#]?\s*[0-9A-Z]{8,10}|registration(?:\s*(?:number|no\.?))?\s*[:#]?\s*[0-9A-Z-]{5,}|reg(?:istration)?\s*[:#]?\s*[0-9A-Z-]{5,}|licen[cs]e(?:\s*(?:number|no\.?))?\s*[:#]?\s*[0-9A-Z-]{5,}|workhead\s+[A-Z]{2}\d{2}|grade\s+[A-Z]\d|class\s+[A-Z]{2}\d|builder\s*class\s+[A-Z]{2}\d|details?|records?)$/i,
      "",
    )
    .replace(/^(?:the)\s+/, "")
    .trim();
};

const sanitizeNamedSubject = (value: string): string => {
  return trimTrailingBusinessPunctuation(
    stripTrailingBusinessContext(value)
      .replace(/^["""'`]\s*|\s*["""'`]$/g, "")
      .trim(),
  )
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
      const cleaned = sanitizeNamedSubject(candidate);
      if (cleaned !== "" && !isGenericBusinessIdentifier(cleaned)) {
        return cleaned;
      }
    }
  }
  return null;
};

export const extractNamedFacility = (query: string): string | null => {
  return extractNamedSubject(query, [
    /\b(?:named|called)\s+(.+?)(?=\s+(?:near|around|by|at|in|with|for)\b|[?.!,]|$)/i,
  ]) ?? (
    /(community\s+club|passion\s*wave|resident(?:s')?\s*(?:committee|network)|sportsg|sports?\s+facility|child\s*care|childcare|preschool|kindergarten|family\s+service\s+cent(?:re|er)|student\s+care|social\s+service\s+office)/i.test(query)
      ? extractQuotedTerm(query)
      : null
  );
};

export const extractSportSgFacilityType = (query: string): string | null => {
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

export const extractChildcareCentreType = (query: string): string | null => {
  if (/\bkindergarten\b/i.test(query)) return "KN";
  if (/\bchild\s*care|childcare|preschool\b/i.test(query)) return "CC";
  return null;
};

export const extractAuditStatus = (query: string): string | null => {
  const match = query.match(/\bgrade\s*([abc])\b/i);
  return match?.[1] === undefined ? null : `Grade ${match[1].toUpperCase()}`;
};

export type CivicModule = "pa" | "sportsg" | "ecda" | "msf" | "hawker";

export const extractCivicModules = (query: string): readonly CivicModule[] => {
  const modules = new Set<CivicModule>();
  if (/\bcommunity\s+club|passion\s*wave|resident(?:s')?\s*(?:committee|network)|\brn\b|\brc\b|\bcc\b/i.test(query)) {
    modules.add("pa");
  }
  if (/\bsportsg\b|\bsports?\s+facility\b|\bswim(?:ming)?|pool\b|\btennis\b|\bsquash\b|\bstadium\b|\bsports?\s+hall\b|\bsport(?:s)?\s+centre\b|\bhockey\b|\barchery\b/i.test(query)) {
    modules.add("sportsg");
  }
  if (/\bchild\s*care\b|\bchildcare\b|\bpreschool\b|\bkindergarten\b|\becda\b/i.test(query)) {
    modules.add("ecda");
  }
  if (/\bfamily\s+services?\b|\bfamily\s+service\s+cent(?:re|er)s?\b|\bfsc\b|\bstudent\s+care\b|\bscfa\b|\bsocial\s+service\s+offices?\b|\bsso\b|\bmsf\b/i.test(query)) {
    modules.add("msf");
  }
  if (/\bhawker\s+cent(?:re|er)s?\b|\bhawker\b/i.test(query)) {
    modules.add("hawker");
  }
  return Array.from(modules);
};

export const detectCivicTool = (query: string): string | null => {
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

export const extractSingStatCategory = (query: string): string | null => {
  if (!/\b(singstat|dataset|table|indicator|macro|economic|economy|statistics?|stats|category|browse)\b/i.test(query)) {
    return null;
  }

  for (const matcher of SINGSTAT_CATEGORY_MATCHERS) {
    if (matcher.pattern.test(query)) {
      return matcher.category;
    }
  }
  return null;
};

export const extractCollection = (query: string): string | null => {
  const explicit = query.match(/\bcollection\s+(.+?)(?=\s+(?:datasets?|data|resources?|rows?)\b|[?.!,]|$)/i);
  if (explicit?.[1] !== undefined) {
    return explicit[1].trim();
  }
  return /collection/i.test(query) ? extractQuotedTerm(query) : null;
};

export const extractUseGroup = (query: string): string | null => {
  const explicit = query.match(/\buse\s+group\s+(.+?)(?=\s+(?:sector|rate|rates)\b|[?.!,]|$)/i);
  return explicit?.[1]?.trim() ?? null;
};

export const extractSector = (query: string): string | null => {
  const explicit = query.match(/\bsector\s+(.+?)(?=\s+(?:use\s+group|rate|rates)\b|[?.!,]|$)/i);
  return explicit?.[1]?.trim() ?? null;
};

export const extractCoordinateSource = (query: string): "SVY21" | "WGS84" | null => {
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

export const extractCompanyName = (query: string): string | null => {
  return extractNamedSubject(query, [
    /\b(?:architecture\s+firm\s+diligence|healthcare\s+supplier\s+diligence|hotel\s+operator\s+lookup|sector[-\s]*scoped\s+business\s+diligence|business\s+diligence|business\s+dossier|registry\s+diligence|counterparty\s+diligence)\s+for\s+(?:(?:a|an|the)\s+)?(?:architecture\s+firm|hotel\s+operator|company|entity|business|counterparty|builder|contractor|vendor|architect|pharmacy|supplier|manufacturer|importer|wholesaler|hotel|keeper|operator)?\s*(.+?)(?=\s+(?:with|using|under|and\s+include|include|return|in\s+(?:construction|procurement|healthcare|hospitality|architecture|real\s*estate))\b|[?!,;:]|$)/i,
    /\b(?:company|entity|business|counterparty)\s+(.+?)(?=\s+(?:with|using|under|in\s+(?:construction|procurement|healthcare|hospitality|architecture|real\s*estate))\b|[?!,;:]|$)/i,
    /\b(?:builder|contractor|vendor)\s+(.+?)(?=\s+(?:with|using|under|in\s+(?:construction|procurement|healthcare|hospitality|architecture|real\s*estate))\b|[?!,;:]|$)/i,
    /\b(?:architecture\s+firm|hotel\s+operator|architect|pharmacy|supplier|manufacturer|importer|wholesaler|hotel|keeper|operator)\s+(.+?)(?=\s+(?:with|using|under|and\s+include|include|return|in\s+(?:construction|procurement|healthcare|hospitality|architecture|real\s*estate))\b|[?!,;:]|$)/i,
  ]) ?? extractQuotedTerm(query);
};

export const extractSalespersonName = (query: string): string | null => {
  return extractNamedSubject(query, [
    /\bsalesperson\s+(.+?)(?=\s+(?:with|using|under|registration|licen[cs]e|estate\s+agent)\b|[?.!,]|$)/i,
  ]) ?? (/salesperson/i.test(query) ? extractQuotedTerm(query) : null);
};

export const extractEstateAgentName = (query: string): string | null => {
  return extractNamedSubject(query, [
    /\bestate\s+agent\s+(.+?)(?=\s+(?:with|using|under|registration|licen[cs]e|salesperson)\b|[?.!,]|$)/i,
  ]) ?? (/estate\s+agent/i.test(query) ? extractQuotedTerm(query) : null);
};

export const extractUen = (query: string): string | null => {
  const explicit = query.match(/\buen(?:\s*(?:number|no\.?))?\s*[:#]?\s*([0-9A-Z]{8,10})\b/i);
  return explicit?.[1]?.toUpperCase() ?? null;
};

export const extractRegistrationNo = (query: string): string | null => {
  const direct = query.match(/\bR\d{6}[A-Z]\b/i);
  if (direct !== null) {
    return direct[0]?.toUpperCase() ?? null;
  }

  return query
    .match(/\bregistration(?:\s*(?:number|no\.?))?\s*[:#]?\s*([0-9A-Z-]{5,})\b/i)?.[1]
    ?.toUpperCase() ?? null;
};

export const extractEstateAgentLicenseNo = (query: string): string | null => {
  const direct = query.match(/\bL\d{7}[A-Z]\b/i);
  if (direct !== null) {
    return direct[0]?.toUpperCase() ?? null;
  }

  return query
    .match(/\blicen[cs]e(?:\s*(?:number|no\.?))?\s*[:#]?\s*([0-9A-Z-]{5,})\b/i)?.[1]
    ?.toUpperCase() ?? null;
};

export const extractWorkhead = (query: string): string | null => {
  return query.match(/\bworkhead\s+([A-Z]{2}\d{2})\b/i)?.[1]?.toUpperCase() ?? null;
};

export const extractGrade = (query: string): string | null => {
  return query.match(/\bgrade\s+([A-Z]\d)\b/i)?.[1]?.toUpperCase() ?? null;
};

export const extractBuilderClassCode = (query: string): string | null => {
  const explicit = query.match(/\b(GB[12])\b/i);
  if (explicit !== null) {
    return explicit[1]?.toUpperCase() ?? null;
  }

  return query.match(/\bclass\s+([A-Z]{2}\d)\b/i)?.[1]?.toUpperCase() ?? null;
};

export const countMacroSignals = (lower: string): number => {
  return [
    /gdp/.test(lower),
    /cpi|inflation/.test(lower),
    /exchange\s*rate|forex|currency\s*rate|sgd/.test(lower),
    /sora|interest\s*rate/.test(lower),
    /unemployment|trade|econom/.test(lower),
  ].filter(Boolean).length;
};

export const getApiForTool = (tool: string): string => {
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
  if (tool.startsWith("sg_sfa_")) return "sfa";
  if (tool.startsWith("sg_nparks_")) return "nparks";
  if (tool.startsWith("sg_nlb_")) return "nlb";
  if (tool.startsWith("sg_law_")) return "law";
  if (tool.startsWith("sg_pa_")) return "pa";
  if (tool.startsWith("sg_sportsg_")) return "sportsg";
  if (tool.startsWith("sg_ecda_")) return "ecda";
  if (tool === "sg_msf_family_services") return "msf_family_services";
  if (tool === "sg_msf_student_care_services") return "msf_student_care_services";
  if (tool === "sg_msf_social_service_offices") return "msf_social_service_offices";
  if (tool === "sg_gebiz_tenders") return "gebiz";
  return "datagov";
};

export const extractSectorHints = (query: string): readonly BusinessSectorHint[] => {
  const hints: BusinessSectorHint[] = [];
  if (/\bconstruction|builder|contractor|workhead\b/i.test(query)) hints.push("construction");
  if (/\breal\s*estate|estate\s*agent|salesperson|property\b/i.test(query)) hints.push("real_estate");
  if (/\barchitect|architecture\s+firm|boa\b/i.test(query)) hints.push("architecture");
  if (/\bpharmacy|pharmacies|health\s+product|healthcare|medical\s+device|hsa\b/i.test(query)) hints.push("healthcare");
  if (/\bhotel|hospitality|keeper|hlb\b/i.test(query)) hints.push("hospitality");
  if (/\bprocurement|supplier|tender|gebiz\b/i.test(query)) hints.push("procurement");
  return Array.from(new Set(hints));
};

export const extractExplicitModules = (query: string): readonly BusinessDossierModule[] => {
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

export const buildIntentResult = (
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
