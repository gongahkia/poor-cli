// Side-effect-free recipe -> fallback tools lookup. Imported by both
// query-tool.ts (for unsupported-response direct-tool hints) and catalog.ts
// (which validates parity against this table at module load). Keeping this
// data here avoids the circular import chain query-tool -> catalog ->
// tool-set -> query-tool.
//
// Keys are slugified recipe ids matching catalog-surface.ts:slugify(recipeName).
export const RECIPE_FALLBACK_TOOLS: Readonly<Record<string, readonly string[]>> = {
  postal_route: ["sg_onemap_geocode", "sg_onemap_route", "sg_onemap_reverse_geocode"],
  reverse_geocode: ["sg_onemap_geocode", "sg_onemap_route", "sg_onemap_reverse_geocode"],
  coordinate_conversion: ["sg_onemap_convert_coords"],
  singstat_drilldown: ["sg_singstat_browse", "sg_singstat_search", "sg_singstat_table", "sg_singstat_timeseries"],
  dataset_discovery_fallback: ["sg_datagov_search", "sg_datagov_get", "sg_datagov_resources", "sg_datagov_rows"],
  macro_snapshot: ["sg_macro_brief", "sg_mas_exchange_rates", "sg_singstat_search"],
  property_due_diligence: ["sg_property_brief", "sg_ura_property_transactions", "sg_hdb_resale_prices"],
  transport_status: ["sg_transport_brief", "sg_lta_bus_arrivals", "sg_lta_train_alerts", "sg_lta_traffic_incidents"],
  environment_snapshot: ["sg_environment_brief", "sg_nea_forecast_2hr", "sg_nea_air_quality", "sg_nea_rainfall"],
  business_registry_diligence: ["sg_business_dossier", "sg_acra_entities", "sg_bca_licensed_builders", "sg_bca_registered_contractors", "sg_cea_salespersons"],
  civic_discovery: ["sg_civic_brief", "sg_pa_community_outlets", "sg_sportsg_facilities", "sg_ecda_childcare_centres", "sg_msf_family_services"],
  hdb_resale_check: ["sg_property_brief", "sg_hdb_resale_prices", "sg_ura_property_transactions"],
  hdb_rental_check: ["sg_hdb_rental_prices", "sg_hdb_resale_prices"],
  ura_development_charges: ["sg_ura_dev_charges", "sg_ura_planning_area"],
};
