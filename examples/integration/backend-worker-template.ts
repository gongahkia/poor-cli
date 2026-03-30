// Backend worker integration template for sg-apis-mcp.
// Demonstrates explicit handling for blocked / unsupported / failed outcomes.
//
// Run after `npm run build`:
//   npx tsx examples/integration/backend-worker-template.ts
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

type TextContent = Readonly<{
  type?: string;
  text?: string;
}>;

type ResourceTextContent = Readonly<{
  text?: string;
}>;

type QueryBlocker = Readonly<{
  field: string;
  directTool: string;
  suggestedPrompt: string;
}>;

type QueryFailedStep = Readonly<{
  id?: string;
  tool?: string;
  status?: "completed" | "failed";
  error?: Readonly<{
    code?: string;
    message?: string;
    retryable?: boolean;
    suggestedAction?: string;
  }>;
}>;

type QueryOutcome = Readonly<{
  status: "planned" | "completed" | "blocked" | "unsupported" | "failed";
  workflow?: string;
  reason?: string;
  suggestion?: string;
  blockers?: readonly QueryBlocker[];
  failedStep?: QueryFailedStep | null;
  steps?: readonly QueryFailedStep[];
}>;

type OpsTaxonomy = Readonly<{
  errorCodes?: readonly Readonly<{
    code: string;
    retryable: boolean;
    severity: "low" | "medium" | "high";
    suggestedAction?: string;
  }>[];
}>;

type WorkerJob = Readonly<{
  id: string;
  prompt: string;
}>;

type WorkerDecision =
  | Readonly<{ kind: "completed"; summary: string; workflow?: string }>
  | Readonly<{ kind: "needs_input"; reason: string; blockers: readonly QueryBlocker[] }>
  | Readonly<{ kind: "fallback_discovery"; reason: string; suggestion?: string }>
  | Readonly<{ kind: "retryable_failure"; reason: string; retryAfterSec: number }>
  | Readonly<{ kind: "terminal_failure"; reason: string }>;

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

const callQuery = async (client: Client, prompt: string): Promise<QueryOutcome> => {
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
  return JSON.parse(getText(result.content as readonly TextContent[])) as QueryOutcome;
};

const lookupRetryability = (
  opsTaxonomy: OpsTaxonomy,
  errorCode: string | undefined,
): boolean | undefined => {
  if (errorCode === undefined || !Array.isArray(opsTaxonomy.errorCodes)) {
    return undefined;
  }
  const match = opsTaxonomy.errorCodes.find((entry) => entry.code === errorCode);
  return match?.retryable;
};

const decideWorkerAction = (
  outcome: QueryOutcome,
  opsTaxonomy: OpsTaxonomy,
): WorkerDecision => {
  if (outcome.status === "completed") {
    return {
      kind: "completed",
      summary: `workflow completed${outcome.workflow === undefined ? "" : `: ${outcome.workflow}`}`,
      ...(outcome.workflow === undefined ? {} : { workflow: outcome.workflow }),
    };
  }

  if (outcome.status === "blocked") {
    const blockers = Array.isArray(outcome.blockers) ? outcome.blockers : [];
    return {
      kind: "needs_input",
      reason: outcome.reason ?? "Workflow recognized but required fields are missing.",
      blockers,
    };
  }

  if (outcome.status === "unsupported") {
    return {
      kind: "fallback_discovery",
      reason: outcome.reason ?? "Prompt not covered by a bounded workflow.",
      ...(outcome.suggestion === undefined ? {} : { suggestion: outcome.suggestion }),
    };
  }

  if (outcome.status === "failed") {
    const failedStep = outcome.failedStep ?? null;
    const failureCode = failedStep?.error?.code;
    const retryable = failedStep?.error?.retryable ?? lookupRetryability(opsTaxonomy, failureCode) ?? false;
    const reason = failedStep?.error?.message ?? outcome.reason ?? "Workflow execution failed.";

    if (retryable) {
      return {
        kind: "retryable_failure",
        reason,
        retryAfterSec: 30,
      };
    }

    return {
      kind: "terminal_failure",
      reason,
    };
  }

  return {
    kind: "terminal_failure",
    reason: `Unhandled sg_query status: ${outcome.status}`,
  };
};

const runJob = async (client: Client, job: WorkerJob, opsTaxonomy: OpsTaxonomy): Promise<WorkerDecision> => {
  const outcome = await callQuery(client, job.prompt);
  return decideWorkerAction(outcome, opsTaxonomy);
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
  const client = new Client({ name: "backend-worker-template", version: "0.1.0" });
  await client.connect(transport);

  try {
    const opsTaxonomy = await readJsonResource<OpsTaxonomy>(client, "sg://ops-taxonomy");
    const jobs: readonly WorkerJob[] = [
      { id: "job-1", prompt: "Architecture firm diligence for DP Architects" },
      { id: "job-2", prompt: "Find a social service office near me" },
      { id: "job-3", prompt: "Compare GDP and CPI in Singapore" },
      { id: "job-4", prompt: "Find datasets about a definitely unknown topic" },
    ];

    for (const job of jobs) {
      const decision = await runJob(client, job, opsTaxonomy);
      console.log(`${job.id}: ${decision.kind} - ${decision.reason}`);
      if (decision.kind === "needs_input" && decision.blockers.length > 0) {
        const first = decision.blockers[0];
        console.log(`  blocker: ${first.field} -> ${first.directTool}`);
        console.log(`  suggested prompt: ${first.suggestedPrompt}`);
      }
      if (decision.kind === "fallback_discovery" && decision.suggestion !== undefined) {
        console.log(`  suggestion: ${decision.suggestion}`);
      }
      if (decision.kind === "retryable_failure") {
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
