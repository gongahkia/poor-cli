import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { execFileSync, spawn } from "node:child_process";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const root = resolve(import.meta.dirname, "..");
const tempDir = mkdtempSync(join(tmpdir(), "sg-apis-smoke-"));
const tarballs = [];
let mockServer = null;
const RUNTIME_LEAK_PATTERNS = ["/__tests__/", "/fixtures/", "/mock-server/"];

const EXPECTED_TOOL_NAMES = [
  "sg_singstat_search",
  "sg_singstat_table",
  "sg_singstat_timeseries",
  "sg_singstat_compare",
  "sg_singstat_browse",
  "sg_mas_exchange_rates",
  "sg_mas_interest_rates",
  "sg_mas_financial_stats",
  "sg_onemap_geocode",
  "sg_onemap_reverse_geocode",
  "sg_onemap_route",
  "sg_onemap_population",
  "sg_onemap_convert_coords",
  "sg_ura_property_transactions",
  "sg_ura_planning_area",
  "sg_ura_dev_charges",
  "sg_datagov_search",
  "sg_datagov_get",
  "sg_datagov_resources",
  "sg_datagov_rows",
  "sg_datagov_browse",
  "sg_lta_bus_arrivals",
  "sg_lta_train_alerts",
  "sg_lta_traffic_incidents",
  "sg_nea_forecast_2hr",
  "sg_nea_air_quality",
  "sg_nea_rainfall",
  "sg_hdb_resale_prices",
  "sg_hdb_rental_prices",
  "sg_cea_salespersons",
  "sg_bca_licensed_builders",
  "sg_bca_registered_contractors",
  "sg_boa_architects",
  "sg_boa_architecture_firms",
  "sg_acra_entities",
  "sg_pa_community_outlets",
  "sg_pa_resident_network_centres",
  "sg_sportsg_facilities",
  "sg_ecda_childcare_centres",
  "sg_msf_family_services",
  "sg_msf_student_care_services",
  "sg_msf_social_service_offices",
  "sg_gebiz_tenders",
  "sg_hawker_centres",
  "sg_moe_schools",
  "sg_moh_facilities",
  "sg_hsa_licensed_pharmacies",
  "sg_hsa_health_product_licensees",
  "sg_sfa_establishments",
  "sg_nparks_parks",
  "sg_pub_water_levels",
  "sg_mom_labour_stats",
  "sg_stb_visitor_stats",
  "sg_hlb_hotels",
  "sg_business_dossier",
  "sg_property_brief",
  "sg_macro_brief",
  "sg_transport_brief",
  "sg_environment_brief",
  "sg_health_check",
  "sg_key_set",
  "sg_key_list",
  "sg_key_delete",
  "sg_cache_stats",
  "sg_cache_clear",
  "sg_config_get",
  "sg_config_set",
  "sg_query",
];

const EXPECTED_RESOURCE_URIS = ["sg://apis", "sg://tools", "sg://workflows", "sg://recipes"];

const toValueMap = (items) => {
  if (!Array.isArray(items)) {
    return new Map();
  }
  return new Map(
    items
      .filter((item) => item !== null && typeof item === "object" && "label" in item)
      .map((item) => [item.label, item.value]),
  );
};

const run = (args, cwd = root) => {
  return execFileSync("npm", args, {
    cwd,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "inherit"],
  }).trim();
};

const startMockServer = async () => {
  return new Promise((resolveMock, reject) => {
    const child = spawn("npm", ["run", "mock-server"], {
      cwd: root,
      env: { ...process.env, MOCK_PORT: "0" },
      stdio: ["ignore", "ignore", "pipe"],
    });

    let stderr = "";
    const timeout = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error(`Timed out waiting for mock API server startup.\n${stderr}`));
    }, 10000);

    child.stderr.on("data", (chunk) => {
      stderr += String(chunk);
      const match = stderr.match(/Mock API server running on (http:\/\/localhost:\d+)/);
      if (match !== null) {
        clearTimeout(timeout);
        resolveMock({ child, url: match[1] });
      }
    });

    child.on("exit", (code) => {
      clearTimeout(timeout);
      reject(new Error(`Mock API server exited before startup with code ${String(code)}.\n${stderr}`));
    });
  });
};

try {
  const assertRuntimeOnlyPackage = (workspace, packInfo) => {
    const leaked = packInfo.files
      .map((file) => file.path)
      .filter((path) => RUNTIME_LEAK_PATTERNS.some((pattern) => path.includes(pattern)));
    if (leaked.length > 0) {
      throw new Error(`${workspace} package still includes non-runtime files: ${leaked.join(", ")}`);
    }
  };

  const packWorkspace = (workspace) => {
    const output = run(["pack", "--json", "--workspace", workspace]);
    const [packInfo] = JSON.parse(output);
    assertRuntimeOnlyPackage(workspace, packInfo);
    const { filename } = packInfo;
    const tarballPath = join(root, filename);
    tarballs.push(tarballPath);
    return tarballPath;
  };

  const sharedTarball = packWorkspace("packages/shared");
  const serverTarball = packWorkspace("packages/mcp-server");

  writeFileSync(
    join(tempDir, "package.json"),
    JSON.stringify(
      {
        name: "sg-apis-smoke",
        private: true,
        type: "module",
      },
      null,
      2,
    ),
  );

  run(["install", "--no-package-lock", sharedTarball], tempDir);
  run(["install", "--no-package-lock", serverTarball], tempDir);

  JSON.parse(readFileSync(join(tempDir, "node_modules", "sg-apis-mcp", "package.json"), "utf8"));
  JSON.parse(readFileSync(join(tempDir, "node_modules", "@sg-apis", "shared", "package.json"), "utf8"));

  mockServer = await startMockServer();

  const transport = new StdioClientTransport({
    command: join(tempDir, "node_modules", ".bin", "sg-apis-mcp"),
    cwd: tempDir,
    env: {
      ...process.env,
      HOME: tempDir,
      SG_APIS_LOG_LEVEL: "error",
      MOCK_API_BASE_URL: mockServer.url,
      SG_API_ONEMAP_EMAIL: "test-onemap@example.com",
      SG_API_ONEMAP_PASSWORD: "test-onemap-password",
      SG_API_URA_KEY: "test-ura-key",
      SG_API_LTA_KEY: "test-lta-key",
    },
    stderr: "pipe",
  });
  const stderrChunks = [];
  transport.stderr?.on("data", (chunk) => {
    stderrChunks.push(String(chunk));
  });

  const client = new Client(
    {
      name: "sg-apis-smoke",
      version: "0.1.0",
    },
    { capabilities: {} },
  );

  const formatServerLogs = () => {
    const logs = stderrChunks.join("").trim();
    return logs.length > 0 ? `\nServer stderr:\n${logs}` : "";
  };

  try {
    await client.connect(transport);

    if (client.getServerVersion()?.name !== "sg-apis-mcp") {
      throw new Error(`Unexpected MCP server name: ${JSON.stringify(client.getServerVersion())}${formatServerLogs()}`);
    }

    const toolsResult = await client.listTools();
    const resourcesResult = await client.listResources();

    const toolNames = new Set((toolsResult.tools ?? []).map((tool) => tool.name));
    for (const toolName of EXPECTED_TOOL_NAMES) {
      if (!toolNames.has(toolName)) {
        throw new Error(`Packaged MCP server is missing tool: ${toolName}${formatServerLogs()}`);
      }
    }

    const resourceUris = new Set((resourcesResult.resources ?? []).map((resource) => resource.uri));
    for (const uri of EXPECTED_RESOURCE_URIS) {
      if (!resourceUris.has(uri)) {
        throw new Error(`Packaged MCP server is missing resource: ${uri}${formatServerLogs()}`);
      }
    }

    for (const uri of EXPECTED_RESOURCE_URIS) {
      const resource = await client.readResource({ uri });
      const textContent = resource.contents.find((content) => "text" in content && typeof content.text === "string");
      if (textContent === undefined) {
        throw new Error(`Packaged MCP resource did not return text content: ${uri}${formatServerLogs()}`);
      }

      let parsed;
      try {
        parsed = JSON.parse(textContent.text);
      } catch (error) {
        throw new Error(
          `Packaged MCP resource returned invalid JSON for ${uri}: ${error instanceof Error ? error.message : String(error)}${formatServerLogs()}`,
        );
      }

      if (!Array.isArray(parsed) || parsed.length === 0) {
        throw new Error(`Packaged MCP resource returned empty catalog payload for ${uri}${formatServerLogs()}`);
      }
    }

    const toolResult = await client.callTool({
      name: "sg_config_get",
      arguments: {},
    });
    const toolText = "content" in toolResult
      ? toolResult.content.find((item) => item.type === "text" && typeof item.text === "string")?.text
      : undefined;
    if (toolText === undefined || !toolText.includes("\"cache\"")) {
      throw new Error(`Packaged MCP tool invocation failed to return config payload${formatServerLogs()}`);
    }

    const datasetMetadataResult = await client.callTool({
      name: "sg_datagov_get",
      arguments: {
        datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
        format: "json",
      },
    });
    const datasetMetadataText = "content" in datasetMetadataResult
      ? datasetMetadataResult.content.find((item) => item.type === "text" && typeof item.text === "string")?.text
      : undefined;
    if (datasetMetadataText === undefined) {
      throw new Error(`Packaged sg_datagov_get did not return text content${formatServerLogs()}`);
    }
    const datasetMetadataPayload = JSON.parse(datasetMetadataText);
    if (datasetMetadataPayload.name !== "HDB Resale Flat Prices") {
      throw new Error(`Packaged sg_datagov_get returned unexpected metadata payload${formatServerLogs()}`);
    }

    const datasetResourcesResult = await client.callTool({
      name: "sg_datagov_resources",
      arguments: {
        datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
        format: "json",
      },
    });
    const datasetResourcesText = "content" in datasetResourcesResult
      ? datasetResourcesResult.content.find((item) => item.type === "text" && typeof item.text === "string")?.text
      : undefined;
    if (datasetResourcesText === undefined) {
      throw new Error(`Packaged sg_datagov_resources did not return text content${formatServerLogs()}`);
    }
    const datasetResourcesPayload = JSON.parse(datasetResourcesText);
    if (!Array.isArray(datasetResourcesPayload.resources) || datasetResourcesPayload.resources.length === 0) {
      throw new Error(`Packaged sg_datagov_resources returned no resource metadata${formatServerLogs()}`);
    }

    const datasetRowsResult = await client.callTool({
      name: "sg_datagov_rows",
      arguments: {
        datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
        limit: 1,
        format: "json",
      },
    });
    const datasetRowsText = "content" in datasetRowsResult
      ? datasetRowsResult.content.find((item) => item.type === "text" && typeof item.text === "string")?.text
      : undefined;
    if (datasetRowsText === undefined) {
      throw new Error(`Packaged sg_datagov_rows did not return text content${formatServerLogs()}`);
    }
    const datasetRowsPayload = JSON.parse(datasetRowsText);
    if (!Array.isArray(datasetRowsPayload.records) || datasetRowsPayload.records.length === 0) {
      throw new Error(`Packaged sg_datagov_rows returned no records${formatServerLogs()}`);
    }

    const macroBriefResult = await client.callTool({
      name: "sg_macro_brief",
      arguments: {
        currency: "USD",
        format: "json",
      },
    });
    const macroBriefText = "content" in macroBriefResult
      ? macroBriefResult.content.find((item) => item.type === "text" && typeof item.text === "string")?.text
      : undefined;
    if (macroBriefText === undefined) {
      throw new Error(`Packaged sg_macro_brief did not return text content${formatServerLogs()}`);
    }
    const macroBriefPayload = JSON.parse(macroBriefText);
    if (macroBriefPayload.title !== "Macro Brief") {
      throw new Error(`Packaged sg_macro_brief returned an unexpected payload${formatServerLogs()}`);
    }
    for (const key of ["provenance", "freshness", "limits"]) {
      if (!Array.isArray(macroBriefPayload[key])) {
        throw new Error(`Packaged sg_macro_brief did not include ${key}${formatServerLogs()}`);
      }
    }
    const macroSummary = toValueMap(macroBriefPayload.summary);
    const macroEvidence = toValueMap(macroBriefPayload.evidence);
    if (macroEvidence.get("Primary SORA key") === "preliminary") {
      throw new Error(`Packaged sg_macro_brief selected a non-metric SORA field${formatServerLogs()}`);
    }
    if (macroEvidence.get("Primary banking key") === "preliminary") {
      throw new Error(`Packaged sg_macro_brief selected a non-metric banking field${formatServerLogs()}`);
    }
    if (macroSummary.get("CPI table ID") === macroSummary.get("GDP table ID")) {
      throw new Error(`Packaged sg_macro_brief reused the GDP dataset as CPI${formatServerLogs()}`);
    }

    const environmentBriefResult = await client.callTool({
      name: "sg_environment_brief",
      arguments: {
        area: "Tampines",
        region: "East",
        format: "json",
      },
    });
    const environmentBriefText = "content" in environmentBriefResult
      ? environmentBriefResult.content.find((item) => item.type === "text" && typeof item.text === "string")?.text
      : undefined;
    if (environmentBriefText === undefined) {
      throw new Error(`Packaged sg_environment_brief did not return text content${formatServerLogs()}`);
    }
    const environmentBriefPayload = JSON.parse(environmentBriefText);
    if (environmentBriefPayload.title !== "Environment Brief") {
      throw new Error(`Packaged sg_environment_brief returned an unexpected payload${formatServerLogs()}`);
    }
    if (!Array.isArray(environmentBriefPayload.provenance) || !Array.isArray(environmentBriefPayload.freshness)) {
      throw new Error(`Packaged sg_environment_brief omitted provenance or freshness${formatServerLogs()}`);
    }

    const businessDossierResult = await client.callTool({
      name: "sg_business_dossier",
      arguments: {
        entityName: "DP Architects",
        modules: ["acra", "boa", "gebiz"],
        sectorHints: ["architecture", "procurement"],
        format: "json",
      },
    });
    const businessDossierText = "content" in businessDossierResult
      ? businessDossierResult.content.find((item) => item.type === "text" && typeof item.text === "string")?.text
      : undefined;
    if (businessDossierText === undefined) {
      throw new Error(`Packaged sg_business_dossier did not return text content${formatServerLogs()}`);
    }
    const businessDossierPayload = JSON.parse(businessDossierText);
    const selectedModules = businessDossierPayload.records?.resolution?.selectedModules;
    if (
      businessDossierPayload.title !== "Business Dossier"
      || !Array.isArray(selectedModules)
      || !selectedModules.includes("boa")
      || !selectedModules.includes("gebiz")
    ) {
      throw new Error(`Packaged sg_business_dossier did not preserve explicit business modules${formatServerLogs()}`);
    }

    const hotelDirectoryResult = await client.callTool({
      name: "sg_hlb_hotels",
      arguments: {
        name: "Marina Bay Sands",
        format: "json",
      },
    });
    const hotelDirectoryText = "content" in hotelDirectoryResult
      ? hotelDirectoryResult.content.find((item) => item.type === "text" && typeof item.text === "string")?.text
      : undefined;
    if (hotelDirectoryText === undefined) {
      throw new Error(`Packaged sg_hlb_hotels did not return text content${formatServerLogs()}`);
    }
    const hotelDirectoryPayload = JSON.parse(hotelDirectoryText);
    if (!Array.isArray(hotelDirectoryPayload) || hotelDirectoryPayload[0]?.name !== "Marina Bay Sands") {
      throw new Error(`Packaged sg_hlb_hotels returned an unexpected payload${formatServerLogs()}`);
    }

    const queryPlanResult = await client.callTool({
      name: "sg_query",
      arguments: {
        query: "Macro snapshot of Singapore",
        mode: "plan",
      },
    });
    if (!("structuredContent" in queryPlanResult) || queryPlanResult.structuredContent?.status !== "planned") {
      throw new Error(`Packaged sg_query plan call did not return workflow metadata${formatServerLogs()}`);
    }

    const queryExecuteResult = await client.callTool({
      name: "sg_query",
      arguments: {
        query: "Transport status in Singapore right now",
        mode: "execute",
        format: "json",
      },
    });
    if (
      !("structuredContent" in queryExecuteResult)
      || queryExecuteResult.structuredContent?.status !== "completed"
      || queryExecuteResult.structuredContent?.workflow !== "transport_brief"
    ) {
      throw new Error(`Packaged sg_query execute call did not complete successfully${formatServerLogs()}`);
    }

    const routeRecipeResult = await client.callTool({
      name: "sg_query",
      arguments: {
        query: "Walk from 049178 to 048616",
        mode: "execute",
        format: "json",
      },
    });
    if (
      !("structuredContent" in routeRecipeResult)
      || routeRecipeResult.structuredContent?.status !== "completed"
      || routeRecipeResult.structuredContent?.workflow !== "route_plan"
    ) {
      throw new Error(`Packaged sg_query route recipe did not complete successfully${formatServerLogs()}`);
    }

    const diligenceQueryResult = await client.callTool({
      name: "sg_query",
      arguments: {
        query: "Architecture firm diligence for DP Architects",
        mode: "execute",
        format: "json",
      },
    });
    if (
      !("structuredContent" in diligenceQueryResult)
      || diligenceQueryResult.structuredContent?.status !== "completed"
      || diligenceQueryResult.structuredContent?.workflow !== "architecture_firm_diligence"
    ) {
      throw new Error(`Packaged sg_query architecture diligence did not complete successfully${formatServerLogs()}`);
    }

    const civicDirectoryResult = await client.callTool({
      name: "sg_msf_family_services",
      arguments: {
        postalCode: "560230",
        format: "json",
      },
    });
    const civicDirectoryText = "content" in civicDirectoryResult
      ? civicDirectoryResult.content.find((item) => item.type === "text" && typeof item.text === "string")?.text
      : undefined;
    if (civicDirectoryText === undefined) {
      throw new Error(`Packaged sg_msf_family_services did not return text content${formatServerLogs()}`);
    }
    const civicDirectoryPayload = JSON.parse(civicDirectoryText);
    if (!Array.isArray(civicDirectoryPayload) || civicDirectoryPayload[0]?.name !== "Allkin Family Service Centre @ Ang Mo Kio 230") {
      throw new Error(`Packaged sg_msf_family_services returned an unexpected payload${formatServerLogs()}`);
    }

    const civicQueryResult = await client.callTool({
      name: "sg_query",
      arguments: {
        query: "Find a family service centre near 560230",
        mode: "execute",
        format: "json",
      },
    });
    if (
      !("structuredContent" in civicQueryResult)
      || civicQueryResult.structuredContent?.status !== "completed"
      || civicQueryResult.structuredContent?.workflow !== "civic_discovery"
    ) {
      throw new Error(`Packaged sg_query civic recipe did not complete successfully${formatServerLogs()}`);
    }
  } catch (error) {
    if (error instanceof Error && stderrChunks.length > 0 && !error.message.includes("Server stderr:")) {
      error.message += formatServerLogs();
    }
    throw error;
  } finally {
    await client.close().catch(() => undefined);
  }

  process.stdout.write("packaging smoke test passed\n");
} finally {
  for (const tarball of tarballs) {
    rmSync(tarball, { force: true });
  }
  if (mockServer !== null) {
    mockServer.child.kill("SIGTERM");
  }
  rmSync(tempDir, { recursive: true, force: true });
}
