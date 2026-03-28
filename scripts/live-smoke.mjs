import { accessSync } from "node:fs";
import { resolve } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const root = resolve(import.meta.dirname, "..");
const serverEntry = resolve(root, "packages/mcp-server/dist/index.js");

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

const getRecordArray = (payload, key = "records") => {
  const records = payload?.[key];
  if (!Array.isArray(records)) {
    throw new Error(`Expected ${key} to be an array.`);
  }
  return records;
};

const getHealthRecord = (records, api) => {
  const record = records.find((candidate) => candidate?.api === api);
  if (record === undefined) {
    throw new Error(`sg_health_check did not return a record for ${api}.`);
  }
  return record;
};

const ensureLiveHealth = (record) => {
  if (record.configured !== true) {
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

    process.stdout.write("Checking authenticated upstreams via sg_health_check...\n");
    const healthPayload = await callToolPayload(client, "sg_health_check", {});
    const healthRecords = getRecordArray(healthPayload);

    for (const api of ["OneMap", "URA", "LTA"]) {
      const record = getHealthRecord(healthRecords, api);
      ensureLiveHealth(record);
      process.stdout.write(`- ${api}: ok\n`);
    }

    process.stdout.write("Running live MCP smoke flow...\n");

    const onemapPayload = await callToolPayload(client, "sg_onemap_geocode", {
      searchVal: "049178",
      limit: 1,
    });
    ensureNonEmpty("sg_onemap_geocode", getRecordArray(onemapPayload));
    process.stdout.write("- OneMap geocode: ok\n");

    const uraPayload = await callToolPayload(client, "sg_ura_dev_charges", {});
    ensureNonEmpty("sg_ura_dev_charges", getRecordArray(uraPayload));
    process.stdout.write("- URA development charges: ok\n");

    const ltaPayload = await callToolPayload(client, "sg_lta_bus_arrivals", {
      busStopCode: "83139",
      format: "json",
    });
    ensureNonEmpty("sg_lta_bus_arrivals", getRecordArray(ltaPayload));
    process.stdout.write("- LTA bus arrivals: ok\n");

    const datastorePayload = await callToolPayload(client, "sg_hdb_resale_prices", {
      town: "Bedok",
      flatType: "4 ROOM",
      limit: 1,
      format: "json",
    });
    ensureNonEmpty("sg_hdb_resale_prices", getRecordArray(datastorePayload));
    process.stdout.write("- data.gov datastore family (HDB): ok\n");

    const fileDownloadPayload = await callToolPayload(client, "sg_boa_architecture_firms", {
      firmName: "DP Architects",
      limit: 1,
      format: "json",
    });
    ensureNonEmpty("sg_boa_architecture_firms", getRecordArray(fileDownloadPayload));
    process.stdout.write("- official file-download family (BOA): ok\n");

    process.stdout.write("live smoke test passed\n");
  } catch (error) {
    throw new Error(`${error instanceof Error ? error.message : String(error)}${serverLogs()}`);
  } finally {
    await client.close().catch(() => undefined);
  }
};

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.stderr.write("See docs/api-auth-guide.md for credential setup and live health-check behavior.\n");
  process.exit(1);
});
