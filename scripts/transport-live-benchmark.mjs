import { accessSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const root = resolve(import.meta.dirname, "..");
const serverEntry = resolve(root, "packages/mcp-server/dist/index.js");

const readOption = (name) => {
  const direct = process.argv.find((arg) => arg.startsWith(`--${name}=`));
  if (direct !== undefined) {
    return direct.slice(name.length + 3);
  }
  const index = process.argv.findIndex((arg) => arg === `--${name}`);
  return index === -1 ? undefined : process.argv[index + 1];
};

const outputPath = resolve(root, readOption("output") ?? "artifacts/transport/latest.json");
const markdownPath = resolve(root, readOption("markdown") ?? "artifacts/transport/latest.md");
const generatedAt = process.env["SWEE_TRANSPORT_BENCHMARK_GENERATED_AT"] ?? new Date().toISOString();

const TRANSPORT_SOURCES = [
  {
    sourceTool: "sg_lta_traffic_incidents",
    source: "LTA DataMall",
    authRequired: true,
    surface: "Swee Pulse mobility",
    coverage: "Network-wide traffic incident rows.",
  },
  {
    sourceTool: "sg_lta_train_alerts",
    source: "LTA DataMall",
    authRequired: true,
    surface: "Swee Pulse mobility",
    coverage: "Network-wide train service alerts and operator messages.",
  },
  {
    sourceTool: "sg_lta_road_works",
    source: "LTA DataMall",
    authRequired: true,
    surface: "Swee Pulse mobility",
    coverage: "Network-wide road-work events with start/end timing.",
  },
  {
    sourceTool: "sg_lta_road_openings",
    source: "LTA DataMall",
    authRequired: true,
    surface: "Swee Pulse mobility",
    coverage: "Network-wide road-opening events with start/end timing.",
  },
  {
    sourceTool: "sg_lta_traffic_images",
    source: "data.gov.sg transport feed",
    authRequired: false,
    surface: "Swee Pulse source health",
    coverage: "Traffic camera image references and camera timestamps.",
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
  const result = await client.callTool({ name, arguments: args });
  return getStructuredPayload(result);
};

const isCredentialGap = (source) => {
  const text = [
    source.sourceTool,
    ...(Array.isArray(source.gaps) ? source.gaps.flatMap((gap) => [gap.code, gap.message]) : []),
  ].join(" ");
  return /\b(auth|credential|api key|accountkey|key missing|not configured)\b/i.test(text);
};

const classifySourceState = (source) => {
  if (source === undefined) return "not_returned";
  if (isCredentialGap(source)) return "credential_missing";
  if (source.status === "ready") return "ready";
  if (source.status === "stale") return "stale";
  return "gap";
};

const sourceCheckFromHealth = (profile, source) => ({
  ...profile,
  state: classifySourceState(source),
  pulseStatus: source?.status ?? "not_returned",
  recordCount: source?.recordCount ?? 0,
  observedAt: source?.observedAt ?? null,
  upstreamTimestamp: source?.freshness?.upstreamTimestamp ?? null,
  freshnessStatus: source?.freshness?.status ?? "unknown",
  ageSeconds: source?.freshness?.ageSeconds ?? null,
  gapCodes: Array.isArray(source?.gaps) ? source.gaps.map((gap) => gap.code) : [],
  gapMessages: Array.isArray(source?.gaps) ? source.gaps.map((gap) => gap.message) : [],
});

const escapeCell = (value) => String(value ?? "n/a").replaceAll("|", "\\|").replace(/\s+/g, " ").trim();

const writeArtifacts = (artifact) => {
  mkdirSync(dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, JSON.stringify(artifact, null, 2) + "\n");

  mkdirSync(dirname(markdownPath), { recursive: true });
  const markdown = [
    "# Swee Transport Live Benchmark",
    "",
    `Generated: ${artifact.generatedAt}`,
    "",
    `Pulse audit: ${artifact.shield.pulseAuditId ?? "n/a"}`,
    "",
    `Shield decision: ${artifact.shield.pulseDecision === null ? "n/a" : `${artifact.shield.pulseDecision.decision} / ${artifact.shield.pulseDecision.riskLevel}`}`,
    "",
    "## Source Checks",
    "",
    "| Source tool | Source | Auth | State | Records | Freshness | Upstream | Gaps |",
    "| --- | --- | --- | --- | ---: | --- | --- | --- |",
    ...artifact.sourceChecks.map((item) =>
      `| ${escapeCell(item.sourceTool)} | ${escapeCell(item.source)} | ${item.authRequired ? "required" : "not required"} | ${escapeCell(item.state)} | ${item.recordCount} | ${escapeCell(item.freshnessStatus)} | ${escapeCell(item.upstreamTimestamp)} | ${escapeCell(item.gapCodes.join(", ") || "none")} |`,
    ),
    "",
    "## Pulse Summary",
    "",
    `Signals: ${artifact.pulse.signalCount}`,
    "",
    `Watch-or-higher signals: ${artifact.pulse.actionSignalCount}`,
    "",
    `Gaps: ${artifact.pulse.gapCount}`,
    "",
    "## Limits",
    "",
    ...artifact.limits.map((limit) => `- ${limit}`),
    "",
  ].join("\n");
  writeFileSync(markdownPath, markdown);
};

const buildArtifact = ({ mobilityPayload, auditPayload }) => {
  const sourceHealth = Array.isArray(mobilityPayload.sourceHealth) ? mobilityPayload.sourceHealth : [];
  const sourceHealthByTool = new Map(sourceHealth.map((source) => [source.sourceTool, source]));
  const signals = Array.isArray(mobilityPayload.signals) ? mobilityPayload.signals : [];
  const gaps = Array.isArray(mobilityPayload.gaps) ? mobilityPayload.gaps : [];
  const shield = mobilityPayload.shield ?? null;
  const replay = auditPayload?.replay ?? null;
  const auditRecord = auditPayload?.record ?? null;

  return {
    schemaVersion: "swee-transport-live-benchmark/v1",
    generatedAt,
    source: "local-live-mcp",
    command: "npm run benchmark:transport:live",
    pulse: {
      toolName: "swee_pulse_mobility",
      signalCount: signals.length,
      actionSignalCount: signals.filter((signal) => signal.severity !== "info").length,
      gapCount: gaps.length,
      gaps,
      sourceHealth,
    },
    sourceChecks: TRANSPORT_SOURCES.map((profile) => sourceCheckFromHealth(profile, sourceHealthByTool.get(profile.sourceTool))),
    shield: {
      pulseAuditId: shield?.auditId ?? auditRecord?.auditId ?? null,
      pulseDecision: shield?.decision ?? auditRecord?.decision ?? null,
      pulseAudit: auditRecord,
      pulseReplay: replay,
    },
    limits: [
      "This artifact is live local evidence, not an SLA or official public-agency service status.",
      "Credentialed LTA DataMall checks require SG_API_LTA_KEY or a local Swee SG keystore entry.",
      "Missing upstream timestamps and source gaps are preserved instead of being filled with synthetic freshness.",
      "Stop-level bus arrivals, carparks, and taxis remain direct-adapter follow-ups; this proof covers the default Pulse mobility runtime path.",
    ],
  };
};

const main = async () => {
  accessSync(serverEntry);
  const stateDir = mkdtempSync(resolve(tmpdir(), "swee-transport-benchmark-"));
  const transport = new StdioClientTransport({
    command: "node",
    args: [serverEntry],
    cwd: root,
    env: {
      ...process.env,
      SG_APIS_LOG_LEVEL: process.env["SG_APIS_LOG_LEVEL"] ?? "error",
      SG_APIS_STATE_DIR: stateDir,
    },
    stderr: "pipe",
  });

  const stderrChunks = [];
  transport.stderr?.on("data", (chunk) => {
    stderrChunks.push(String(chunk));
  });

  const client = new Client(
    { name: "swee-transport-live-benchmark", version: "0.1.0" },
    { capabilities: {} },
  );

  const serverLogs = () => {
    const joined = stderrChunks.join("").trim();
    return joined === "" ? "" : `\nServer stderr:\n${joined}`;
  };

  try {
    await client.connect(transport);
    const mobilityPayload = await callToolPayload(client, "swee_pulse_mobility", {});
    const pulseAuditId = mobilityPayload.shield?.auditId;
    const auditPayload = typeof pulseAuditId === "string"
      ? await callToolPayload(client, "swee_shield_audit_lookup", { auditId: pulseAuditId })
      : null;
    const artifact = buildArtifact({ mobilityPayload, auditPayload });
    writeArtifacts(artifact);

    const summary = {
      ok: true,
      output: outputPath,
      markdown: markdownPath,
      sourceStates: Object.fromEntries(artifact.sourceChecks.map((item) => [item.sourceTool, item.state])),
      pulseAuditId: artifact.shield.pulseAuditId,
    };
    process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
  } catch (error) {
    throw new Error(`${error instanceof Error ? error.message : String(error)}${serverLogs()}`);
  } finally {
    await client.close().catch(() => undefined);
    rmSync(stateDir, { recursive: true, force: true });
  }
};

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.stderr.write("Run npm run build first. Missing SG_API_LTA_KEY should appear as credential_missing in the artifact, not as a command failure.\n");
  process.exit(1);
});
