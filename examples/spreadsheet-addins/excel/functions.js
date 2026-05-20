/* global CustomFunctions */

const DUDE_DEFAULT_GATEWAY_URL = "http://localhost:3000";

/**
 * Runs a Dude CDD orchestrator lookup and returns the raw dossier JSON envelope.
 * @customfunction
 * @param {string} identifier Company name or UEN.
 * @param {string} [gatewayUrl] Dude REST gateway URL.
 * @param {string} [token] Optional short-lived Dude bearer token.
 * @returns {Promise<string>} JSON string for the dossier result.
 */
async function DUDE_DOSSIER(identifier, gatewayUrl, token) {
  const dossier = await dudeFetchDossier(identifier, gatewayUrl, token);
  return JSON.stringify(dossier);
}

/**
 * Runs a Dude CDD orchestrator lookup and returns a two-column summary table.
 * @customfunction
 * @param {string} identifier Company name or UEN.
 * @param {string} [gatewayUrl] Dude REST gateway URL.
 * @param {string} [token] Optional short-lived Dude bearer token.
 * @returns {Promise<string[][]>} Summary rows.
 */
async function DUDE_DOSSIER_SUMMARY(identifier, gatewayUrl, token) {
  const dossier = await dudeFetchDossier(identifier, gatewayUrl, token);
  const rows = [["Label", "Value"]];
  const summary = Array.isArray(dossier.summary) ? dossier.summary : [];
  for (const item of summary) {
    rows.push([String(item.label || ""), String(item.value ?? "")]);
  }
  return rows;
}

/**
 * Runs a Dude CDD orchestrator lookup and returns freshness/provenance rows.
 * @customfunction
 * @param {string} identifier Company name or UEN.
 * @param {string} [gatewayUrl] Dude REST gateway URL.
 * @param {string} [token] Optional short-lived Dude bearer token.
 * @returns {Promise<string[][]>} Freshness rows.
 */
async function DUDE_DOSSIER_FRESHNESS(identifier, gatewayUrl, token) {
  const dossier = await dudeFetchDossier(identifier, gatewayUrl, token);
  const provenance = Array.isArray(dossier.provenance) ? dossier.provenance : [];
  const freshness = Array.isArray(dossier.freshness) ? dossier.freshness : [];
  const bySource = Object.fromEntries(provenance.map((item) => [item.source, item]));

  const rows = [["Source", "Observed at", "Upstream timestamp", "Records"]];
  for (const item of freshness) {
    const source = String(item.source || "");
    rows.push([
      source,
      String(item.observedAt || ""),
      String(item.upstreamTimestamp || ""),
      String(bySource[source]?.recordCount ?? ""),
    ]);
  }
  return rows;
}

async function dudeFetchDossier(identifier, gatewayUrl, token) {
  const value = String(identifier || "").trim();
  if (value === "") {
    throw new Error("identifier is required");
  }

  const payload = dudeLooksLikeUen(value)
    ? { uen: value.toUpperCase() }
    : { entityName: value };
  const headers = new Headers({ "Content-Type": "application/json" });
  if (token !== undefined && String(token).trim() !== "") {
    headers.set("Authorization", `Bearer ${String(token).trim()}`);
  }

  const response = await fetch(
    `${String(gatewayUrl || DUDE_DEFAULT_GATEWAY_URL).replace(/\/+$/, "")}/api/v1/dude/cdd-orchestrator`,
    {
      body: JSON.stringify(payload),
      headers,
      method: "POST",
    },
  );
  const bodyText = await response.text();
  const parsed = bodyText ? JSON.parse(bodyText) : {};
  if (!response.ok) {
    throw new Error(parsed?.error?.message || parsed?.message || `Dude gateway returned ${response.status}`);
  }

  return parsed?.data?.dossier || parsed?.dossier || parsed?.data?.record || parsed;
}

function dudeLooksLikeUen(value) {
  return /^[0-9A-Z]{9,10}$/i.test(String(value).replace(/\s+/g, ""));
}

if (typeof CustomFunctions !== "undefined") {
  CustomFunctions.associate("DUDE.DOSSIER", DUDE_DOSSIER);
  CustomFunctions.associate("DUDE.DOSSIER.SUMMARY", DUDE_DOSSIER_SUMMARY);
  CustomFunctions.associate("DUDE.DOSSIER.FRESHNESS", DUDE_DOSSIER_FRESHNESS);
}
