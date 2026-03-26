#!/usr/bin/env node
// sg-data CLI: quick lookups without full MCP setup
// usage: sg-data <command> [args]
import { handleBusinessDossier, handleEnvironmentBrief, handleMacroBrief, handlePropertyBrief, handleTransportBrief } from "./tools/brief-tools.js";
import { handleHdbResalePrices } from "./tools/hdb-tools.js";
import { handleLtaBusArrivals } from "./tools/lta-tools.js";
import { handleNeaForecast2Hr } from "./tools/nea-tools.js";

const printResult = (result: { content: readonly { type: string; text: string }[] }) => {
  for (const item of result.content) {
    if (item.type === "text") process.stdout.write(item.text + "\n");
  }
};

const parseArgs = (args: string[]): Record<string, string> => {
  const parsed: Record<string, string> = {};
  for (let i = 0; i < args.length; i++) {
    const arg = args[i]!;
    if (arg.startsWith("--") && i + 1 < args.length) {
      parsed[arg.slice(2)] = args[++i]!;
    }
  }
  return parsed;
};

const commands: Record<string, (args: string[]) => Promise<void>> = {
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
    type ToolResult = { content: readonly { type: string; text: string }[]; isError?: boolean; structuredContent?: Readonly<Record<string, unknown>> };
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
};

const main = async () => {
  const [cmd, ...args] = process.argv.slice(2);
  if (!cmd || cmd === "help" || cmd === "--help") {
    console.log(`sg-data - Singapore public data CLI

commands:
  query <prompt>              natural-language query
  health                      check API health
  forecast --area <area>      2-hour weather forecast
  bus-arrivals --stop <code>  bus arrival timings
  hdb-resale --town <town>    HDB resale prices
  property-brief --area <a>   property brief
  business-dossier --uen <u>  business dossier
  macro-brief                 macro snapshot
  transport-brief             transport status
  environment-brief           environment status`);
    process.exit(0);
  }
  const handler = commands[cmd];
  if (!handler) { console.error(`unknown command: ${cmd}. run 'sg-data help'`); process.exit(1); }
  await handler(args);
};

main().catch((err) => { console.error(err.message); process.exit(1); });
