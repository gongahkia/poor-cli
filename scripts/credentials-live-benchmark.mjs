import { accessSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const root = resolve(import.meta.dirname, "..");
const serverEntry = resolve(root, "packages/mcp-server/dist/index.js");
const outputPath = resolve(root, "artifacts/credentials/latest.json");
const markdownPath = resolve(root, "artifacts/credentials/latest.md");
const generatedAt = process.env["SWEE_CREDENTIALS_BENCHMARK_GENERATED_AT"] ?? new Date().toISOString();

const PROBES = [
  {
    sourceTool: "sg_onemap_geocode",
    source: "OneMap",
    family: "geospatial",
    authRequired: true,
    input: { searchVal: "Raffles Place", limit: 3 },
    coverage: "Credentialed OneMap geocoding readiness.",
    credentialNames: ["SG_API_ONEMAP_EMAIL", "SG_API_ONEMAP_PASSWORD", "onemap_email", "onemap_password"],
  },
  {
    sourceTool: "sg_datagov_search",
    source: "data.gov.sg",
    family: "dataset-discovery",
    authRequired: false,
    input: { keyword: "weather", limit: 3 },
    coverage: "Public no-key data.gov.sg discovery readiness and rate-limit posture.",
    credentialNames: [],
  },
];

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

const callToolPayload = async (client, name, args) => {
  const result = await client.callTool(
    { name, arguments: args },
    undefined,
    { timeout: 120_000, maxTotalTimeout: 180_000 },
  );
  return getStructuredPayload(result);
};

const latestAuditForTool = async (client, toolName) => {
  const payload = await callToolPayload(client, "swee_shield_audit_lookup", { toolName, limit: 1 });
  return Array.isArray(payload.records) ? payload.records[0] ?? null : null;
};

const isCredentialText = (value) => /\b(auth|credential|api key|accountkey|key missing|not configured|token)\b/i.test(value);
const isRateLimitText = (value) => /\b(rate limit|too many requests|429)\b/i.test(value);

const countRecords = (payload) => {
  if (Array.isArray(payload?.records)) return payload.records.length;
  if (payload?.record === null) return 0;
  if (payload?.record !== undefined) return 1;
  return 0;
};

const classifyPayload = (payload, thrownError) => {
  if (thrownError !== null) {
    const message = thrownError instanceof Error ? thrownError.message : String(thrownError);
    if (isCredentialText(message)) return "credential_missing";
    if (isRateLimitText(message)) return "gap";
    return "error";
  }
  if (payload?.error !== undefined) {
    const message = JSON.stringify(payload.error);
    if (isCredentialText(message)) return "credential_missing";
    if (isRateLimitText(message)) return "gap";
    return "error";
  }
  return countRecords(payload) > 0 ? "ready" : "gap";
};

const runProbe = async (client, probe) => {
  let payload = null;
  let thrownError = null;
  try {
    payload = await callToolPayload(client, probe.sourceTool, probe.input);
  } catch (error) {
    thrownError = error;
  }
  const audit = await latestAuditForTool(client, probe.sourceTool);
  const state = classifyPayload(payload, thrownError);
  const thrownMessage = thrownError instanceof Error ? thrownError.message : thrownError === null ? null : String(thrownError);
  const payloadError = payload?.error;
  return {
    sourceTool: probe.sourceTool,
    source: probe.source,
    family: probe.family,
    authRequired: probe.authRequired,
    coverage: probe.coverage,
    credentialNames: probe.credentialNames,
    state,
    recordCount: countRecords(payload),
    observedAt: audit?.finishedAt ?? null,
    gapCodes: payloadError?.code !== undefined ? [payloadError.code] : thrownMessage === null ? [] : ["TOOL_CALL_FAILED"],
    gapMessages: payloadError?.message !== undefined ? [payloadError.message] : thrownMessage === null ? [] : [thrownMessage],
    auditId: payload?.shield?.auditId ?? audit?.auditId ?? null,
    decision: payload?.shield?.decision ?? audit?.decision ?? null,
  };
};

const escapeCell = (value) => String(value ?? "n/a").replaceAll("|", "\\|").replace(/\s+/g, " ").trim();

const writeArtifacts = (artifact) => {
  mkdirSync(dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, JSON.stringify(artifact, null, 2) + "\n");

  mkdirSync(dirname(markdownPath), { recursive: true });
  const markdown = [
    "# Swee Credential Readiness Benchmark",
    "",
    `Generated: ${artifact.generatedAt}`,
    "",
    "| Tool | Source | Auth required | State | Records | Audit | Gaps |",
    "| --- | --- | --- | --- | ---: | --- | --- |",
    ...artifact.credentialChecks.map((item) =>
      `| ${escapeCell(item.sourceTool)} | ${escapeCell(item.source)} | ${item.authRequired ? "yes" : "no"} | ${escapeCell(item.state)} | ${item.recordCount} | ${escapeCell(item.auditId)} | ${escapeCell(item.gapCodes.join(", ") || "none")} |`,
    ),
    "",
    "## Limits",
    "",
    ...artifact.limits.map((limit) => `- ${limit}`),
    "",
  ].join("\n");
  writeFileSync(markdownPath, markdown);
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
    { name: "swee-credential-readiness-live-benchmark", version: "0.1.0" },
    { capabilities: {} },
  );

  const serverLogs = () => {
    const joined = stderrChunks.join("").trim();
    return joined === "" ? "" : `\nServer stderr:\n${joined}`;
  };

  try {
    await client.connect(transport);
    const credentialChecks = [];
    for (const probe of PROBES) {
      credentialChecks.push(await runProbe(client, probe));
    }
    const artifact = {
      schemaVersion: "swee-credential-live-benchmark/v1",
      generatedAt,
      source: "local-live-mcp",
      command: "npm run benchmark:credentials:live",
      credentialChecks,
      limits: [
        "This artifact records local credential readiness only; credential_missing is an actionable setup state, not a runtime failure.",
        "OneMap may use SG_API_ONEMAP_EMAIL and SG_API_ONEMAP_PASSWORD or the onemap_email/onemap_password keystore keys.",
        "data.gov.sg discovery currently uses the public no-key path and remains subject to upstream public rate limits.",
      ],
    };
    writeArtifacts(artifact);
    process.stdout.write(`${JSON.stringify({
      ok: true,
      output: outputPath,
      markdown: markdownPath,
      states: Object.fromEntries(credentialChecks.map((check) => [check.sourceTool, check.state])),
    }, null, 2)}\n`);
  } catch (error) {
    throw new Error(`${error instanceof Error ? error.message : String(error)}${serverLogs()}`);
  } finally {
    await client.close().catch(() => undefined);
  }
};

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.stderr.write("Run npm run build first. Credential gaps should be written into the artifact instead of becoming invented readiness claims.\n");
  process.exit(1);
});
