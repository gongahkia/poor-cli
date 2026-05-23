// Backend worker integration template for Swee SG.
// Run after `npm run build`:
//   npx tsx examples/integration/backend-worker-template.ts
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

type TextContent = Readonly<{ text?: string }>;
type ResourceTextContent = Readonly<{ text?: string }>;

type PulseSignal = Readonly<{
  severity: "info" | "watch" | "disrupted";
  title: string;
  sourceTool: string;
}>;

type PulseSnapshot = Readonly<{
  signals: readonly PulseSignal[];
  sourceHealth: readonly Readonly<{ sourceTool: string; status: "ready" | "stale" | "gap" }>[];
  gaps: readonly Readonly<{ code: string; message?: string }>[];
}>;

type PulseToolPayload = Readonly<{ snapshot: PulseSnapshot }>;

type WorkerJob = Readonly<{
  id: string;
  focus: "all" | "mobility" | "weather";
  area?: string;
}>;

type WorkerDecision =
  | Readonly<{ kind: "escalate"; reason: string }>
  | Readonly<{ kind: "monitor"; reason: string }>
  | Readonly<{ kind: "source_gap"; reason: string; retryAfterSec: number }>
  | Readonly<{ kind: "complete"; reason: string }>;

const currentDir = dirname(fileURLToPath(import.meta.url));
const root = resolve(currentDir, "..", "..");
const serverEntry = resolve(root, "packages/mcp-server/dist/index.js");

const getText = (items: readonly TextContent[] | readonly ResourceTextContent[]): string => {
  const text = items.find((item) => typeof item.text === "string")?.text;
  if (text === undefined) {
    throw new Error("Expected text content from MCP response.");
  }
  return text;
};

const readJsonResource = async <T>(client: Client, uri: string): Promise<T> => {
  const resource = await client.readResource({ uri });
  return JSON.parse(getText(resource.contents as readonly ResourceTextContent[])) as T;
};

const callPulseSnapshot = async (client: Client, job: WorkerJob): Promise<PulseToolPayload> => {
  const result = await client.callTool({
    name: "swee_pulse_snapshot",
    arguments: {
      focus: job.focus,
      ...(job.area === undefined ? {} : { area: job.area }),
    },
  });

  if ("structuredContent" in result && result.structuredContent !== undefined) {
    return result.structuredContent as PulseToolPayload;
  }
  return JSON.parse(getText(result.content as readonly TextContent[])) as PulseToolPayload;
};

const decideWorkerAction = (payload: PulseToolPayload): WorkerDecision => {
  const disrupted = payload.snapshot.signals.find((signal) => signal.severity === "disrupted");
  if (disrupted !== undefined) {
    return { kind: "escalate", reason: `${disrupted.title} from ${disrupted.sourceTool}` };
  }

  const watch = payload.snapshot.signals.find((signal) => signal.severity === "watch");
  if (watch !== undefined) {
    return { kind: "monitor", reason: `${watch.title} from ${watch.sourceTool}` };
  }

  if (payload.snapshot.gaps.length > 0 || payload.snapshot.sourceHealth.some((source) => source.status === "gap")) {
    return { kind: "source_gap", reason: "Pulse source gaps need review.", retryAfterSec: 300 };
  }

  return { kind: "complete", reason: "No watch-level Pulse signals." };
};

const main = async () => {
  const transport = new StdioClientTransport({
    command: "node",
    args: [serverEntry],
    cwd: root,
    env: {
      ...process.env,
      SG_APIS_LOG_LEVEL: "error",
    },
  });
  const client = new Client({ name: "swee-backend-worker-template", version: "0.1.0" });
  await client.connect(transport);

  try {
    const runtime = await readJsonResource<Record<string, unknown>>(client, "sg://runtime");
    console.log(`runtime: ${String(runtime.schemaVersion ?? "unknown")}`);

    const jobs: readonly WorkerJob[] = [
      { id: "job-1", focus: "all", area: "Bedok" },
      { id: "job-2", focus: "weather", area: "Ang Mo Kio" },
      { id: "job-3", focus: "mobility" },
    ];

    for (const job of jobs) {
      const payload = await callPulseSnapshot(client, job);
      const decision = decideWorkerAction(payload);
      console.log(`${job.id}: ${decision.kind} - ${decision.reason}`);
      if (decision.kind === "source_gap") {
        console.log(`  retry in: ${decision.retryAfterSec}s`);
      }
    }
  } finally {
    await client.close();
  }
};

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
