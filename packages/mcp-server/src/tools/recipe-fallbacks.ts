// Side-effect-free recipe -> fallback tools lookup. Imported by both
// query-tool.ts (for unsupported-response direct-tool hints) and the
// catalog-parity test (which validates this table stays aligned with the
// catalog's fallbackTools fields). Keeping this data here avoids the
// circular import chain query-tool -> catalog -> tool-set -> query-tool.
//
// Keys are slugified recipe ids that exist in RECIPE_CATALOG. When a recipe
// id does not match a keyword-hint name, the keyword hint falls through to
// the empty fallbacks list and the unsupported-response markdown still shows
// the nearest recipe prompt without a misleading direct-tool list.
export const RECIPE_FALLBACK_TOOLS: Readonly<Record<string, readonly string[]>> = {
  postal_route: ["sg_onemap_geocode", "sg_onemap_route"],
  reverse_geocode: ["sg_onemap_reverse_geocode"],
  coordinate_conversion: ["sg_onemap_convert_coords"],
  singstat_drilldown: ["sg_singstat_browse", "sg_singstat_table", "sg_singstat_timeseries"],
  data_gov_collection_browse: ["sg_datagov_browse", "sg_datagov_search", "sg_datagov_resources", "sg_datagov_rows"],
  ura_development_charges: ["sg_ura_dev_charges"],
  hdb_rental_check: ["sg_hdb_rental_prices"],
  business_due_diligence: ["sg_business_dossier", "sg_acra_entities", "sg_bca_licensed_builders"],
  bus_stop_status: ["sg_lta_bus_arrivals", "sg_transport_brief"],
  outdoor_event_check: ["sg_environment_brief", "sg_nea_forecast_2hr", "sg_nea_air_quality"],
  community_club_near_postal_code: ["sg_onemap_geocode", "sg_pa_community_outlets"],
};
