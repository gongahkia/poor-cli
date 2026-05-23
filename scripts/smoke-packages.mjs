import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { execFileSync } from "node:child_process";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const root = resolve(import.meta.dirname, "..");
const tempDir = mkdtempSync(join(tmpdir(), "swee-sg-smoke-"));
const npmCacheDir = join(tempDir, "npm-cache");
const smokeEnv = {
  ...process.env,
  NPM_CONFIG_CACHE: npmCacheDir,
  npm_config_cache: npmCacheDir,
};
const tarballs = [];
const RUNTIME_LEAK_PATTERNS = ["/__tests__/", "/fixtures/", "/mock-server/", "/golden-outputs/"];
const runtimeEnv = { ...process.env };

const EXPECTED_TOOL_NAMES = [
  "swee_pulse_snapshot",
  "swee_pulse_mobility",
  "swee_pulse_weather",
  "swee_pulse_explain",
  "swee_shield_audit_lookup",
  "swee_shield_scan_tools",
  "sg_datagov_search",
  "sg_nea_forecast_2hr",
  "sg_lta_traffic_images",
  "sg_acra_entities",
  "sg_health_check",
  "sg_key_set",
  "sg_key_list",
  "sg_key_delete",
  "sg_cache_stats",
  "sg_cache_clear",
  "sg_config_get",
  "sg_config_set",
  "sg_trace_lookup",
  "sg_request_lookup",
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
    env: smokeEnv,
    encoding: "utf8",
    maxBuffer: 10 * 1024 * 1024,
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
        name: "swee-sg-smoke",
        private: true,
        type: "module",
      },
      null,
      2,
    ),
  );

  run(["install", "--no-package-lock", sharedTarball], tempDir);
  run(["install", "--no-package-lock", serverTarball], tempDir);

  JSON.parse(readFileSync(join(tempDir, "node_modules", "@swee-sg", "shield", "package.json"), "utf8"));
  JSON.parse(readFileSync(join(tempDir, "node_modules", "@swee-sg", "shared", "package.json"), "utf8"));
  JSON.parse(readFileSync(join(tempDir, "node_modules", "@swee-sg", "shield", "openapi.json"), "utf8"));

  const transport = new StdioClientTransport({
    command: join(tempDir, "node_modules", ".bin", "swee-sg"),
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
      name: "swee-sg-smoke",
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

    if (client.getServerVersion()?.name !== "swee-sg") {
      throw new Error(`Unexpected MCP server name: ${JSON.stringify(client.getServerVersion())}${formatServerLogs()}`);
    }

    const toolsResult = await client.listTools();
    const resourcesResult = await client.listResources();
    const promptsResult = await client.listPrompts();
    const templatesResult = await client.listResourceTemplates();

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

    for (const promptName of ["recipe-pulse_overview", "recipe-shield_recent_audit", "playbook-city_ops"]) {
      if (!(promptsResult.prompts ?? []).some((prompt) => prompt.name === promptName)) {
        throw new Error(`Packaged MCP server is missing prompt: ${promptName}${formatServerLogs()}`);
      }
    }

    for (const uriTemplate of ["sg://apis/{name}", "sg://tools/{name}", "sg://workflows/{id}", "sg://recipes/{id}"]) {
      if (!(templatesResult.resourceTemplates ?? []).some((template) => template.uriTemplate === uriTemplate)) {
        throw new Error(`Packaged MCP server is missing resource template: ${uriTemplate}${formatServerLogs()}`);
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

    const shieldScanResult = await client.callTool({
      name: "swee_shield_scan_tools",
      arguments: {},
    });
    if (
      !("structuredContent" in shieldScanResult)
      || typeof shieldScanResult.structuredContent?.scannedTools !== "number"
      || !Array.isArray(shieldScanResult.structuredContent?.findings)
    ) {
      throw new Error(`Packaged Shield scan call did not return scanner metadata${formatServerLogs()}`);
    }

  } catch (error) {
    if (error instanceof Error && stderrChunks.length > 0 && !error.message.includes("Server stderr:")) {
      error.message += formatServerLogs();
    }
    throw error;
  } finally {
    await client.close().catch(() => undefined);
  }

  const compatTransport = new StdioClientTransport({
    command: join(tempDir, "node_modules", ".bin", "sg-apis-mcp"),
    cwd: tempDir,
    env: {
      ...runtimeEnv,
      HOME: tempDir,
      SG_APIS_LOG_LEVEL: "error",
    },
    stderr: "pipe",
  });
  const compatClient = new Client(
    {
      name: "swee-sg-compat-smoke",
      version: "0.1.0",
    },
    { capabilities: {} },
  );

  try {
    await compatClient.connect(compatTransport);
    if (compatClient.getServerVersion()?.name !== "swee-sg") {
      throw new Error(`Compatibility bin returned unexpected MCP server name: ${JSON.stringify(compatClient.getServerVersion())}`);
    }
  } finally {
    await compatClient.close().catch(() => undefined);
  }

  process.stdout.write("packaging smoke test passed\n");
} finally {
  for (const tarball of tarballs) {
    rmSync(tarball, { force: true });
  }
  rmSync(tempDir, { recursive: true, force: true });
}
