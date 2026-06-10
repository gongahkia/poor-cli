#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const root = resolve(import.meta.dirname, "..");

const loadToolDefinitions = async () => {
  try {
    const moduleUrl = pathToFileURL(resolve(root, "packages/mcp-server/dist/tools/tool-set.js")).href;
    return (await import(moduleUrl)).ALL_TOOL_DEFINITIONS;
  } catch (error) {
    throw new Error(
      `Unable to load built tool definitions. Run "npm run build" first. ${
        error instanceof Error ? error.message : String(error)
      }`,
    );
  }
};

const generateOpenApiSpec = async () => {
  const moduleUrl = pathToFileURL(resolve(root, "scripts/generate-openapi.mjs")).href;
  const module = await import(moduleUrl);
  if (typeof module.generateOpenApiSpec !== "function") {
    throw new Error("OpenAPI generator did not export generateOpenApiSpec().");
  }
  return module.generateOpenApiSpec();
};

const spec = await generateOpenApiSpec();
const toolDefinitions = await loadToolDefinitions();
const publishedArtifact = JSON.parse(
  readFileSync(resolve(root, "packages/mcp-server/openapi.json"), "utf8"),
);

if (JSON.stringify(spec) !== JSON.stringify(publishedArtifact)) {
  throw new Error("Generated OpenAPI does not match packages/mcp-server/openapi.json.");
}

for (const definition of toolDefinitions) {
  const pathKey = `/api/v1/${definition.name}`;
  if (spec.paths[pathKey]?.post === undefined) {
    throw new Error(`Generated OpenAPI is missing tool path ${pathKey}.`);
  }
}

for (const pathKey of [
  "/api/v1/swee_pulse_snapshot",
  "/api/v1/swee_pulse_weather",
  "/api/v1/swee_pulse_mobility",
  "/api/v1/swee_pulse_explain",
  "/api/v1/swee_shield_audit_lookup",
  "/api/v1/swee_shield_scan_tools",
  "/api/v1/swee_shield_approval_list",
  "/api/v1/swee_shield_approval_decide",
  "/api/v1/swee_shield_policy_simulate",
  "/api/v1/swee_shield_splunk_investigation_pack",
  "/api/v1/sg_nea_forecast_2hr",
  "/api/v1/sg_nea_air_quality",
  "/api/v1/sg_nea_rainfall",
  "/api/v1/sg_lta_traffic_incidents",
  "/api/v1/sg_lta_train_alerts",
]) {
  if (spec.paths[pathKey]?.post === undefined) {
    throw new Error(`Generated OpenAPI is missing required Swee SG endpoint ${pathKey}.`);
  }
}

for (const removedPath of [
  "/api/v1/sg_business_dossier",
  "/api/v1/sg_cdd_report",
  "/api/v1/sg_query",
  "/api/v1/sg_resolve_counterparty",
]) {
  if (spec.paths[removedPath] !== undefined) {
    throw new Error(`Generated OpenAPI still exposes removed CDD endpoint ${removedPath}.`);
  }
}

const pulseProperties = spec.paths["/api/v1/swee_pulse_snapshot"]?.post?.requestBody?.content?.["application/json"]?.schema?.properties;
if (pulseProperties === undefined) {
  throw new Error("Generated OpenAPI is missing the swee_pulse_snapshot request schema.");
}

for (const key of ["area", "region", "stationId", "focus"]) {
  if (pulseProperties[key] === undefined) {
    throw new Error(`Generated OpenAPI is missing swee_pulse_snapshot.${key}.`);
  }
}

process.stdout.write("openapi check passed\n");
