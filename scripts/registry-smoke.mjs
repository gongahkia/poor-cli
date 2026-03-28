import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { execFileSync, spawn } from "node:child_process";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const root = resolve(import.meta.dirname, "..");
const tempDir = mkdtempSync(join(tmpdir(), "sg-apis-registry-smoke-"));
let mockServer = null;

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

  const client = new Client(
    { name: "sg-apis-registry-smoke", version: serverVersion },
    { capabilities: {} },
  );

  try {
    await client.connect(transport);

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

    const diligenceDirectResult = await client.callTool({
      name: "sg_boa_architecture_firms",
      arguments: {
        firmName: "DP Architects",
        format: "json",
      },
    });
    const diligenceDirectText = "content" in diligenceDirectResult
      ? diligenceDirectResult.content.find((item) => item.type === "text" && typeof item.text === "string")?.text
      : undefined;
    if (diligenceDirectText === undefined) {
      throw new Error("Registry-installed server did not return sg_boa_architecture_firms content.");
    }
    const diligenceDirectPayload = JSON.parse(diligenceDirectText);
    if (!Array.isArray(diligenceDirectPayload) || diligenceDirectPayload[0]?.firmName !== "DP Architects") {
      throw new Error("Registry-installed sg_boa_architecture_firms returned an unexpected payload.");
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
        query: "Transport status in Singapore right now",
        mode: "execute",
        format: "json",
      },
    });
    if (!("structuredContent" in queryResult) || queryResult.structuredContent?.workflow !== "transport_brief") {
      throw new Error("Registry-installed sg_query did not route transport status to sg_transport_brief.");
    }

    const routeRecipeResult = await client.callTool({
      name: "sg_query",
      arguments: {
        query: "Walk from 049178 to 048616",
        mode: "execute",
        format: "json",
      },
    });
    if (!("structuredContent" in routeRecipeResult) || routeRecipeResult.structuredContent?.workflow !== "route_plan") {
      throw new Error("Registry-installed sg_query did not complete the route recipe workflow.");
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
      || diligenceQueryResult.structuredContent?.workflow !== "architecture_firm_diligence"
    ) {
      throw new Error("Registry-installed sg_query did not complete the architecture-firm diligence workflow.");
    }
  } finally {
    await client.close().catch(() => undefined);
  }

  process.stdout.write("registry smoke test passed\n");
} finally {
  if (mockServer !== null) {
    mockServer.child.kill("SIGTERM");
  }
  rmSync(tempDir, { recursive: true, force: true });
}
