import { accessSync, mkdtempSync, rmSync } from "node:fs";
import { spawn } from "node:child_process";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const root = resolve(import.meta.dirname, "..");
const serverEntry = resolve(root, "packages/mcp-server/dist/index.js");
const tempHome = mkdtempSync(join(tmpdir(), "sg-apis-demo-"));

const PROFILES = {
  business: {
    resourceUri: "sg://workflows",
    direct: {
      name: "sg_acra_entities",
      arguments: { entityName: "ABC CONSTRUCTION PTE LTD", format: "json" },
    },
    supporting: {
      name: "sg_business_dossier",
      arguments: { entityName: "ABC CONSTRUCTION PTE LTD", workhead: "CW01", format: "json" },
    },
    query: {
      name: "sg_query",
      arguments: {
        query: "Run registry diligence for company ABC CONSTRUCTION PTE LTD workhead CW01",
        mode: "execute",
        format: "json",
      },
    },
  },
  property: {
    resourceUri: "sg://workflows",
    direct: {
      name: "sg_hdb_resale_prices",
      arguments: { town: "Bedok", flatType: "4 ROOM", limit: 1, format: "json" },
    },
    supporting: {
      name: "sg_property_brief",
      arguments: {
        planningArea: "Bedok",
        flatType: "4 ROOM",
        includeEnvironment: true,
        includeTransport: true,
        format: "json",
      },
    },
    query: {
      name: "sg_query",
      arguments: {
        query: "Property due diligence for Bedok HDB resale",
        mode: "execute",
        format: "json",
      },
    },
  },
  macro: {
    resourceUri: "sg://workflows",
    direct: {
      name: "sg_mas_exchange_rates",
      arguments: { currency: "USD", format: "json" },
    },
    supporting: {
      name: "sg_macro_brief",
      arguments: { currency: "USD", format: "json" },
    },
    query: {
      name: "sg_query",
      arguments: {
        query: "Macro snapshot of Singapore",
        mode: "execute",
        format: "json",
      },
    },
  },
  transport: {
    resourceUri: "sg://workflows",
    direct: {
      name: "sg_lta_bus_arrivals",
      arguments: { busStopCode: "83139", serviceNo: "851", format: "json" },
    },
    supporting: {
      name: "sg_transport_brief",
      arguments: { busStopCode: "83139", serviceNo: "851", format: "json" },
    },
    query: {
      name: "sg_query",
      arguments: {
        query: "Transport status in Singapore right now",
        mode: "execute",
        format: "json",
      },
    },
  },
  environment: {
    resourceUri: "sg://workflows",
    direct: {
      name: "sg_nea_forecast_2hr",
      arguments: { area: "Tampines", format: "json" },
    },
    supporting: {
      name: "sg_environment_brief",
      arguments: { area: "Tampines", region: "East", format: "json" },
    },
    query: {
      name: "sg_query",
      arguments: {
        query: "Environment snapshot of Singapore right now",
        mode: "execute",
        format: "json",
      },
    },
  },
  geospatial: {
    resourceUri: "sg://recipes",
    direct: {
      name: "sg_onemap_route",
      arguments: {
        startLat: 1.2864,
        startLng: 103.8537,
        endLat: 1.284,
        endLng: 103.851,
        routeType: "walk",
      },
    },
    supporting: {
      name: "sg_onemap_reverse_geocode",
      arguments: { lat: 1.284, lng: 103.851 },
    },
    query: {
      name: "sg_query",
      arguments: {
        query: "Walk from 049178 to 048616",
        mode: "execute",
        format: "json",
      },
    },
  },
};

const profileName = process.argv[2] ?? "macro";
const profile = PROFILES[profileName];

if (profile === undefined) {
  throw new Error(`Unknown demo profile: ${profileName}`);
}

accessSync(serverEntry);

const startMockServer = async () => {
  return new Promise((resolveMock, reject) => {
    const child = spawn("npm", ["run", "mock-server"], {
      cwd: root,
      env: { ...process.env, MOCK_PORT: "0" },
      stdio: ["ignore", "ignore", "pipe"],
    });

    let stderr = "";
    const timeout = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error(`Timed out waiting for mock server startup.\n${stderr}`));
    }, 10000);

    child.stderr.on("data", (chunk) => {
      stderr += String(chunk);
      const match = stderr.match(/Mock API server running on (http:\/\/localhost:\d+)/);
      if (match !== null) {
        clearTimeout(timeout);
        resolveMock({ child, url: match[1] });
      }
    });

    child.on("exit", (code) => {
      clearTimeout(timeout);
      reject(new Error(`Mock server exited early with code ${String(code)}.\n${stderr}`));
    });
  });
};

const formatToolResult = (result) => {
  if (!("content" in result)) {
    return JSON.stringify(result, null, 2);
  }
  const text = result.content.find((item) => item.type === "text" && typeof item.text === "string")?.text;
  return text ?? JSON.stringify(result, null, 2);
};

const printSection = (title, body) => {
  process.stdout.write(`\n## ${title}\n`);
  process.stdout.write(`${body}\n`);
};

let mockServer = null;

try {
  mockServer = await startMockServer();

  const transport = new StdioClientTransport({
    command: "node",
    args: [serverEntry],
    cwd: root,
    env: {
      ...process.env,
      HOME: tempHome,
      SG_APIS_LOG_LEVEL: "error",
      MOCK_API_BASE_URL: mockServer.url,
      SG_API_URA_KEY: "test-ura-key",
      SG_API_LTA_KEY: "test-lta-key",
    },
    stderr: "pipe",
  });

  const client = new Client(
    { name: "sg-apis-demo", version: "0.1.0" },
    { capabilities: {} },
  );

  try {
    await client.connect(transport);

    const resource = await client.readResource({ uri: profile.resourceUri });
    const resourceText = resource.contents.find((content) => "text" in content && typeof content.text === "string")?.text ?? "";

    const directResult = await client.callTool(profile.direct);
    const supportingResult = await client.callTool(profile.supporting);
    const queryResult = await client.callTool(profile.query);

    printSection("Profile", profileName);
    printSection("Resource", resourceText);
    printSection(`${profile.direct.name}`, formatToolResult(directResult));
    printSection(`${profile.supporting.name}`, formatToolResult(supportingResult));
    printSection("sg_query", formatToolResult(queryResult));
  } finally {
    await client.close().catch(() => undefined);
  }
} finally {
  if (mockServer !== null) {
    mockServer.child.kill("SIGTERM");
  }
  rmSync(tempHome, { recursive: true, force: true });
}
