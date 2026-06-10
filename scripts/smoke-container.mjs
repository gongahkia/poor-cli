import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const root = resolve(import.meta.dirname, "..");
const runtimeEnv = { ...process.env };
const configuredImage = process.env["SG_APIS_CONTAINER_IMAGE"]?.trim();
const localImage = `swee-sg-smoke:${Date.now()}`;
const imageRef = configuredImage && configuredImage.length > 0 ? configuredImage : localImage;
const removeImageAfter = configuredImage === undefined || configuredImage.length === 0;

const failPreflight = (message) => {
  process.stderr.write(`${message}\n`);
  process.exit(1);
};

const docker = (args, options = {}) => {
  return execFileSync("docker", args, {
    cwd: root,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "inherit"],
    ...options,
  }).trim();
};

const dockerStreaming = (args) => {
  execFileSync("docker", args, {
    cwd: root,
    stdio: "inherit",
  });
};

const assertDockerAvailable = () => {
  try {
    execFileSync("docker", ["--version"], {
      cwd: root,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch {
    failPreflight("Docker is required for npm run test:smoke:container. Install Docker and make sure the docker CLI is on PATH.");
  }

  try {
    execFileSync("docker", ["info"], {
      cwd: root,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch {
    failPreflight("Docker is installed but the daemon is not reachable. Start Docker Desktop or the Docker daemon, then rerun npm run test:smoke:container.");
  }
};

const assert = (condition, message) => {
  if (!condition) {
    throw new Error(message);
  }
};

let client;
let imageReady = false;

try {
  assertDockerAvailable();

  if (configuredImage && configuredImage.length > 0) {
    dockerStreaming(["pull", imageRef]);
  } else {
    dockerStreaming(["build", "-t", imageRef, "."]);
  }
  imageReady = true;

  const openapiMetadata = JSON.parse(
    docker([
      "run",
      "--rm",
      "--entrypoint",
      "node",
      imageRef,
      "--input-type=module",
      "-e",
      [
        "import { readFileSync } from 'node:fs';",
        "const spec = JSON.parse(readFileSync('packages/mcp-server/openapi.json', 'utf8'));",
        "process.stdout.write(JSON.stringify({ title: spec.info?.title ?? null, pathCount: Object.keys(spec.paths ?? {}).length }));",
      ].join(" "),
    ]),
  );
  assert(typeof openapiMetadata.title === "string" && openapiMetadata.title.length > 0, "Container image is missing OpenAPI metadata.");
  assert(openapiMetadata.pathCount > 0, "Container image OpenAPI artifact has no paths.");

  const transport = new StdioClientTransport({
    command: "docker",
    args: ["run", "--rm", "-i", "-e", "HOME=/tmp/swee-sg", "-e", "SG_APIS_LOG_LEVEL=error", imageRef],
    cwd: root,
    env: runtimeEnv,
    stderr: "pipe",
  });
  const stderrChunks = [];
  transport.stderr?.on("data", (chunk) => {
    stderrChunks.push(String(chunk));
  });

  const formatServerLogs = () => {
    const logs = stderrChunks.join("").trim();
    return logs.length > 0 ? `\nContainer stderr:\n${logs}` : "";
  };

  client = new Client(
    { name: "swee-sg-container-smoke", version: "0.1.0" },
    { capabilities: {} },
  );
  await client.connect(transport);

  const serverVersion = client.getServerVersion();
  assert(serverVersion?.name === "swee-sg", `Unexpected container server identity: ${JSON.stringify(serverVersion)}${formatServerLogs()}`);

  const [toolsResult, resourcesResult, promptsResult, templatesResult] = await Promise.all([
    client.listTools(),
    client.listResources(),
    client.listPrompts(),
    client.listResourceTemplates(),
  ]);

  const pulseSnapshot = (toolsResult.tools ?? []).find((tool) => tool.name === "swee_pulse_snapshot");
  assert(pulseSnapshot !== undefined, `Container image is missing swee_pulse_snapshot${formatServerLogs()}`);
  assert(typeof pulseSnapshot.title === "string" && pulseSnapshot.title.length > 0, `Container swee_pulse_snapshot is missing title metadata${formatServerLogs()}`);
  assert(pulseSnapshot.annotations?.readOnlyHint === true, `Container swee_pulse_snapshot is missing readOnlyHint metadata${formatServerLogs()}`);
  assert(pulseSnapshot.outputSchema !== undefined, `Container swee_pulse_snapshot is missing outputSchema metadata${formatServerLogs()}`);

  const recipesResource = (resourcesResult.resources ?? []).find((resource) => resource.uri === "sg://recipes");
  assert(recipesResource !== undefined, `Container image is missing sg://recipes${formatServerLogs()}`);
  assert(typeof recipesResource.title === "string" && recipesResource.title.length > 0, `Container sg://recipes is missing title metadata${formatServerLogs()}`);
  assert(typeof recipesResource.description === "string" && recipesResource.description.length > 0, `Container sg://recipes is missing description metadata${formatServerLogs()}`);

  assert(
    (promptsResult.prompts ?? []).some((prompt) => prompt.name === "recipe-pulse_overview"),
    `Container image is missing Pulse recipe prompts${formatServerLogs()}`,
  );
  assert(
    (templatesResult.resourceTemplates ?? []).some((template) => template.uriTemplate === "sg://recipes/{id}"),
    `Container image is missing recipe resource templates${formatServerLogs()}`,
  );

  const recipesPayload = await client.readResource({ uri: "sg://recipes" });
  const recipesText = recipesPayload.contents.find((content) => "text" in content && typeof content.text === "string")?.text;
  assert(recipesText !== undefined, `Container sg://recipes did not return text content${formatServerLogs()}`);
  const recipes = JSON.parse(recipesText);
  assert(Array.isArray(recipes) && recipes.length > 0, `Container sg://recipes returned an empty payload${formatServerLogs()}`);

  const configResult = await client.callTool({
    name: "sg_config_get",
    arguments: {},
  });
  const configText = "content" in configResult
    ? configResult.content.find((item) => item.type === "text" && typeof item.text === "string")?.text
    : undefined;
  assert(configText !== undefined && configText.includes("\"cache\""), `Container sg_config_get did not return config content${formatServerLogs()}`);

  process.stdout.write("container smoke test passed\n");
} catch (error) {
  process.stderr.write(`container smoke failed: ${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
} finally {
  await client?.close().catch(() => undefined);

  if (removeImageAfter && imageReady) {
    try {
      docker(["image", "rm", "-f", imageRef]);
    } catch {
      // Best-effort cleanup only.
    }
  }
}
