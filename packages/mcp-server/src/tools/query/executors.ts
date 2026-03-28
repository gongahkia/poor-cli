import type { ToolResult } from "@sg-apis/shared";
import { handleAcraEntities } from "../acra-tools.js";
import {
  handleBcaLicensedBuilders,
  handleBcaRegisteredContractors,
} from "../bca-tools.js";
import { handleBoaArchitects, handleBoaArchitectureFirms } from "../boa-tools.js";
import {
  handleBusinessDossier,
  handleEnvironmentBrief,
  handleMacroBrief,
  handlePropertyBrief,
  handleTransportBrief,
} from "../brief-tools.js";
import { handleCeaSalespersons } from "../cea-tools.js";
import {
  handleDatagovBrowse,
  handleDatagovGet,
  handleDatagovResources,
  handleDatagovRows,
  handleDatagovSearch,
} from "../datagov-tools.js";
import { handleEcdaChildcareCentres } from "../ecda-tools.js";
import { handleGeBIZTenders } from "../gebiz-tools.js";
import { handleHawkerCentres } from "../hawker-tools.js";
import { handleHdbRentalPrices, handleHdbResalePrices } from "../hdb-tools.js";
import { handleHlbHotels } from "../hlb-tools.js";
import { handleHsaHealthProductLicensees, handleHsaLicensedPharmacies } from "../hsa-tools.js";
import { handleLtaBusArrivals, handleLtaTrafficIncidents, handleLtaTrainAlerts } from "../lta-tools.js";
import {
  handleMasExchangeRates,
  handleMasFinancialStats,
  handleMasInterestRates,
} from "../mas-tools.js";
import { handleMoeSchools } from "../moe-tools.js";
import { handleMohFacilities } from "../moh-tools.js";
import { handleMomLabourStats } from "../mom-tools.js";
import {
  handleMsfFamilyServices,
  handleMsfSocialServiceOffices,
  handleMsfStudentCareServices,
} from "../msf-tools.js";
import { handleNeaAirQuality, handleNeaForecast2Hr, handleNeaRainfall } from "../nea-tools.js";
import { handleNParks } from "../nparks-tools.js";
import {
  handleOneMapConvertCoords,
  handleOneMapGeocode,
  handleOneMapPopulation,
  handleOneMapReverseGeocode,
  handleOneMapRoute,
} from "../onemap-tools.js";
import { handlePaCommunityOutlets, handlePaResidentNetworkCentres } from "../pa-tools.js";
import { handlePubWaterLevels } from "../pub-tools.js";
import { handleSfaEstablishments } from "../sfa-tools.js";
import {
  handleSingStatBrowse,
  handleSingStatSearch,
  handleSingStatTable,
  handleSingStatTimeseries,
} from "../singstat-tools.js";
import { handleSportSgFacilities } from "../sportsg-tools.js";
import { handleStbVisitorStats } from "../stb-tools.js";
import {
  handleUraDevCharges,
  handleUraPlanningArea,
  handleUraPropertyTransactions,
} from "../ura-tools.js";

export type ToolExecutor = (params: Readonly<Record<string, unknown>>) => Promise<ToolResult>;

export const TOOL_EXECUTORS: Readonly<Record<string, ToolExecutor>> = {
  sg_acra_entities: async (params) =>
    handleAcraEntities(params as Parameters<typeof handleAcraEntities>[0]),
  sg_bca_licensed_builders: async (params) =>
    handleBcaLicensedBuilders(params as Parameters<typeof handleBcaLicensedBuilders>[0]),
  sg_bca_registered_contractors: async (params) =>
    handleBcaRegisteredContractors(params as Parameters<typeof handleBcaRegisteredContractors>[0]),
  sg_boa_architects: async (params) =>
    handleBoaArchitects(params as Parameters<typeof handleBoaArchitects>[0]),
  sg_boa_architecture_firms: async (params) =>
    handleBoaArchitectureFirms(params as Parameters<typeof handleBoaArchitectureFirms>[0]),
  sg_cea_salespersons: async (params) =>
    handleCeaSalespersons(params as Parameters<typeof handleCeaSalespersons>[0]),
  sg_business_dossier: async (params) =>
    handleBusinessDossier(params as Parameters<typeof handleBusinessDossier>[0]),
  sg_property_brief: async (params) =>
    handlePropertyBrief(params as Parameters<typeof handlePropertyBrief>[0]),
  sg_macro_brief: async (params) =>
    handleMacroBrief(params as Parameters<typeof handleMacroBrief>[0]),
  sg_transport_brief: async (params) =>
    handleTransportBrief(params as Parameters<typeof handleTransportBrief>[0]),
  sg_environment_brief: async (params) =>
    handleEnvironmentBrief(params as Parameters<typeof handleEnvironmentBrief>[0]),
  sg_singstat_search: async (params) =>
    handleSingStatSearch(params as Parameters<typeof handleSingStatSearch>[0]),
  sg_singstat_table: async (params) =>
    handleSingStatTable(params as Parameters<typeof handleSingStatTable>[0]),
  sg_singstat_timeseries: async (params) =>
    handleSingStatTimeseries(params as Parameters<typeof handleSingStatTimeseries>[0]),
  sg_singstat_browse: async (params) =>
    handleSingStatBrowse(params as Parameters<typeof handleSingStatBrowse>[0]),
  sg_mas_exchange_rates: async (params) =>
    handleMasExchangeRates(params as Parameters<typeof handleMasExchangeRates>[0]),
  sg_mas_interest_rates: async (params) =>
    handleMasInterestRates(params as Parameters<typeof handleMasInterestRates>[0]),
  sg_mas_financial_stats: async (params) =>
    handleMasFinancialStats(params as Parameters<typeof handleMasFinancialStats>[0]),
  sg_onemap_geocode: async (params) =>
    handleOneMapGeocode(params as Parameters<typeof handleOneMapGeocode>[0]),
  sg_onemap_reverse_geocode: async (params) =>
    handleOneMapReverseGeocode(params as Parameters<typeof handleOneMapReverseGeocode>[0]),
  sg_onemap_route: async (params) =>
    handleOneMapRoute(params as Parameters<typeof handleOneMapRoute>[0]),
  sg_onemap_population: async (params) =>
    handleOneMapPopulation(params as Parameters<typeof handleOneMapPopulation>[0]),
  sg_onemap_convert_coords: async (params) =>
    handleOneMapConvertCoords(params as Parameters<typeof handleOneMapConvertCoords>[0]),
  sg_ura_property_transactions: async (params) =>
    handleUraPropertyTransactions(params as Parameters<typeof handleUraPropertyTransactions>[0]),
  sg_ura_planning_area: async (params) =>
    handleUraPlanningArea(params as Parameters<typeof handleUraPlanningArea>[0]),
  sg_ura_dev_charges: async (params) =>
    handleUraDevCharges(params as Parameters<typeof handleUraDevCharges>[0]),
  sg_datagov_search: async (params) =>
    handleDatagovSearch(params as Parameters<typeof handleDatagovSearch>[0]),
  sg_datagov_get: async (params) =>
    handleDatagovGet(params as Parameters<typeof handleDatagovGet>[0]),
  sg_datagov_resources: async (params) =>
    handleDatagovResources(params as Parameters<typeof handleDatagovResources>[0]),
  sg_datagov_rows: async (params) =>
    handleDatagovRows(params as Parameters<typeof handleDatagovRows>[0]),
  sg_datagov_browse: async (params) =>
    handleDatagovBrowse(params as Parameters<typeof handleDatagovBrowse>[0]),
  sg_lta_bus_arrivals: async (params) =>
    handleLtaBusArrivals(params as Parameters<typeof handleLtaBusArrivals>[0]),
  sg_lta_train_alerts: async (params) =>
    handleLtaTrainAlerts(params as Parameters<typeof handleLtaTrainAlerts>[0]),
  sg_lta_traffic_incidents: async (params) =>
    handleLtaTrafficIncidents(params as Parameters<typeof handleLtaTrafficIncidents>[0]),
  sg_nea_forecast_2hr: async (params) =>
    handleNeaForecast2Hr(params as Parameters<typeof handleNeaForecast2Hr>[0]),
  sg_nea_air_quality: async (params) =>
    handleNeaAirQuality(params as Parameters<typeof handleNeaAirQuality>[0]),
  sg_nea_rainfall: async (params) =>
    handleNeaRainfall(params as Parameters<typeof handleNeaRainfall>[0]),
  sg_hdb_resale_prices: async (params) =>
    handleHdbResalePrices(params as Parameters<typeof handleHdbResalePrices>[0]),
  sg_hdb_rental_prices: async (params) =>
    handleHdbRentalPrices(params as Parameters<typeof handleHdbRentalPrices>[0]),
  sg_gebiz_tenders: async (params) =>
    handleGeBIZTenders(params as Parameters<typeof handleGeBIZTenders>[0]),
  sg_hawker_centres: async (params) =>
    handleHawkerCentres(params as Parameters<typeof handleHawkerCentres>[0]),
  sg_moe_schools: async (params) =>
    handleMoeSchools(params as Parameters<typeof handleMoeSchools>[0]),
  sg_moh_facilities: async (params) =>
    handleMohFacilities(params as Parameters<typeof handleMohFacilities>[0]),
  sg_hsa_licensed_pharmacies: async (params) =>
    handleHsaLicensedPharmacies(params as Parameters<typeof handleHsaLicensedPharmacies>[0]),
  sg_hsa_health_product_licensees: async (params) =>
    handleHsaHealthProductLicensees(params as Parameters<typeof handleHsaHealthProductLicensees>[0]),
  sg_hlb_hotels: async (params) =>
    handleHlbHotels(params as Parameters<typeof handleHlbHotels>[0]),
  sg_pa_community_outlets: async (params) =>
    handlePaCommunityOutlets(params as Parameters<typeof handlePaCommunityOutlets>[0]),
  sg_pa_resident_network_centres: async (params) =>
    handlePaResidentNetworkCentres(params as Parameters<typeof handlePaResidentNetworkCentres>[0]),
  sg_sportsg_facilities: async (params) =>
    handleSportSgFacilities(params as Parameters<typeof handleSportSgFacilities>[0]),
  sg_ecda_childcare_centres: async (params) =>
    handleEcdaChildcareCentres(params as Parameters<typeof handleEcdaChildcareCentres>[0]),
  sg_msf_family_services: async (params) =>
    handleMsfFamilyServices(params as Parameters<typeof handleMsfFamilyServices>[0]),
  sg_msf_student_care_services: async (params) =>
    handleMsfStudentCareServices(params as Parameters<typeof handleMsfStudentCareServices>[0]),
  sg_msf_social_service_offices: async (params) =>
    handleMsfSocialServiceOffices(params as Parameters<typeof handleMsfSocialServiceOffices>[0]),
  sg_sfa_establishments: async (params) =>
    handleSfaEstablishments(params as Parameters<typeof handleSfaEstablishments>[0]),
  sg_nparks_parks: async (params) =>
    handleNParks(params as Parameters<typeof handleNParks>[0]),
  sg_pub_water_levels: async (params) =>
    handlePubWaterLevels(params as Parameters<typeof handlePubWaterLevels>[0]),
  sg_mom_labour_stats: async (params) =>
    handleMomLabourStats(params as Parameters<typeof handleMomLabourStats>[0]),
  sg_stb_visitor_stats: async (params) =>
    handleStbVisitorStats(params as Parameters<typeof handleStbVisitorStats>[0]),
};

export const executeQueryTool = async (
  toolName: string,
  input: Readonly<Record<string, unknown>>,
): Promise<ToolResult> => {
  const executor = TOOL_EXECUTORS[toolName];
  if (executor === undefined) {
    throw new Error(`No executor for tool: ${toolName}`);
  }
  return executor(input);
};
