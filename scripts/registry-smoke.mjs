import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { execFileSync } from "node:child_process";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const root = resolve(import.meta.dirname, "..");
const tempDir = mkdtempSync(join(tmpdir(), "sg-apis-registry-smoke-"));
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
  await waitForRegistryVersion("@sg-apis/shared", sharedVersion);
  await waitForRegistryVersion("sg-apis-mcp", serverVersion);

  writeFileSync(
    join(tempDir, "package.json"),
    JSON.stringify(
      {
        name: "sg-apis-registry-smoke",
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
      `@sg-apis/shared@${sharedVersion}`,
      `sg-apis-mcp@${serverVersion}`,
    ],
    tempDir,
  );

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

  const client = new Client(
    { name: "sg-apis-registry-smoke", version: serverVersion },
    { capabilities: {} },
  );

  try {
    await client.connect(transport);

    const prompts = await client.listPrompts();
    if (!(prompts.prompts ?? []).some((prompt) => prompt.name === "recipe-postal_route")) {
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

    const directResult = await client.callTool({
      name: "sg_datagov_get",
      arguments: {
        datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
        format: "json",
      },
    });
    const directText = "content" in directResult
      ? directResult.content.find((item) => item.type === "text" && typeof item.text === "string")?.text
      : undefined;
    if (directText === undefined) {
      throw new Error("Registry-installed server did not return sg_datagov_get content.");
    }
    const directPayload = JSON.parse(directText);
    if (
      directPayload.datasetId !== "d_8b84c4ee58e3cfc0ece0d773c8ca6abc"
      || directPayload.managedByAgencyName !== "Housing & Development Board"
    ) {
      throw new Error("Registry-installed sg_datagov_get returned an unexpected metadata payload.");
    }

    const resourcesResult = await client.callTool({
      name: "sg_datagov_resources",
      arguments: {
        datasetId: "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
        format: "json",
      },
    });
    const resourcesText = "content" in resourcesResult
      ? resourcesResult.content.find((item) => item.type === "text" && typeof item.text === "string")?.text
      : undefined;
    if (resourcesText === undefined) {
      throw new Error("Registry-installed server did not return sg_datagov_resources content.");
    }
    const resourcesPayload = JSON.parse(resourcesText);
    if (!Array.isArray(resourcesPayload.resources) || resourcesPayload.resources.length === 0) {
      throw new Error("Registry-installed sg_datagov_resources returned no resource metadata.");
    }

    const briefResult = await client.callTool({
      name: "sg_environment_brief",
      arguments: {
        area: "Tampines",
        region: "East",
        format: "json",
      },
    });
    const briefText = "content" in briefResult
      ? briefResult.content.find((item) => item.type === "text" && typeof item.text === "string")?.text
      : undefined;
    if (briefText === undefined) {
      throw new Error("Registry-installed server did not return sg_environment_brief content.");
    }
    const briefPayload = JSON.parse(briefText);
    if (briefPayload.title !== "Environment Brief") {
      throw new Error("Registry-installed sg_environment_brief returned an unexpected payload.");
    }
    for (const key of ["provenance", "freshness", "limits"]) {
      if (!Array.isArray(briefPayload[key])) {
        throw new Error(`Registry-installed sg_environment_brief omitted ${key}.`);
      }
    }

    const queryResult = await client.callTool({
      name: "sg_query",
      arguments: {
        query: "Environment snapshot of Singapore right now",
        mode: "execute",
        format: "json",
      },
    });
    if (!("structuredContent" in queryResult) || queryResult.structuredContent?.workflow !== "environment_brief") {
      throw new Error("Registry-installed sg_query did not route the environment snapshot to sg_environment_brief.");
    }

  } finally {
    await client.close().catch(() => undefined);
  }

  process.stdout.write("registry smoke test passed\n");
} finally {
  rmSync(tempDir, { recursive: true, force: true });
}
