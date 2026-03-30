#!/usr/bin/env node
import { execFileSync } from "node:child_process";
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

const output = execFileSync("node", ["./scripts/generate-openapi.mjs"], {
  cwd: root,
  encoding: "utf8",
  stdio: ["ignore", "pipe", "inherit"],
});

const spec = JSON.parse(output);
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
  "/api/v1/sg_boa_architects",
  "/api/v1/sg_boa_architecture_firms",
  "/api/v1/sg_hsa_licensed_pharmacies",
  "/api/v1/sg_hsa_health_product_licensees",
  "/api/v1/sg_hlb_hotels",
]) {
  if (spec.paths[pathKey]?.post === undefined) {
    throw new Error(`Generated OpenAPI is missing required diligence endpoint ${pathKey}.`);
  }
}

const dossierProperties = spec.paths["/api/v1/sg_business_dossier"]?.post?.requestBody?.content?.["application/json"]?.schema?.properties;
if (dossierProperties === undefined) {
  throw new Error("Generated OpenAPI is missing the sg_business_dossier request schema.");
}

for (const key of ["modules", "sectorHints"]) {
  if (dossierProperties[key] === undefined) {
    throw new Error(`Generated OpenAPI is missing sg_business_dossier.${key}.`);
  }
}

process.stdout.write("openapi check passed\n");
