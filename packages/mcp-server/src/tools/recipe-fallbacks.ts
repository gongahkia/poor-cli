// Side-effect-free recipe -> fallback tools lookup. Imported by both
// legacy query-tool.ts (for unsupported-response direct-tool hints) and the
// catalog-parity test (which validates this table stays aligned with the
// catalog's fallbackTools fields). Keeping this data here avoids the
// circular import chain query-tool -> catalog -> tool-set -> query-tool.
//
// Keys are slugified recipe ids that exist in RECIPE_CATALOG. When a recipe
// id does not match a keyword-hint name, the keyword hint falls through to
// the empty fallbacks list and the unsupported-response markdown still shows
// the nearest recipe prompt without a misleading direct-tool list.
export const RECIPE_FALLBACK_TOOLS: Readonly<Record<string, readonly string[]>> = {
  pulse_overview: ["swee_pulse_mobility", "swee_pulse_weather"],
  shield_recent_audit: ["swee_shield_scan_tools", "swee_shield_approval_list", "swee_shield_policy_simulate"],
  splunk_investigation_pack: ["swee_shield_policy_simulate", "swee_shield_audit_lookup", "swee_shield_approval_list"],
};
