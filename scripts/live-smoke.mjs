import { accessSync } from "node:fs";
import { resolve } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const root = resolve(import.meta.dirname, "..");
const serverEntry = resolve(root, "packages/mcp-server/dist/index.js");
const PUBLIC_ONLY = process.argv.includes("--public-only");

const getText = (items) => {
  const text = items.find((item) => typeof item?.text === "string")?.text;
  if (text === undefined) {
    throw new Error("Expected text content from MCP response.");
  }
  return text;
};

const getStructuredPayload = (result) => {
  if ("structuredContent" in result && result.structuredContent !== undefined) {
    return result.structuredContent;
  }
  return JSON.parse(getText(result.content));
};

const getRecordArray = (payload, label, key = "records") => {
  const records = payload?.[key];
  if (Array.isArray(records)) {
    return records;
  }
  const previewRecords = payload?.preview?.[key];
  if (Array.isArray(previewRecords)) {
    return previewRecords;
  }
  throw new Error(`${label} did not expose ${key} as an array in either the primary payload or artifact preview.`);
};

const getHealthRecord = (records, api) => {
  const record = records.find((candidate) => candidate?.api === api);
  if (record === undefined) {
    throw new Error(`sg_health_check did not return a record for ${api}.`);
  }
  return record;
};

const ensureLiveHealth = (record) => {
  if (record.authRequired === true && record.configured !== true) {
    throw new Error(`${record.api} is not configured for live use. Set env vars or keystore entries before running this smoke test.`);
  }
  if (record.reachable !== true) {
    throw new Error(`${record.api} live probe failed: ${record.error ?? "unreachable"}`);
  }
  if (typeof record.error === "string" && record.error.trim() !== "") {
    throw new Error(`${record.api} live probe returned an error: ${record.error}`);
  }
};

const ensureNonEmpty = (label, records) => {
  if (!Array.isArray(records) || records.length === 0) {
    throw new Error(`${label} returned no records.`);
  }
};

const callToolPayload = async (client, name, args) => {
  const result = await client.callTool({ name, arguments: args });
  return getStructuredPayload(result);
};

const readRuntimeCatalog = async (client) => {
  const resource = await client.readResource({ uri: "sg://runtime" });
  const text = resource.contents.find((content) => "text" in content && typeof content.text === "string")?.text;
  if (text === undefined) {
    throw new Error("sg://runtime did not return text content.");
  }
  return JSON.parse(text);
};

const ensureBriefArtifact = (label, payload, expectation) => {
  const record = payload?.record;
  if (record === null || typeof record !== "object") {
    throw new Error(`${label} did not return a brief artifact record.`);
  }
  if (record.title !== expectation.title) {
    throw new Error(`${label} returned an unexpected title: ${JSON.stringify(record.title)}`);
  }
  const provenance = Array.isArray(record.provenance) ? record.provenance : [];
  const totalProvenance = provenance.reduce(
    (sum, entry) => sum + (typeof entry?.recordCount === "number" ? entry.recordCount : 0),
    0,
  );
  const minimum = typeof expectation.minimumProvenanceCount === "number" ? expectation.minimumProvenanceCount : 0;
  if (totalProvenance < minimum) {
    throw new Error(`${label} returned insufficient live evidence. Expected provenance recordCount >= ${minimum}, received ${totalProvenance}.`);
  }
};

const ensureQueryCompleted = (label, payload, expectation) => {
  if (payload?.status !== "completed") {
    throw new Error(`${label} did not complete successfully. Received status ${JSON.stringify(payload?.status)}.`);
  }
  if (payload?.workflow !== expectation.workflow) {
    throw new Error(`${label} routed to ${JSON.stringify(payload?.workflow)} instead of ${JSON.stringify(expectation.workflow)}.`);
  }
};

const validateSmokePayload = (label, payload, expectation) => {
  switch (expectation.kind) {
    case "records_non_empty":
      ensureNonEmpty(label, getRecordArray(payload, label, expectation.key ?? "records"));
      return;
    case "brief_artifact":
      ensureBriefArtifact(label, payload, expectation);
      return;
    case "query_completed":
      ensureQueryCompleted(label, payload, expectation);
      return;
    default:
      throw new Error(`${label} has an unsupported smoke expectation: ${JSON.stringify(expectation)}`);
  }
};

const main = async () => {
  accessSync(serverEntry);

  const transport = new StdioClientTransport({
    command: "node",
    args: [serverEntry],
    cwd: root,
    env: {
      ...process.env,
      SG_APIS_LOG_LEVEL: process.env["SG_APIS_LOG_LEVEL"] ?? "error",
    },
    stderr: "pipe",
  });

  const stderrChunks = [];
  transport.stderr?.on("data", (chunk) => {
    stderrChunks.push(String(chunk));
  });

  const client = new Client(
    { name: "sg-apis-live-smoke", version: "0.1.0" },
    { capabilities: {} },
  );

  const serverLogs = () => {
    const joined = stderrChunks.join("").trim();
    return joined === "" ? "" : `\nServer stderr:\n${joined}`;
  };

  try {
    await client.connect(transport);

    const runtimeCatalog = await readRuntimeCatalog(client);
    const liveSurface = Array.isArray(runtimeCatalog?.liveSurface) ? runtimeCatalog.liveSurface : [];
    const releaseReadiness = runtimeCatalog?.releaseReadiness;
    const smokeCases = Array.isArray(releaseReadiness?.requiredSmokeCases) ? releaseReadiness.requiredSmokeCases : [];

    if (liveSurface.length === 0 || smokeCases.length === 0) {
      throw new Error("sg://runtime does not expose live surface and smoke coverage metadata.");
    }

    const releaseBlockingSurfaces = liveSurface.filter((entry) => entry?.releaseBlocking === true);
    const targetSurfaces = PUBLIC_ONLY
      ? releaseBlockingSurfaces.filter((entry) => entry?.authRequired !== true)
      : releaseBlockingSurfaces;
    const releaseBlockingCases = smokeCases.filter((entry) => entry?.releaseBlocking === true);
    const targetCases = PUBLIC_ONLY
      ? releaseBlockingCases.filter((entry) => entry?.authRequired !== true)
      : releaseBlockingCases;

    if (targetSurfaces.length === 0 || targetCases.length === 0) {
      throw new Error("No matching release-blocking smoke coverage found for selected mode.");
    }

    process.stdout.write(
      PUBLIC_ONLY
        ? "Checking public upstreams via sg_health_check...\n"
        : "Checking authenticated and public upstreams via sg_health_check...\n",
    );
    const healthPayload = await callToolPayload(client, "sg_health_check", {});
    const healthRecords = getRecordArray(healthPayload, "sg_health_check");

    for (const surface of targetSurfaces) {
      const record = getHealthRecord(healthRecords, surface.api);
      ensureLiveHealth(record);
      process.stdout.write(`- ${surface.api}: ok\n`);
    }

    process.stdout.write(PUBLIC_ONLY ? "Running public MCP smoke flow...\n" : "Running live MCP smoke flow...\n");

    for (const smokeCase of targetCases) {
      const payload = await callToolPayload(client, smokeCase.tool, smokeCase.arguments ?? {});
      validateSmokePayload(smokeCase.name, payload, smokeCase.expectation ?? {});
      process.stdout.write(`- ${smokeCase.name}: ok\n`);
    }

    process.stdout.write(PUBLIC_ONLY ? "public smoke test passed\n" : "live smoke test passed\n");
  } catch (error) {
    throw new Error(`${error instanceof Error ? error.message : String(error)}${serverLogs()}`);
  } finally {
    await client.close().catch(() => undefined);
  }
};

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  if (PUBLIC_ONLY) {
    process.stderr.write("See docs/troubleshooting.md for public smoke and diagnostics guidance.\n");
  } else {
    process.stderr.write("See docs/api-auth-guide.md for credential setup and live health-check behavior.\n");
    process.stderr.write("For no-credential onboarding, run: npm run test:smoke:public\n");
  }
  process.exit(1);
});
