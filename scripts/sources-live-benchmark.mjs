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

const outputPath = resolve(root, readOption("output") ?? "artifacts/sources/latest.json");
const markdownPath = resolve(root, readOption("markdown") ?? "artifacts/sources/latest.md");
const generatedAt = process.env["SWEE_SOURCES_BENCHMARK_GENERATED_AT"] ?? new Date().toISOString();
const DATASET_DOWNLOAD_PAUSE_MS = 5500;

const DIRECT_PROBES = [
  {
    sourceTool: "sg_onemap_geocode",
    source: "OneMap",
    family: "geospatial",
    authRequired: true,
    input: { searchVal: "Raffles Place", limit: 3 },
    coverage: "Address/building-name geocoding to Singapore coordinates.",
    credentialGuidance: "Set SG_API_ONEMAP_EMAIL and SG_API_ONEMAP_PASSWORD, or store onemap_email/onemap_password with sg_key_set.",
  },
  {
    sourceTool: "sg_datagov_search",
    source: "data.gov.sg",
    family: "dataset-discovery",
    authRequired: false,
    input: { keyword: "weather", limit: 5 },
    coverage: "Public dataset discovery through data.gov.sg search.",
    rateLimitPauseMs: 2600,
  },
  {
    sourceTool: "sg_singstat_search",
    source: "SingStat",
    family: "statistics-discovery",
    authRequired: false,
    input: { keyword: "population", limit: 5 },
    coverage: "Official statistics table discovery through SingStat Table Builder search.",
  },
  {
    sourceTool: "sg_hawker_closures",
    source: "NEA via data.gov.sg",
    family: "hawker-operations",
    authRequired: false,
    input: { limit: 5 },
    coverage: "Hawker centre quarterly cleaning and other-works closure windows.",
    rateLimitPauseMs: 2600,
  },
  {
    sourceTool: "sg_nlb_libraries",
    source: "NLB via data.gov.sg",
    family: "public-amenities",
    authRequired: false,
    input: { limit: 5 },
    coverage: "Public library directory records.",
    rateLimitPauseMs: DATASET_DOWNLOAD_PAUSE_MS,
  },
  {
    sourceTool: "sg_sportsg_facilities",
    source: "SportSG via data.gov.sg",
    family: "public-facilities",
    authRequired: false,
    input: { limit: 5 },
    coverage: "Public sports facility directory records.",
    rateLimitPauseMs: DATASET_DOWNLOAD_PAUSE_MS,
  },
  {
    sourceTool: "sg_nparks_parks",
    source: "NParks via data.gov.sg",
    family: "parks",
    authRequired: false,
    input: { limit: 5 },
    coverage: "Parks and nature reserve directory records.",
    rateLimitPauseMs: DATASET_DOWNLOAD_PAUSE_MS,
  },
  {
    sourceTool: "sg_pub_water_levels",
    source: "PUB via data.gov.sg",
    family: "water-levels",
    authRequired: false,
    input: { limit: 5 },
    coverage: "PUB water-level sensor station records; public fields do not include live water-height readings.",
    rateLimitPauseMs: DATASET_DOWNLOAD_PAUSE_MS,
  },
  {
    sourceTool: "sg_pa_community_outlets",
    source: "People's Association via data.gov.sg",
    family: "community-amenities",
    authRequired: false,
    input: { limit: 5 },
    coverage: "Community club and PAssion WaVe outlet directory records.",
    rateLimitPauseMs: DATASET_DOWNLOAD_PAUSE_MS,
  },
];

const NEA_SOURCE_PROFILES = [
  {
    sourceTool: "sg_nea_forecast_2hr",
    source: "NEA",
    family: "weather",
    authRequired: false,
    coverage: "2-hour forecast coverage for Singapore areas.",
  },
  {
    sourceTool: "sg_nea_air_quality",
    source: "NEA",
    family: "weather",
    authRequired: false,
    coverage: "Regional PSI and PM2.5 readings.",
  },
  {
    sourceTool: "sg_nea_rainfall",
    source: "NEA",
    family: "weather",
    authRequired: false,
    coverage: "Station rainfall readings.",
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
const isSourceGapText = (value) => /\b(source gap|unsupported|not exposed|not available|no live|non-geojson)\b/i.test(value);
const isRateLimitText = (value) => /\b(rate limit|too many requests|429)\b/i.test(value);

const classifyHealth = (source) => {
  if (source === undefined) return "not_returned";
  const text = [
    source.sourceTool,
    ...(Array.isArray(source.gaps) ? source.gaps.flatMap((gap) => [gap.code, gap.message]) : []),
  ].join(" ");
  if (isRateLimitText(text)) return "gap";
  if (isCredentialText(text)) return "credential_missing";
  if (source.status === "ready") return "ready";
  if (source.status === "stale") return "stale";
  return "gap";
};

const countRecords = (payload) => {
  if (Array.isArray(payload?.records)) return payload.records.length;
  if (Array.isArray(payload?.alerts) || Array.isArray(payload?.messages)) {
    return (payload.alerts?.length ?? 0) + (payload.messages?.length ?? 0);
  }
  if (payload?.record === null) return 0;
  if (payload?.record !== undefined) return 1;
  return 0;
};

const classifyDirectPayload = (payload, thrownError) => {
  if (thrownError !== null) {
    const message = thrownError instanceof Error ? thrownError.message : String(thrownError);
    if (isRateLimitText(message)) return "gap";
    if (isSourceGapText(message)) return "gap";
    return isCredentialText(message) ? "credential_missing" : "error";
  }
  if (payload?.error !== undefined) {
    const message = JSON.stringify(payload.error);
    if (isRateLimitText(message)) return "gap";
    if (isSourceGapText(message)) return "gap";
    return isCredentialText(message) ? "credential_missing" : "error";
  }
  return countRecords(payload) > 0 ? "ready" : "gap";
};

const pause = (milliseconds) => new Promise((resolvePause) => {
  setTimeout(resolvePause, milliseconds);
});

const sourceCheckFromHealth = (profile, source) => ({
  ...profile,
  state: classifyHealth(source),
  recordCount: source?.recordCount ?? 0,
  observedAt: source?.observedAt ?? null,
  upstreamTimestamp: source?.freshness?.upstreamTimestamp ?? null,
  freshnessStatus: source?.freshness?.status ?? "unknown",
  ageSeconds: source?.freshness?.ageSeconds ?? null,
  gapCodes: Array.isArray(source?.gaps) ? source.gaps.map((gap) => gap.code) : [],
  gapMessages: Array.isArray(source?.gaps) ? source.gaps.map((gap) => gap.message) : [],
  auditId: null,
  decision: null,
});

const directProbeCheck = async (client, probe) => {
  let payload = null;
  let thrownError = null;
  try {
    payload = await callToolPayload(client, probe.sourceTool, probe.input);
  } catch (error) {
    thrownError = error;
  }
  const audit = await latestAuditForTool(client, probe.sourceTool);
  const state = classifyDirectPayload(payload, thrownError);
  const thrownMessage = thrownError instanceof Error ? thrownError.message : thrownError === null ? null : String(thrownError);
  const payloadError = payload?.error;
  return {
    sourceTool: probe.sourceTool,
    source: probe.source,
    family: probe.family,
    authRequired: probe.authRequired,
    coverage: probe.coverage,
    state,
    recordCount: countRecords(payload),
    observedAt: audit?.finishedAt ?? null,
    upstreamTimestamp: payload?.meta?.upstreamTimestamp ?? null,
    freshnessStatus: payload?.meta?.upstreamTimestamp === undefined ? "unknown" : "reported",
    ageSeconds: null,
    gapCodes: payloadError?.code !== undefined ? [payloadError.code] : thrownMessage === null ? [] : ["TOOL_CALL_FAILED"],
    gapMessages: payloadError?.message !== undefined ? [payloadError.message] : thrownMessage === null ? [] : [thrownMessage],
    auditId: payload?.shield?.auditId ?? audit?.auditId ?? null,
    decision: payload?.shield?.decision ?? audit?.decision ?? null,
    credentialGuidance: state === "credential_missing" ? probe.credentialGuidance ?? null : null,
  };
};

const escapeCell = (value) => String(value ?? "n/a").replaceAll("|", "\\|").replace(/\s+/g, " ").trim();

const writeArtifacts = (artifact) => {
  mkdirSync(dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, JSON.stringify(artifact, null, 2) + "\n");

  mkdirSync(dirname(markdownPath), { recursive: true });
  const markdown = [
    "# Swee Source Family Live Benchmark",
    "",
    `Generated: ${artifact.generatedAt}`,
    "",
    "## Source Checks",
    "",
    "| Family | Source tool | Source | State | Records | Freshness | Audit | Gaps |",
    "| --- | --- | --- | --- | ---: | --- | --- | --- |",
    ...artifact.sourceChecks.map((item) =>
      `| ${escapeCell(item.family)} | ${escapeCell(item.sourceTool)} | ${escapeCell(item.source)} | ${escapeCell(item.state)} | ${item.recordCount} | ${escapeCell(item.freshnessStatus)} | ${escapeCell(item.auditId)} | ${escapeCell(item.gapCodes.join(", ") || "none")} |`,
    ),
    "",
    "## Pulse Weather",
    "",
    `Pulse audit: ${artifact.pulseWeather.auditId ?? "n/a"}`,
    "",
    `Signals: ${artifact.pulseWeather.signalCount}`,
    "",
    `Gaps: ${artifact.pulseWeather.gapCount}`,
    "",
    "## Limits",
    "",
    ...artifact.limits.map((limit) => `- ${limit}`),
    "",
  ].join("\n");
  writeFileSync(markdownPath, markdown);
};

const buildWeatherChecks = (weatherPayload) => {
  const sourceHealth = Array.isArray(weatherPayload.sourceHealth) ? weatherPayload.sourceHealth : [];
  const byTool = new Map(sourceHealth.map((source) => [source.sourceTool, source]));
  return NEA_SOURCE_PROFILES.map((profile) => sourceCheckFromHealth(profile, byTool.get(profile.sourceTool)));
};

const main = async () => {
  accessSync(serverEntry);
  const stateDir = mkdtempSync(resolve(tmpdir(), "swee-sources-benchmark-"));
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
    { name: "swee-source-family-live-benchmark", version: "0.1.0" },
    { capabilities: {} },
  );

  const serverLogs = () => {
    const joined = stderrChunks.join("").trim();
    return joined === "" ? "" : `\nServer stderr:\n${joined}`;
  };

  try {
    await client.connect(transport);
    const weatherPayload = await callToolPayload(client, "swee_pulse_weather", {});
    const weatherChecks = buildWeatherChecks(weatherPayload);
    const directChecks = [];
    for (const probe of DIRECT_PROBES) {
      directChecks.push(await directProbeCheck(client, probe));
      if (typeof probe.rateLimitPauseMs === "number" && probe.rateLimitPauseMs > 0) {
        await pause(probe.rateLimitPauseMs);
      }
    }

    const weatherAuditId = weatherPayload.shield?.auditId;
    const weatherAuditPayload = typeof weatherAuditId === "string"
      ? await callToolPayload(client, "swee_shield_audit_lookup", { auditId: weatherAuditId })
      : null;
    const artifact = {
      schemaVersion: "swee-source-live-benchmark/v1",
      generatedAt,
      source: "local-live-mcp",
      command: "npm run benchmark:sources:live",
      sourceChecks: [...weatherChecks, ...directChecks],
      pulseWeather: {
        toolName: "swee_pulse_weather",
        auditId: weatherAuditId ?? weatherAuditPayload?.record?.auditId ?? null,
        decision: weatherPayload.shield?.decision ?? weatherAuditPayload?.record?.decision ?? null,
        replay: weatherAuditPayload?.replay ?? null,
        signalCount: Array.isArray(weatherPayload.signals) ? weatherPayload.signals.length : 0,
        gapCount: Array.isArray(weatherPayload.gaps) ? weatherPayload.gaps.length : 0,
      },
      limits: [
        "This artifact is live local evidence, not an SLA or official public-agency service status.",
        "A ready source check means the adapter returned a bounded response during this run; it does not certify upstream completeness.",
        "Missing upstream timestamps, empty results, and source gaps are reported directly instead of being filled with synthetic freshness.",
        "Direct discovery probes use stable sample queries: OneMap 'Raffles Place', data.gov.sg 'weather', SingStat 'population', plus bounded directory probes for hawker closures, libraries, sports facilities, parks, water levels, and community outlets.",
        "OneMap geocoding is expected to show credential_missing until SG_API_ONEMAP_EMAIL and SG_API_ONEMAP_PASSWORD, or the onemap_email/onemap_password keystore keys, are configured.",
      ],
    };
    writeArtifacts(artifact);

    const summary = {
      ok: true,
      output: outputPath,
      markdown: markdownPath,
      sourceStates: Object.fromEntries(artifact.sourceChecks.map((item) => [item.sourceTool, item.state])),
      pulseWeatherAuditId: artifact.pulseWeather.auditId,
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
  process.stderr.write("Run npm run build first. Source gaps should be written into the artifact instead of becoming invented source values.\n");
  process.exit(1);
});
