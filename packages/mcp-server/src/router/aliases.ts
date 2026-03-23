const ALIAS_MAP: Readonly<Record<string, string>> = {
  forex: "sg_mas_exchange_rates",
  "exchange rate": "sg_mas_exchange_rates",
  currency: "sg_mas_exchange_rates",
  sora: "sg_mas_interest_rates",
  "interest rate": "sg_mas_interest_rates",
  "lending rate": "sg_mas_interest_rates",
  gdp: "sg_singstat_search",
  cpi: "sg_singstat_search",
  inflation: "sg_singstat_search",
  unemployment: "sg_singstat_search",
  trade: "sg_singstat_search",
  population: "sg_onemap_population",
  demographic: "sg_onemap_population",
  "age group": "sg_onemap_population",
  income: "sg_onemap_population",
  geocode: "sg_onemap_geocode",
  "postal code": "sg_onemap_geocode",
  address: "sg_onemap_geocode",
  "where is": "sg_onemap_geocode",
  directions: "sg_onemap_route",
  route: "sg_onemap_route",
  "how to get": "sg_onemap_route",
  property: "sg_ura_property_transactions",
  resale: "sg_ura_property_transactions",
  rental: "sg_ura_property_transactions",
  condo: "sg_ura_property_transactions",
  condominium: "sg_ura_property_transactions",
  zoning: "sg_ura_planning_area",
  "plot ratio": "sg_ura_planning_area",
  "master plan": "sg_ura_planning_area",
  hdb: "sg_hdb_resale_prices",
  "flat prices": "sg_hdb_resale_prices",
  "resale prices": "sg_hdb_resale_prices",
  "rental prices": "sg_hdb_rental_prices",
  "bus arrival": "sg_lta_bus_arrivals",
  "train alert": "sg_lta_train_alerts",
  "traffic incident": "sg_lta_traffic_incidents",
  forecast: "sg_nea_forecast_2hr",
  weather: "sg_nea_forecast_2hr",
  rainfall: "sg_nea_rainfall",
  "air quality": "sg_nea_air_quality",
  pm25: "sg_nea_air_quality",
  psi: "sg_nea_air_quality",
  salesperson: "sg_cea_salespersons",
  "estate agent": "sg_cea_salespersons",
  cea: "sg_cea_salespersons",
  "licensed builder": "sg_bca_licensed_builders",
  "registered contractor": "sg_bca_registered_contractors",
  "builder class": "sg_bca_licensed_builders",
  workhead: "sg_bca_registered_contractors",
  bca: "sg_bca_registered_contractors",
  acra: "sg_acra_entities",
  uen: "sg_acra_entities",
  "company registration": "sg_acra_entities",
  "corporate entity": "sg_acra_entities",
  hawker: "sg_datagov_search",
  school: "sg_datagov_search",
  park: "sg_datagov_search",
};

export const resolveAlias = (term: string): string | null => {
  const lower = term.toLowerCase();

  const exact = ALIAS_MAP[lower];
  if (exact !== undefined) return exact;

  for (const [alias, tool] of Object.entries(ALIAS_MAP)) {
    if (lower.includes(alias)) return tool;
  }

  return null;
};
