import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { execFileSync } from "node:child_process";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const root = resolve(import.meta.dirname, "..");
const tempDir = mkdtempSync(join(tmpdir(), "sg-apis-smoke-"));
const tarballs = [];

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
  "sg_datagov_browse",
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

const EXPECTED_RESOURCE_URIS = ["sg://apis", "sg://tools", "sg://workflows"];

const run = (args, cwd = root) => {
  return execFileSync("npm", args, {
    cwd,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "inherit"],
  }).trim();
};

try {
  const packWorkspace = (workspace) => {
    const output = run(["pack", "--json", "--workspace", workspace]);
    const [{ filename }] = JSON.parse(output);
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
    env: { ...process.env, SG_APIS_LOG_LEVEL: "error" },
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
