const DUDE_DEFAULT_GATEWAY_URL = "http://localhost:3000";

/**
 * Runs a Dude CDD orchestrator lookup and returns the raw dossier JSON envelope.
 *
 * @param {string} identifier Company name or UEN.
 * @param {string=} gatewayUrl Dude REST gateway URL.
 * @param {string=} token Optional short-lived Dude bearer token.
 * @return {string} JSON string for the dossier result.
 * @customfunction
 */
function DUDE_DOSSIER(identifier, gatewayUrl, token) {
  const dossier = dudeFetchDossier_(identifier, gatewayUrl, token);
  return JSON.stringify(dossier);
}

/**
 * Runs a Dude CDD orchestrator lookup and returns a two-column summary table.
 *
 * @param {string} identifier Company name or UEN.
 * @param {string=} gatewayUrl Dude REST gateway URL.
 * @param {string=} token Optional short-lived Dude bearer token.
 * @return {Array<Array<string>>} Summary rows.
 * @customfunction
 */
function DUDE_DOSSIER_SUMMARY(identifier, gatewayUrl, token) {
  const dossier = dudeFetchDossier_(identifier, gatewayUrl, token);
  const rows = [["Label", "Value"]];
  const summary = Array.isArray(dossier.summary) ? dossier.summary : [];
  summary.forEach((item) => {
    rows.push([String(item.label || ""), String(item.value ?? "")]);
  });
  return rows;
}

/**
 * Runs a Dude CDD orchestrator lookup and returns freshness/provenance rows.
 *
 * @param {string} identifier Company name or UEN.
 * @param {string=} gatewayUrl Dude REST gateway URL.
 * @param {string=} token Optional short-lived Dude bearer token.
 * @return {Array<Array<string>>} Freshness rows.
 * @customfunction
 */
function DUDE_DOSSIER_FRESHNESS(identifier, gatewayUrl, token) {
  const dossier = dudeFetchDossier_(identifier, gatewayUrl, token);
  const provenance = Array.isArray(dossier.provenance) ? dossier.provenance : [];
  const freshness = Array.isArray(dossier.freshness) ? dossier.freshness : [];
  const bySource = {};
  provenance.forEach((item) => {
    bySource[item.source] = item;
  });

  const rows = [["Source", "Observed at", "Upstream timestamp", "Records"]];
  freshness.forEach((item) => {
    const source = String(item.source || "");
    rows.push([
      source,
      String(item.observedAt || ""),
      String(item.upstreamTimestamp || ""),
      String(bySource[source]?.recordCount ?? ""),
    ]);
  });
  return rows;
}

function dudeFetchDossier_(identifier, gatewayUrl, token) {
  const value = String(identifier || "").trim();
  if (value === "") {
    throw new Error("identifier is required");
  }

  const url = `${String(gatewayUrl || DUDE_DEFAULT_GATEWAY_URL).replace(/\/+$/, "")}/api/v1/dude/cdd-orchestrator`;
  const payload = dudeLooksLikeUen_(value)
    ? { uen: value.toUpperCase() }
    : { entityName: value };
  const headers = { "Content-Type": "application/json" };
  if (token !== undefined && String(token).trim() !== "") {
    headers.Authorization = `Bearer ${String(token).trim()}`;
  }

  const response = UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    headers,
    muteHttpExceptions: true,
    payload: JSON.stringify(payload),
  });

  const body = response.getContentText();
  const parsed = body ? JSON.parse(body) : {};
  const status = response.getResponseCode();
  if (status < 200 || status >= 300) {
    throw new Error(parsed?.error?.message || parsed?.message || `Dude gateway returned ${status}`);
  }

  return parsed?.data?.dossier || parsed?.dossier || parsed?.data?.record || parsed;
}

function dudeLooksLikeUen_(value) {
  return /^[0-9A-Z]{9,10}$/i.test(String(value).replace(/\s+/g, ""));
}
