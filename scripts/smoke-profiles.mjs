import { accessSync } from "node:fs";
import { resolve } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const root = resolve(import.meta.dirname, "..");
const serverEntry = resolve(root, "packages/mcp-server/dist/index.js");

const EXPECTATIONS = [
  {
    profile: "public",
    includes: ["swee_pulse_snapshot", "swee_pulse_explain", "sg_acra_entities"],
    excludes: ["swee_shield_audit_lookup", "swee_shield_policy_simulate", "swee_shield_splunk_investigation_pack", "sg_key_set", "sg_cache_clear"],
  },
  {
    profile: "cdd_report",
    includes: ["swee_pulse_snapshot", "swee_pulse_explain", "sg_acra_entities"],
    excludes: ["sg_query", "sg_business_dossier", "sg_cache_clear"],
  },
  {
    profile: "diligence",
    includes: ["swee_pulse_snapshot", "sg_acra_entities", "sg_gebiz_tenders"],
    excludes: ["sg_query", "sg_business_dossier", "sg_cache_clear"],
  },
  {
    profile: "ops",
    includes: ["swee_shield_audit_lookup", "swee_shield_policy_simulate", "swee_shield_splunk_investigation_pack", "sg_cache_stats", "sg_key_set", "sg_config_set"],
    excludes: ["swee_pulse_snapshot", "sg_query", "sg_business_dossier"],
  },
];

const assert = (condition, message) => {
  if (!condition) {
    throw new Error(message);
  }
};

const listToolNamesForProfile = async (profile) => {
  const transport = new StdioClientTransport({
    command: "node",
    args: [serverEntry],
    cwd: root,
    env: {
      ...process.env,
      SG_APIS_LOG_LEVEL: process.env["SG_APIS_LOG_LEVEL"] ?? "error",
      SG_APIS_TOOL_PROFILE: profile,
    },
    stderr: "pipe",
  });

  const stderrChunks = [];
  transport.stderr?.on("data", (chunk) => {
    stderrChunks.push(String(chunk));
  });

  const client = new Client(
    { name: "swee-sg-profile-smoke", version: "0.1.0" },
    { capabilities: {} },
  );

  try {
    await client.connect(transport);
    const tools = await client.listTools();
    return {
      names: new Set((tools.tools ?? []).map((tool) => tool.name)),
      logs: stderrChunks.join(""),
    };
  } finally {
    await client.close().catch(() => undefined);
  }
};

const main = async () => {
  accessSync(serverEntry);

  for (const expectation of EXPECTATIONS) {
    const { names, logs } = await listToolNamesForProfile(expectation.profile);

    for (const tool of expectation.includes) {
      assert(
        names.has(tool),
        `Profile ${expectation.profile} is missing expected tool ${tool}.${logs ? `\nServer stderr:\n${logs}` : ""}`,
      );
    }
    for (const tool of expectation.excludes) {
      assert(
        !names.has(tool),
        `Profile ${expectation.profile} unexpectedly exposed ${tool}.${logs ? `\nServer stderr:\n${logs}` : ""}`,
      );
    }
    process.stdout.write(`- ${expectation.profile}: ok\n`);
  }

  process.stdout.write("tool profile smoke test passed\n");
};

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exit(1);
});
