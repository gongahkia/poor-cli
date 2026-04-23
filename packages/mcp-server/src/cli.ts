#!/usr/bin/env node
// sg-data CLI: quick lookups without full MCP setup
// usage: sg-data <command> [args]
import { createLogger, Keystore } from "@sg-apis/shared";
import type { ToolResult } from "@sg-apis/shared";
import { handleBusinessDossier, handleEnvironmentBrief, handleMacroBrief, handlePropertyBrief, handleTransportBrief } from "./tools/brief-tools.js";
import { handleHdbResalePrices } from "./tools/hdb-tools.js";
import { handleLtaBusArrivals } from "./tools/lta-tools.js";
import { handleNeaForecast2Hr } from "./tools/nea-tools.js";
import { handleVisualize, handleCrossDataset } from "./tools/visualize-tools.js";

const logger = createLogger("sg-data-cli");

const printResult = (result: ToolResult) => {
  for (const item of result.content) {
    if (item.type === "text") process.stdout.write(item.text + "\n");
  }
};

const parseArgs = (args: string[]): Record<string, string> => {
  const parsed: Record<string, string> = {};
  for (let i = 0; i < args.length; i++) {
    const arg = args[i]!;
    if (arg.startsWith("--")) {
      if (i + 1 >= args.length) {
        throw new Error(`missing value for ${arg}`);
      }
      parsed[arg.slice(2)] = args[++i]!;
    }
  }
  return parsed;
};

type CredentialEntry = { name: string; envVars: string[]; keystoreKeys: string[]; required: boolean };
const CREDENTIALS: CredentialEntry[] = [
  { name: "OneMap", envVars: ["SG_API_ONEMAP_EMAIL", "SG_API_ONEMAP_PASSWORD"], keystoreKeys: ["onemap_email", "onemap_password"], required: true },
  { name: "URA", envVars: ["SG_API_URA_KEY"], keystoreKeys: ["ura"], required: true },
  { name: "LTA DataMall", envVars: ["SG_API_LTA_KEY"], keystoreKeys: ["lta"], required: false },
];

const checkCredentialStatus = (entry: CredentialEntry, ks: Keystore): { configured: boolean; source: string } => {
  const fromEnv = entry.envVars.every((v) => process.env[v] !== undefined && process.env[v] !== "");
  const fromKs = entry.keystoreKeys.every((k) => { const v = ks.getKey(k); return v !== null && v !== ""; });
  if (fromEnv && fromKs) return { configured: true, source: "env+keystore" };
  if (fromEnv) return { configured: true, source: "env" };
  if (fromKs) return { configured: true, source: "keystore" };
  return { configured: false, source: "none" };
};

const commands: Record<string, (args: string[]) => Promise<void>> = {
  async init(args) {
    const opts = parseArgs(args);
    const ks = new Keystore();
    const hasAnyOpt = opts["lta-key"] || opts["ura-key"] || opts["onemap-email"] || opts["onemap-password"];
    if (hasAnyOpt) {
      if (opts["lta-key"]) { ks.setKey("lta", opts["lta-key"]); console.log("  stored: lta"); }
      if (opts["ura-key"]) { ks.setKey("ura", opts["ura-key"]); console.log("  stored: ura"); }
      if (opts["onemap-email"]) { ks.setKey("onemap_email", opts["onemap-email"]); console.log("  stored: onemap_email"); }
      if (opts["onemap-password"]) { ks.setKey("onemap_password", opts["onemap-password"]); console.log("  stored: onemap_password"); }
      console.log("\nrun 'sg-data doctor' to validate connectivity.");
      ks.close();
      return;
    }
    console.log("sg-data init — credential setup\n");
    for (const cred of CREDENTIALS) {
      const status = checkCredentialStatus(cred, ks);
      const icon = status.configured ? "+" : "-";
      const tag = cred.required ? "required" : "optional";
      console.log(`  [${icon}] ${cred.name} (${tag}) — ${status.configured ? `configured via ${status.source}` : "not configured"}`);
    }
    console.log("\nto set credentials:\n");
    console.log("  sg-data init --ura-key <key>");
    console.log("  sg-data init --lta-key <key>");
    console.log("  sg-data init --onemap-email <email> --onemap-password <pass>");
    console.log("\nor via environment variables:\n");
    console.log("  export SG_API_URA_KEY=<key>");
    console.log("  export SG_API_LTA_KEY=<key>");
    console.log("  export SG_API_ONEMAP_EMAIL=<email>");
    console.log("  export SG_API_ONEMAP_PASSWORD=<pass>");
    ks.close();
  },
  async doctor() {
    console.log("sg-data doctor\n");
    const nodeVersion = parseInt(process.versions.node.split(".")[0]!, 10);
    const nodeOk = nodeVersion >= 20;
    console.log(`[${nodeOk ? "+" : "!"}] node ${process.versions.node} ${nodeOk ? "" : "(>= 20 required)"}`);
    const ks = new Keystore();
    console.log("\ncredentials:");
    for (const cred of CREDENTIALS) {
      const status = checkCredentialStatus(cred, ks);
      const icon = status.configured ? "+" : (cred.required ? "!" : "-");
      console.log(`  [${icon}] ${cred.name} — ${status.configured ? status.source : "missing"}`);
    }
    console.log("\napi connectivity:");
    const { getHealthCheckTargets, checkApiHealth } = await import("./tools/health-check.js");
    const targets = getHealthCheckTargets();
    const results = await Promise.all(targets.map((t) => checkApiHealth(t, ks)));
    let allOk = true;
    for (const r of results) {
      const icon = r.reachable ? "+" : "!";
      if (!r.reachable) allOk = false;
      const latency = r.reachable ? ` (${r.latencyMs}ms)` : "";
      const err = r.error ? ` — ${r.error}` : "";
      console.log(`  [${icon}] ${r.api}${latency}${err}`);
    }
    if (!allOk) {
      console.log("\nfix suggestions:");
      for (const r of results) {
        if (r.reachable) continue;
        if (r.authRequired && r.credentialSource === "none") {
          const cred = CREDENTIALS.find((c) => c.name === r.api);
          if (cred) {
            const envHint = cred.envVars.map((v) => `export ${v}=<value>`).join(" && ");
            console.log(`  ${r.api}: ${envHint}`);
            console.log(`    or: sg-data init --${cred.keystoreKeys[0]!.replace("_", "-")}-key <value>`);
          }
        } else {
          console.log(`  ${r.api}: upstream may be down — retry later`);
        }
      }
    }
    console.log(allOk ? "\nall checks passed." : "\nsome checks failed. see suggestions above.");
    ks.close();
  },
  async health() {
    const { getHealthCheckTargets } = await import("./tools/health-check.js");
    const targets = getHealthCheckTargets();
    console.log(`health check targets: ${targets.length}`);
    for (const t of targets) console.log(`  ${t.api}: ${t.url} (auth: ${t.authRequired})`);
  },
  async query(args) {
    const text = args.join(" ");
    if (!text) { console.error("usage: sg-data query <prompt>"); process.exit(1); }
    const { executeQueryStep } = await import("./tools/query-tool.js");
    const { planQuery } = await import("./router/planner.js");
    const plan = planQuery(text);
    if (!plan.supported) { console.error(`unsupported: ${plan.reason}\n${plan.suggestion}`); process.exit(1); }
    const results = new Map<string, { input: Readonly<Record<string, unknown>>; output: ToolResult }>();
    for (const step of plan.steps) {
      const context = { results };
      const resolvedInput = step.resolveInput !== undefined ? await step.resolveInput(context) : step.input;
      const result = await executeQueryStep(step.tool, resolvedInput);
      results.set(step.id, { input: resolvedInput, output: result });
      printResult(result);
    }
  },
  async forecast(args) {
    const opts = parseArgs(args);
    printResult(await handleNeaForecast2Hr({ area: opts["area"], date: opts["date"] }));
  },
  async "bus-arrivals"(args) {
    const opts = parseArgs(args);
    if (!opts["stop"]) { console.error("usage: sg-data bus-arrivals --stop <code>"); process.exit(1); }
    printResult(await handleLtaBusArrivals({ busStopCode: opts["stop"], serviceNo: opts["service"] }));
  },
  async "hdb-resale"(args) {
    const opts = parseArgs(args);
    printResult(await handleHdbResalePrices({ town: opts["town"], flatType: opts["flatType"], limit: opts["limit"] ? Number(opts["limit"]) : undefined }));
  },
  async "property-brief"(args) {
    const opts = parseArgs(args);
    printResult(await handlePropertyBrief({ planningArea: opts["area"], postalCode: opts["postal"], format: "markdown" }));
  },
  async "business-dossier"(args) {
    const opts = parseArgs(args);
    printResult(await handleBusinessDossier({ entityName: opts["name"], uen: opts["uen"], format: "markdown" }));
  },
  async "macro-brief"(args) {
    const opts = parseArgs(args);
    printResult(await handleMacroBrief({ currency: opts["currency"], format: "markdown" }));
  },
  async "transport-brief"(args) {
    const opts = parseArgs(args);
    printResult(await handleTransportBrief({ busStopCode: opts["stop"], format: "markdown" }));
  },
  async "environment-brief"(args) {
    const opts = parseArgs(args);
    printResult(await handleEnvironmentBrief({ area: opts["area"], region: opts["region"], format: "markdown" }));
  },
  async visualize(args) {
    const opts = parseArgs(args);
    if (opts["values"] !== undefined) {
      const values = opts["values"].split(",").map((v) => Number(v.trim())).filter((v) => Number.isFinite(v));
      if (values.length < 2) { console.error("usage: sg-data visualize --values 1,2,3,4"); process.exit(1); }
      printResult(await handleVisualize({ values, format: "markdown" }));
      return;
    }
    if (opts["tableId"] !== undefined && opts["indicator"] !== undefined) {
      printResult(await handleVisualize({
        tableId: opts["tableId"],
        indicator: opts["indicator"],
        ...(opts["startYear"] ? { startYear: Number(opts["startYear"]) } : {}),
        ...(opts["endYear"] ? { endYear: Number(opts["endYear"]) } : {}),
        format: "markdown",
      }));
      return;
    }
    console.error("usage: sg-data visualize --values 1,2,3  OR  --tableId M015631 --indicator 'GDP At Current Market Prices'");
    process.exit(1);
  },
  async "cross-dataset"(args) {
    const opts = parseArgs(args);
    const required = ["leftTableId", "leftIndicator", "leftLabel", "rightTableId", "rightIndicator", "rightLabel"] as const;
    for (const key of required) {
      if (!opts[key]) { console.error(`missing required --${key}`); process.exit(1); }
    }
    printResult(await handleCrossDataset({
      leftTableId: opts["leftTableId"]!,
      leftIndicator: opts["leftIndicator"]!,
      leftLabel: opts["leftLabel"]!,
      rightTableId: opts["rightTableId"]!,
      rightIndicator: opts["rightIndicator"]!,
      rightLabel: opts["rightLabel"]!,
      ...(opts["startYear"] ? { startYear: Number(opts["startYear"]) } : {}),
      ...(opts["endYear"] ? { endYear: Number(opts["endYear"]) } : {}),
      format: "markdown",
    }));
  },
};

const main = async () => {
  const [cmd, ...args] = process.argv.slice(2);
  if (!cmd || cmd === "help" || cmd === "--help") {
    console.log(`sg-data - Singapore public data CLI

commands:
  init                        configure API credentials
  doctor                      diagnose setup and connectivity
  query <prompt>              natural-language query
  health                      check API health
  forecast --area <area>      2-hour weather forecast
  bus-arrivals --stop <code>  bus arrival timings
  hdb-resale --town <town>    HDB resale prices
  property-brief --area <a>   property brief
  business-dossier --uen <u>  business dossier
  macro-brief                 macro snapshot
  transport-brief             transport status
  environment-brief           environment status
  visualize --values 1,2,3    ASCII sparkline from inline values or --tableId+--indicator
  cross-dataset               compare two SingStat series by period (Pearson correlation)`);
    process.exit(0);
  }
  const handler = commands[cmd];
  if (!handler) { console.error(`unknown command: ${cmd}. run 'sg-data help'`); process.exit(1); }
  logger.info("command start", { command: cmd, args });
  await handler(args);
  logger.info("command finished", { command: cmd });
};

main().catch((err) => {
  logger.error("command failed", {
    error: err instanceof Error ? err.message : String(err),
    ...(err instanceof Error && err.stack !== undefined ? { stack: err.stack } : {}),
  });
  console.error(err instanceof Error ? err.message : String(err));
  process.exit(1);
});
