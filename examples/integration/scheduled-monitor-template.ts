// Scheduled monitoring integration template for Dude MCP.
// Demonstrates periodic polling of bounded operations workflows with explicit
// escalation mapping for completed, blocked, unsupported, and failed outcomes.
//
// Dry-run mode (CI friendly):
//   npx tsx examples/integration/scheduled-monitor-template.ts --dry-run
//
// Live mode (requires built server):
//   npx tsx examples/integration/scheduled-monitor-template.ts
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

type QueryOutcome = Readonly<{
  status: "planned" | "completed" | "blocked" | "unsupported" | "failed";
  workflow?: string;
  reason?: string;
  failedStep?: Readonly<{
    tool?: string;
    error?: Readonly<{
      code?: string;
      message?: string;
      retryable?: boolean;
    }>;
  }> | null;
}>;

type MonitorSignal = Readonly<{
  workflow: string;
  status: QueryOutcome["status"];
  tier: "tier0_monitor" | "tier1_notify" | "tier2_investigate";
  signalId: string;
  summary: string;
}>;

type MonitorConfig = Readonly<{
  workflow: "transport_brief" | "environment_brief";
  prompt: string;
}>;

const currentDir = dirname(fileURLToPath(import.meta.url));
const root = resolve(currentDir, "..", "..");
const serverEntry = resolve(root, "packages/mcp-server/dist/index.js");

const MONITOR_CONFIGS: readonly MonitorConfig[] = [
  { workflow: "transport_brief", prompt: "Transport status in Singapore right now" },
  { workflow: "environment_brief", prompt: "Environment snapshot of Singapore right now" },
];

const toSignal = (workflow: string, outcome: QueryOutcome): MonitorSignal => {
  if (outcome.status === "completed" || outcome.status === "planned") {
    return {
      workflow,
      status: outcome.status,
      tier: "tier0_monitor",
      signalId: `${workflow}::${outcome.status}`,
      summary: `${workflow} is healthy.`,
    };
  }

  if (outcome.status === "blocked" || outcome.status === "unsupported") {
    return {
      workflow,
      status: outcome.status,
      tier: "tier1_notify",
      signalId: `${workflow}::${outcome.status}`,
      summary: outcome.reason ?? `${workflow} needs operator input.`,
    };
  }

  const retryable = outcome.failedStep?.error?.retryable ?? false;
  return {
    workflow,
    status: "failed",
    tier: retryable ? "tier1_notify" : "tier2_investigate",
    signalId: `${workflow}::failed::${outcome.failedStep?.error?.code ?? "unknown"}`,
    summary: outcome.failedStep?.error?.message ?? outcome.reason ?? `${workflow} failed.`,
  };
};

const readOutcome = async (client: Client, prompt: string): Promise<QueryOutcome> => {
  const result = await client.callTool({
    name: "sg_query",
    arguments: {
      query: prompt,
      mode: "execute",
      format: "json",
      includeContextIds: true,
    },
  });

  if ("structuredContent" in result && result.structuredContent !== undefined) {
    return result.structuredContent as QueryOutcome;
  }

  const text = result.content.find((item) => "text" in item && typeof item.text === "string")?.text;
  if (text === undefined) {
    throw new Error("Expected text or structured content from sg_query.");
  }
  return JSON.parse(text) as QueryOutcome;
};

const runDry = () => {
  const synthetic: readonly Readonly<{ workflow: string; outcome: QueryOutcome }>[] = [
    { workflow: "transport_brief", outcome: { status: "completed", workflow: "transport_brief" } },
    {
      workflow: "environment_brief",
      outcome: {
        status: "failed",
        workflow: "environment_brief",
        failedStep: { error: { code: "UPSTREAM_TIMEOUT", message: "NEA request timed out", retryable: true } },
      },
    },
  ];

  for (const entry of synthetic) {
    const signal = toSignal(entry.workflow, entry.outcome);
    console.log(`[dry-run] ${signal.workflow} -> ${signal.tier} (${signal.signalId}) ${signal.summary}`);
  }
};

const runLive = async () => {
  const transport = new StdioClientTransport({
    command: "node",
    args: [serverEntry],
    cwd: root,
    env: {
      ...process.env,
      SG_APIS_LOG_LEVEL: "error",
    },
  });
  const client = new Client({ name: "scheduled-monitor-template", version: "0.1.0" });
  await client.connect(transport);

  try {
    for (const config of MONITOR_CONFIGS) {
      const outcome = await readOutcome(client, config.prompt);
      const signal = toSignal(config.workflow, outcome);
      console.log(`[live] ${signal.workflow} -> ${signal.tier} (${signal.signalId}) ${signal.summary}`);
    }
  } finally {
    await client.close();
  }
};

const main = async () => {
  if (process.argv.includes("--dry-run")) {
    runDry();
    return;
  }
  await runLive();
};

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
