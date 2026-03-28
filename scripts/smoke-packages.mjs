import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { execFileSync } from "node:child_process";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const root = resolve(import.meta.dirname, "..");
const tempDir = mkdtempSync(join(tmpdir(), "sg-apis-smoke-"));
const tarballs = [];
const RUNTIME_LEAK_PATTERNS = ["/__tests__/", "/fixtures/", "/mock-server/", "/golden-outputs/"];
const runtimeEnv = { ...process.env };

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

const EXPECTED_RESOURCE_URIS = [
  "sg://apis",
  "sg://tools",
  "sg://workflows",
  "sg://recipes",
  "sg://runtime",
  "sg://playbooks",
  "sg://benchmarks",
];

const run = (args, cwd = root) => {
  return execFileSync("npm", args, {
    cwd,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "inherit"],
  }).trim();
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

  const transport = new StdioClientTransport({
    command: join(tempDir, "node_modules", ".bin", "sg-apis-mcp"),
    cwd: tempDir,
    env: {
      ...runtimeEnv,
      HOME: tempDir,
      SG_APIS_LOG_LEVEL: "error",
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

      const isNonEmptyArray = Array.isArray(parsed) && parsed.length > 0;
      const isNonEmptyObject = parsed !== null && typeof parsed === "object" && !Array.isArray(parsed) && Object.keys(parsed).length > 0;
      if (!isNonEmptyArray && !isNonEmptyObject) {
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
    if (
      datasetMetadataPayload.datasetId !== "d_8b84c4ee58e3cfc0ece0d773c8ca6abc"
      || datasetMetadataPayload.managedByAgencyName !== "Housing & Development Board"
    ) {
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

    const queryExecuteResult = await client.callTool({
      name: "sg_query",
      arguments: {
        query: "Environment snapshot of Singapore right now",
        mode: "execute",
        format: "json",
      },
    });
    if (
      !("structuredContent" in queryExecuteResult)
      || queryExecuteResult.structuredContent?.status !== "completed"
      || queryExecuteResult.structuredContent?.workflow !== "environment_brief"
    ) {
      throw new Error(`Packaged sg_query execute call did not complete successfully${formatServerLogs()}`);
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
  rmSync(tempDir, { recursive: true, force: true });
}
