#!/usr/bin/env node
// generates openapi.yaml from the tool definitions
// usage: node scripts/generate-openapi.mjs > openapi.yaml
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const pkgJson = JSON.parse(readFileSync(resolve("packages/mcp-server/package.json"), "utf8"));

const spec = {
  openapi: "3.1.0",
  info: {
    title: "sg-apis-mcp REST Gateway",
    version: pkgJson.version,
    description: "REST interface for Singapore public data tools. Each tool is exposed as a POST endpoint.",
  },
  servers: [{ url: "http://localhost:3000", description: "Local REST gateway" }],
  paths: {
    "/api/v1/tools": {
      get: {
        summary: "List all available tools",
        responses: { 200: { description: "Array of tool names and descriptions", content: { "application/json": { schema: { type: "array", items: { type: "object", properties: { name: { type: "string" }, description: { type: "string" } } } } } } } },
      },
    },
    "/api/v1/health": {
      get: {
        summary: "Health check",
        responses: { 200: { description: "Gateway health status", content: { "application/json": { schema: { type: "object", properties: { status: { type: "string" }, tools: { type: "integer" } } } } } } },
      },
    },
  },
};

// add paths for known tool families
const toolFamilies = [
  { path: "sg_query", summary: "Natural-language query interface", body: { query: "string", format: "string?", mode: "string?" } },
  { path: "sg_nea_forecast_2hr", summary: "2-hour weather forecast", body: { area: "string?", date: "string?" } },
  { path: "sg_nea_air_quality", summary: "Air quality readings", body: { region: "string?", date: "string?" } },
  { path: "sg_hdb_resale_prices", summary: "HDB resale prices", body: { town: "string?", flatType: "string?", limit: "integer?" } },
  { path: "sg_property_brief", summary: "Property brief", body: { planningArea: "string?", postalCode: "string?", format: "string?" } },
  { path: "sg_business_dossier", summary: "Business dossier", body: { entityName: "string?", uen: "string?", format: "string?" } },
  { path: "sg_macro_brief", summary: "Macro brief", body: { currency: "string?", format: "string?" } },
  { path: "sg_transport_brief", summary: "Transport brief", body: { busStopCode: "string?", format: "string?" } },
  { path: "sg_environment_brief", summary: "Environment brief", body: { area: "string?", region: "string?", format: "string?" } },
  { path: "sg_pa_community_outlets", summary: "PA community outlets", body: { name: "string?", type: "string?", postalCode: "string?", lat: "string?", lng: "string?" } },
  { path: "sg_pa_resident_network_centres", summary: "PA residents' network centres", body: { name: "string?", postalCode: "string?", lat: "string?", lng: "string?" } },
  { path: "sg_sportsg_facilities", summary: "SportSG facilities", body: { name: "string?", facilityType: "string?", postalCode: "string?", lat: "string?", lng: "string?" } },
  { path: "sg_ecda_childcare_centres", summary: "ECDA childcare centres", body: { name: "string?", centreType: "string?", operatorType: "string?", hasVacancy: "string?", postalCode: "string?", lat: "string?", lng: "string?" } },
  { path: "sg_gebiz_tenders", summary: "GeBIZ tenders", body: { agency: "string?", category: "string?" } },
  { path: "sg_hawker_centres", summary: "Hawker centres", body: { name: "string?" } },
  { path: "sg_moe_schools", summary: "MOE schools", body: { level: "string?", zone: "string?" } },
  { path: "sg_moh_facilities", summary: "Healthcare facilities", body: { type: "string?", name: "string?" } },
];

for (const tool of toolFamilies) {
  const properties = {};
  for (const [key, type] of Object.entries(tool.body)) {
    const isOptional = type.endsWith("?");
    const baseType = type.replace("?", "");
    properties[key] = { type: baseType === "integer" ? "integer" : "string" };
  }
  spec.paths[`/api/v1/${tool.path}`] = {
    post: {
      summary: tool.summary,
      requestBody: {
        content: { "application/json": { schema: { type: "object", properties } } },
      },
      responses: {
        200: { description: "Tool result", content: { "application/json": { schema: { type: "object" } } } },
        400: { description: "Tool error" },
        500: { description: "Server error" },
      },
    },
  };
}

// output as YAML-like JSON (consumers can convert)
console.log(JSON.stringify(spec, null, 2));
