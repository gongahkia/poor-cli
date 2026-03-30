#!/usr/bin/env node
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
