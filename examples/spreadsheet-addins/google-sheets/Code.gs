const SWEE_DEFAULT_GATEWAY_URL = "http://localhost:3000";

/**
 * Returns the raw Swee Pulse snapshot JSON envelope.
 *
 * @param {string=} focus Optional focus: all, mobility, or weather.
 * @param {string=} area Optional Singapore area filter.
 * @param {string=} gatewayUrl Swee SG REST gateway URL.
 * @param {string=} token Optional short-lived bearer token.
 * @return {string} JSON string for the Pulse snapshot.
 * @customfunction
 */
function SWEE_PULSE_SNAPSHOT(focus, area, gatewayUrl, token) {
  const snapshot = sweeFetchPulse_(focus, area, gatewayUrl, token);
  return JSON.stringify(snapshot);
}

/**
 * Returns Swee Pulse signal rows.
 *
 * @param {string=} focus Optional focus: all, mobility, or weather.
 * @param {string=} area Optional Singapore area filter.
 * @param {string=} gatewayUrl Swee SG REST gateway URL.
 * @param {string=} token Optional short-lived bearer token.
 * @return {Array<Array<string>>} Signal rows.
 * @customfunction
 */
function SWEE_PULSE_SIGNALS(focus, area, gatewayUrl, token) {
  const snapshot = sweeFetchPulse_(focus, area, gatewayUrl, token);
  const rows = [["Severity", "Category", "Title", "Summary", "Source", "Observed at"]];
  const signals = Array.isArray(snapshot.signals) ? snapshot.signals : [];
  signals.forEach((signal) => {
    const provenance = Array.isArray(signal.provenance) ? signal.provenance[0] : {};
    rows.push([
      String(signal.severity || ""),
      String(signal.category || ""),
      String(signal.title || ""),
      String(signal.summary || ""),
      String(provenance?.source || signal.source || ""),
      String(signal.freshness?.observedAt || provenance?.observedAt || ""),
    ]);
  });
  return rows;
}

/**
 * Returns Swee Pulse source-health rows.
 *
 * @param {string=} focus Optional focus: all, mobility, or weather.
 * @param {string=} area Optional Singapore area filter.
 * @param {string=} gatewayUrl Swee SG REST gateway URL.
 * @param {string=} token Optional short-lived bearer token.
 * @return {Array<Array<string>>} Source-health rows.
 * @customfunction
 */
function SWEE_PULSE_SOURCES(focus, area, gatewayUrl, token) {
  const snapshot = sweeFetchPulse_(focus, area, gatewayUrl, token);
  const rows = [["Source", "Status", "Rows", "Observed at", "Message"]];
  const sourceHealth = Array.isArray(snapshot.sourceHealth) ? snapshot.sourceHealth : [];
  sourceHealth.forEach((source) => {
    rows.push([
      String(source.source || ""),
      String(source.status || ""),
      String(source.recordCount ?? source.rows ?? ""),
      String(source.observedAt || ""),
      String(source.message || ""),
    ]);
  });
  return rows;
}

function sweeFetchPulse_(focus, area, gatewayUrl, token) {
  const baseUrl = String(gatewayUrl || SWEE_DEFAULT_GATEWAY_URL).replace(/\/+$/, "");
  const query = [];
  if (String(focus || "").trim() !== "") {
    query.push(`focus=${encodeURIComponent(String(focus).trim())}`);
  }
  if (String(area || "").trim() !== "") {
    query.push(`area=${encodeURIComponent(String(area).trim())}`);
  }

  const url = `${baseUrl}/api/v1/pulse/snapshot${query.length === 0 ? "" : `?${query.join("&")}`}`;
  const headers = {};
  if (token !== undefined && String(token).trim() !== "") {
    headers.Authorization = `Bearer ${String(token).trim()}`;
  }

  const response = UrlFetchApp.fetch(url, {
    method: "get",
    headers,
    muteHttpExceptions: true,
  });

  const body = response.getContentText();
  const parsed = body ? JSON.parse(body) : {};
  const status = response.getResponseCode();
  if (status < 200 || status >= 300) {
    throw new Error(parsed?.error?.message || parsed?.message || `Swee SG gateway returned ${status}`);
  }

  return parsed?.data?.snapshot || parsed?.snapshot || parsed?.data?.record || parsed;
}
