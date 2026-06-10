import { resolveAlias } from "./aliases.js";
import {
  BUSINESS_DILIGENCE_PATTERN,
  buildIntentResult,
  countMacroSignals,
  detectCivicTool,
  extractAuditStatus,
  extractBuilderClassCode,
  extractBusService,
  extractBusStopCode,
  extractChildcareCentreType,
  extractCollection,
  extractCompanyName,
  extractCoordinatePairs,
  extractCoordinateSource,
  extractCurrency,
  extractDatasetId,
  extractEstateAgentLicenseNo,
  extractEstateAgentName,
  extractExplicitModules,
  extractFlatType,
  extractGrade,
  extractIndicator,
  extractIsoDate,
  extractLocationPhrase,
  extractMonthRange,
  extractNamedFacility,
  extractPlanningArea,
  extractPostalCode,
  extractPostalCodes,
  extractRegion,
  extractRegistrationNo,
  extractRouteType,
  extractSalespersonName,
  extractSector,
  extractSectorHints,
  extractSingStatCategory,
  extractSportSgFacilityType,
  extractStationId,
  extractSvy21Pair,
  extractTableId,
  extractUen,
  extractUseGroup,
  extractWorkhead,
  extractYearRange,
  getApiForTool,
  type IntentResult,
} from "./extractors.js";
export type { IntentResult } from "./extractors.js";

type KnownMacroTable = {
  readonly tableId: string;
  readonly variables: readonly string[];
};

const resolveKnownMacroTable = (lower: string): KnownMacroTable | null => {
  if (/\bcpi\b/.test(lower) && /\bindex\b/.test(lower)) {
    return { tableId: "M213751", variables: ["All Items"] };
  }
  if (/\bcpi\b|inflation/.test(lower)) {
    return { tableId: "M213781", variables: ["All Items"] };
  }
  if (/\bgdp\b/.test(lower)) {
    return { tableId: "M015631", variables: ["GDP At Current Market Prices"] };
  }
  return null;
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

  if (/\bprimary\b/i.test(lower)) {
    params["level"] = "PRIMARY";
  } else if (/\bsecondary\b/i.test(lower)) {
    params["level"] = "SECONDARY";
  } else if (/\bjunior\s+college\b|\bjc\b/i.test(lower)) {
    params["level"] = "JUNIOR COLLEGE";
  }

  if (/\bwest\s+zone\b|\bwest\b/i.test(lower)) {
    params["zone"] = "WEST";
  } else if (/\beast\s+zone\b|\beast\b/i.test(lower)) {
    params["zone"] = "EAST";
  } else if (/\bnorth\s+zone\b|\bnorth\b/i.test(lower)) {
    params["zone"] = "NORTH";
  } else if (/\bsouth\s+zone\b|\bsouth\b/i.test(lower)) {
    params["zone"] = "SOUTH";
  } else if (/\bcentral\s+zone\b|\bcentral\b/i.test(lower)) {
    params["zone"] = "CENTRAL";
  }

  if (/\bhospitals?\b/i.test(lower)) {
    params["type"] = "HOSPITAL";
  } else if (/\bclinics?\b|\bpolyclinics?\b/i.test(lower)) {
    params["type"] = "CLINIC";
  }

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
  const knownMacroTable = resolveKnownMacroTable(lower);

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
    && /business\s*diligence|business\s*dossier|company\s*dossier|counterparty\s*diligence|acra|company|entity|uen|salesperson|estate\s*agent|builder|contractor|bca|cea|gebiz|architect|pharmacy|health\s+product|hotel/i.test(lower)
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
    if (knownMacroTable !== null) {
      params["tableId"] = knownMacroTable.tableId;
      params["variables"] = knownMacroTable.variables;
    }
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

  if (
    aliasedTool === "sg_moe_schools"
    || /moe\s+school|school\s+directory|school\s+lookup|primary\s+school|secondary\s+school|junior\s+college/i.test(lower)
  ) {
    return buildIntentResult("civic", "direct_tool", 0.87, params, "sg_moe_schools");
  }

  if (
    aliasedTool === "sg_moh_facilities"
    || (
      /\bmoh\b/i.test(lower)
      && /\bhospitals?\b|\bclinics?\b|\bpolyclinics?\b|healthcare\s+facilit/i.test(lower)
    )
    || /hospital\s+directory|clinic\s+directory|healthcare\s+directory/i.test(lower)
  ) {
    return buildIntentResult("civic", "direct_tool", 0.87, params, "sg_moh_facilities");
  }

  if (
    aliasedTool === "sg_nlb_libraries"
    || /\bnlb\b|public\s+librar(?:y|ies)|library\s+directory|libraries\s+(?:near|in|around)/i.test(lower)
  ) {
    return buildIntentResult("civic", "direct_tool", 0.87, params, "sg_nlb_libraries");
  }

  if (
    aliasedTool === "sg_nparks_parks"
    || /\bnparks\b|parks?\s+(?:near|in|around|named|called|directory)|nature\s+reserve|park\s+directory/i.test(lower)
  ) {
    return buildIntentResult("civic", "direct_tool", 0.87, params, "sg_nparks_parks");
  }

  if (
    aliasedTool === "sg_sfa_establishments"
    || /\bsfa\b|licensed\s+food\s+establishments?|food\s+establishments?\s+(?:near|named|called|in|around)|food\s+licen[cs]e/i.test(lower)
  ) {
    return buildIntentResult("civic", "direct_tool", 0.87, params, "sg_sfa_establishments");
  }

  if (
    aliasedTool === "sg_law_search"
    || /singapore\s+(?:statutes?|acts?|law)\s+(?:search|lookup)|sso\s+law|statutes?\s+online|search\s+(?:singapore\s+)?(?:acts?|law|statutes?)/i.test(lower)
  ) {
    return buildIntentResult("law", "direct_tool", 0.87, params, "sg_law_search");
  }

  if (
    aliasedTool?.startsWith("sg_transit_")
    || /transit\s*(health|hotspots?|ops|brief|pack|reliability|transfer|accessib|objective|counterfactual|policy|model)/i.test(lower)
  ) {
    const tool = aliasedTool
      ?? (/hotspots?/i.test(lower)
        ? "sg_transit_hotspots"
        : /health/i.test(lower)
          ? "sg_transit_health"
          : /pack/i.test(lower)
            ? "sg_transit_pack"
            : "sg_transit_ops_brief");
    return buildIntentResult("transport", "direct_tool", 0.92, params, tool);
  }

  if (aliasedTool?.includes("lta") || /bus\s*arrival|train\s*alert|traffic\s*incident|road\s*works|road\s*openings?|traffic\s*(?:camera|image)/i.test(lower)) {
    const tool = aliasedTool
      ?? (/train\s*alert/i.test(lower)
        ? "sg_lta_train_alerts"
        : /traffic\s*incident/i.test(lower)
          ? "sg_lta_traffic_incidents"
          : /road\s*works/i.test(lower)
            ? "sg_lta_road_works"
            : /road\s*openings?/i.test(lower)
              ? "sg_lta_road_openings"
              : /traffic\s*(?:camera|image)/i.test(lower)
                ? "sg_lta_traffic_images"
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

  if (knownMacroTable !== null) {
    params["tableId"] = knownMacroTable.tableId;
    params["variables"] = knownMacroTable.variables;
    return buildIntentResult("economic", "direct_tool", 0.9, params, "sg_singstat_table");
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
    case "sg_moe_schools":
      return {
        tool,
        input: {
          ...(params["level"] !== undefined ? { level: params["level"] } : {}),
          ...(params["zone"] !== undefined ? { zone: params["zone"] } : {}),
          ...(params["name"] !== undefined ? { name: params["name"] } : {}),
        },
      };
    case "sg_moh_facilities":
      return {
        tool,
        input: {
          ...(params["type"] !== undefined ? { type: params["type"] } : {}),
          ...(params["name"] !== undefined ? { name: params["name"] } : {}),
          ...(params["postalCode"] !== undefined ? { postalCode: params["postalCode"] } : {}),
        },
      };
    case "sg_nlb_libraries":
      return {
        tool,
        input: {
          ...(params["name"] !== undefined ? { name: params["name"] } : {}),
          ...(params["region"] !== undefined ? { region: params["region"] } : {}),
          ...(params["postalCode"] !== undefined ? { postalCode: params["postalCode"] } : {}),
        },
      };
    case "sg_nparks_parks":
    case "sg_sfa_establishments":
      return {
        tool,
        input: {
          ...(params["name"] !== undefined ? { name: params["name"] } : {}),
        },
      };
    case "sg_law_search":
      return {
        tool,
        input: {
          query: query
            .replace(/^\s*(?:search|lookup|find|show)\s+(?:singapore\s+)?(?:statutes?|law|acts?|sso\s+law|statutes?\s+online)\s+(?:for|about)?\s*/i, "")
            .replace(/\s+/g, " ")
            .trim() || query,
        },
      };
    case "sg_singstat_table":
      return {
        tool,
        input: {
          ...(params["tableId"] !== undefined ? { tableId: params["tableId"] } : {}),
          ...(params["variables"] !== undefined ? { variables: params["variables"] } : {}),
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
