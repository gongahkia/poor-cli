/* global CustomFunctions */

const SWEE_DEFAULT_GATEWAY_URL = "http://localhost:3000";

/**
 * Returns the raw Swee Pulse snapshot JSON envelope.
 * @customfunction
 * @param {string} [focus] Optional focus: all, mobility, or weather.
 * @param {string} [area] Optional Singapore area filter.
 * @param {string} [gatewayUrl] Swee SG REST gateway URL.
 * @param {string} [token] Optional short-lived bearer token.
 * @returns {Promise<string>} JSON string for the Pulse snapshot.
 */
async function SWEE_PULSE_SNAPSHOT(focus, area, gatewayUrl, token) {
  const snapshot = await sweeFetchPulse(focus, area, gatewayUrl, token);
  return JSON.stringify(snapshot);
}

/**
 * Returns Swee Pulse signal rows.
 * @customfunction
 * @param {string} [focus] Optional focus: all, mobility, or weather.
 * @param {string} [area] Optional Singapore area filter.
 * @param {string} [gatewayUrl] Swee SG REST gateway URL.
 * @param {string} [token] Optional short-lived bearer token.
 * @returns {Promise<string[][]>} Signal rows.
 */
async function SWEE_PULSE_SIGNALS(focus, area, gatewayUrl, token) {
  const snapshot = await sweeFetchPulse(focus, area, gatewayUrl, token);
  const rows = [["Severity", "Category", "Title", "Summary", "Source", "Observed at"]];
  const signals = Array.isArray(snapshot.signals) ? snapshot.signals : [];
  for (const signal of signals) {
    const provenance = Array.isArray(signal.provenance) ? signal.provenance[0] : {};
    rows.push([
      String(signal.severity || ""),
      String(signal.category || ""),
      String(signal.title || ""),
      String(signal.summary || ""),
      String(provenance?.source || signal.source || ""),
      String(signal.freshness?.observedAt || provenance?.observedAt || ""),
    ]);
  }
  return rows;
}

/**
 * Returns Swee Pulse source-health rows.
 * @customfunction
 * @param {string} [focus] Optional focus: all, mobility, or weather.
 * @param {string} [area] Optional Singapore area filter.
 * @param {string} [gatewayUrl] Swee SG REST gateway URL.
 * @param {string} [token] Optional short-lived bearer token.
 * @returns {Promise<string[][]>} Source-health rows.
 */
async function SWEE_PULSE_SOURCES(focus, area, gatewayUrl, token) {
  const snapshot = await sweeFetchPulse(focus, area, gatewayUrl, token);
  const rows = [["Source", "Status", "Rows", "Observed at", "Message"]];
  const sourceHealth = Array.isArray(snapshot.sourceHealth) ? snapshot.sourceHealth : [];
  for (const source of sourceHealth) {
    rows.push([
      String(source.source || ""),
      String(source.status || ""),
      String(source.recordCount ?? source.rows ?? ""),
      String(source.observedAt || ""),
      String(source.message || ""),
    ]);
  }
  return rows;
}

async function sweeFetchPulse(focus, area, gatewayUrl, token) {
  const baseUrl = String(gatewayUrl || SWEE_DEFAULT_GATEWAY_URL).replace(/\/+$/, "");
  const url = new URL(`${baseUrl}/api/v1/pulse/snapshot`);
  if (String(focus || "").trim() !== "") {
    url.searchParams.set("focus", String(focus).trim());
  }
  if (String(area || "").trim() !== "") {
    url.searchParams.set("area", String(area).trim());
  }

  const headers = new Headers();
  if (token !== undefined && String(token).trim() !== "") {
    headers.set("Authorization", `Bearer ${String(token).trim()}`);
  }

  const response = await fetch(url, { headers, method: "GET" });
  const bodyText = await response.text();
  const parsed = bodyText ? JSON.parse(bodyText) : {};
  if (!response.ok) {
    throw new Error(parsed?.error?.message || parsed?.message || `Swee SG gateway returned ${response.status}`);
  }

  return parsed?.data?.snapshot || parsed?.snapshot || parsed?.data?.record || parsed;
}

if (typeof CustomFunctions !== "undefined") {
  CustomFunctions.associate("SWEE.PULSE.SNAPSHOT", SWEE_PULSE_SNAPSHOT);
  CustomFunctions.associate("SWEE.PULSE.SIGNALS", SWEE_PULSE_SIGNALS);
  CustomFunctions.associate("SWEE.PULSE.SOURCES", SWEE_PULSE_SOURCES);
}
