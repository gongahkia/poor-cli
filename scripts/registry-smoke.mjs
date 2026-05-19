import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { execFileSync } from "node:child_process";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const root = resolve(import.meta.dirname, "..");
const tempDir = mkdtempSync(join(tmpdir(), "dude-mcp-registry-smoke-"));
const runtimeEnv = { ...process.env };

const serverPkg = JSON.parse(readFileSync(resolve(root, "packages/mcp-server/package.json"), "utf8"));
const sharedPkg = JSON.parse(readFileSync(resolve(root, "packages/shared/package.json"), "utf8"));
const serverVersion = serverPkg.version;
const sharedVersion = sharedPkg.version;

const run = (args, cwd = root) => {
  return execFileSync("npm", args, {
    cwd,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "inherit"],
  }).trim();
};

const sleep = async (ms) => new Promise((resolveSleep) => setTimeout(resolveSleep, ms));

const waitForRegistryVersion = async (packageName, version) => {
  const attempts = parseInt(process.env["REGISTRY_WAIT_RETRIES"] ?? "18", 10);
  const delayMs = parseInt(process.env["REGISTRY_WAIT_MS"] ?? "10000", 10);

  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      const publishedVersion = run(["view", packageName, "version"]);
      if (publishedVersion === version) {
        return;
      }
    } catch {
      // Package not visible yet.
    }

    if (attempt < attempts) {
      await sleep(delayMs);
    }
  }

  throw new Error(`Timed out waiting for ${packageName}@${version} to become visible in npm.`);
};

try {
  await waitForRegistryVersion("@dude/shared", sharedVersion);
  await waitForRegistryVersion("@dude/mcp", serverVersion);

  writeFileSync(
    join(tempDir, "package.json"),
    JSON.stringify(
      {
        name: "dude-mcp-registry-smoke",
        private: true,
        type: "module",
      },
      null,
      2,
    ),
  );

  run(
    [
      "install",
      "--no-package-lock",
      `@dude/shared@${sharedVersion}`,
      `@dude/mcp@${serverVersion}`,
    ],
    tempDir,
  );

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

  const client = new Client(
    { name: "dude-mcp-registry-smoke", version: serverVersion },
    { capabilities: {} },
  );

  try {
    await client.connect(transport);

    const prompts = await client.listPrompts();
    if (!(prompts.prompts ?? []).some((prompt) => prompt.name === "recipe-business_due_diligence")) {
      throw new Error("Registry-installed server did not expose recipe prompts.");
    }

    const templates = await client.listResourceTemplates();
    if (!(templates.resourceTemplates ?? []).some((template) => template.uriTemplate === "sg://recipes/{id}")) {
      throw new Error("Registry-installed server did not expose recipe resource templates.");
    }

    const resource = await client.readResource({ uri: "sg://workflows" });
    const resourceText = resource.contents.find((content) => "text" in content && typeof content.text === "string")?.text;
    if (resourceText === undefined) {
      throw new Error("Registry-installed server did not return workflow resource text.");
    }

    const recipesResource = await client.readResource({ uri: "sg://recipes" });
    const recipesText = recipesResource.contents.find((content) => "text" in content && typeof content.text === "string")?.text;
    if (recipesText === undefined) {
      throw new Error("Registry-installed server did not return recipe resource text.");
    }

    const runtimeResource = await client.readResource({ uri: "sg://runtime" });
    const runtimeText = runtimeResource.contents.find((content) => "text" in content && typeof content.text === "string")?.text;
    if (runtimeText === undefined) {
      throw new Error("Registry-installed server did not return runtime resource text.");
    }

    const queryResult = await client.callTool({
      name: "sg_query",
      arguments: {
        query: "Business dossier for ABC CONSTRUCTION PTE LTD",
        mode: "plan",
        format: "json",
      },
    });
    if (!("structuredContent" in queryResult) || queryResult.structuredContent?.workflow !== "business_dossier") {
      throw new Error("Registry-installed sg_query did not route company search to the business dossier workflow.");
    }

  } finally {
    await client.close().catch(() => undefined);
  }

  process.stdout.write("registry smoke test passed\n");
} finally {
  rmSync(tempDir, { recursive: true, force: true });
}
