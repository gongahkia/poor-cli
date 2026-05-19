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
  business_due_diligence: ["sg_business_dossier", "sg_acra_entities", "sg_bca_licensed_builders"],
  architecture_firm_diligence: ["sg_business_dossier", "sg_boa_architecture_firms", "sg_boa_architects"],
  healthcare_supplier_diligence: ["sg_business_dossier", "sg_hsa_health_product_licensees", "sg_hsa_licensed_pharmacies"],
  hotel_operator_lookup: ["sg_business_dossier", "sg_hlb_hotels"],
};
