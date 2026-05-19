import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { execFileSync } from "node:child_process";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const root = resolve(import.meta.dirname, "..");
const tempDir = mkdtempSync(join(tmpdir(), "dude-mcp-smoke-"));
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
  "sg_cea_salespersons",
  "sg_bca_licensed_builders",
  "sg_bca_registered_contractors",
  "sg_boa_architects",
  "sg_boa_architecture_firms",
  "sg_acra_entities",
  "sg_gebiz_tenders",
  "sg_hsa_licensed_pharmacies",
  "sg_hsa_health_product_licensees",
  "sg_hlb_hotels",
  "sg_sanctions_screen",
  "sg_opencorporates_links",
  "sg_adverse_media_lite",
  "sg_relationship_graph",
  "sg_business_dossier",
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
        name: "dude-mcp-smoke",
        private: true,
        type: "module",
      },
      null,
      2,
    ),
  );

  run(["install", "--no-package-lock", sharedTarball], tempDir);
  run(["install", "--no-package-lock", serverTarball], tempDir);

  JSON.parse(readFileSync(join(tempDir, "node_modules", "@dude", "mcp", "package.json"), "utf8"));
  JSON.parse(readFileSync(join(tempDir, "node_modules", "@dude", "shared", "package.json"), "utf8"));
  JSON.parse(readFileSync(join(tempDir, "node_modules", "@dude", "mcp", "openapi.json"), "utf8"));

  const transport = new StdioClientTransport({
    command: join(tempDir, "node_modules", ".bin", "dude-mcp"),
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
      name: "dude-mcp-smoke",
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

    if (client.getServerVersion()?.name !== "dude") {
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

    for (const promptName of ["recipe-business_due_diligence", "playbook-business_opportunity_scan"]) {
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

    const queryExecuteResult = await client.callTool({
      name: "sg_query",
      arguments: {
        query: "Business dossier for ABC CONSTRUCTION PTE LTD",
        mode: "plan",
        format: "json",
      },
    });
    if (
      !("structuredContent" in queryExecuteResult)
      || queryExecuteResult.structuredContent?.status !== "planned"
      || queryExecuteResult.structuredContent?.workflow !== "business_dossier"
    ) {
      throw new Error(`Packaged sg_query plan call did not return the CDD workflow${formatServerLogs()}`);
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
      name: "dude-mcp-compat-smoke",
      version: "0.1.0",
    },
    { capabilities: {} },
  );

  try {
    await compatClient.connect(compatTransport);
    if (compatClient.getServerVersion()?.name !== "dude") {
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
