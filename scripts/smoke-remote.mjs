#!/usr/bin/env node
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";

const remoteUrl = process.env["SG_APIS_REMOTE_URL"];
const token = process.env["SG_APIS_REMOTE_TOKEN"];

if (remoteUrl === undefined || remoteUrl.trim() === "") {
  throw new Error("Set SG_APIS_REMOTE_URL to the deployed /mcp URL before running the remote smoke.");
}

const baseUrl = new URL(remoteUrl);
const metadataUrl = new URL(
  `/.well-known/oauth-protected-resource${baseUrl.pathname === "/" ? "" : baseUrl.pathname}`,
  baseUrl,
);

const metadataResponse = await fetch(metadataUrl, {
  headers: token === undefined ? {} : { Authorization: `Bearer ${token}` },
});

if (!metadataResponse.ok) {
  throw new Error(`Protected-resource metadata request failed with ${metadataResponse.status}.`);
}

const metadata = await metadataResponse.json();
if (metadata.resource !== baseUrl.href) {
  throw new Error(`Protected-resource metadata resource mismatch: expected ${baseUrl.href}, got ${metadata.resource}.`);
}

const transport = new StreamableHTTPClientTransport(baseUrl, {
  ...(token === undefined
    ? {}
    : {
        requestInit: {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        },
      }),
});

const client = new Client(
  { name: "swee-sg-remote-smoke", version: "0.1.0" },
  { capabilities: {} },
);

try {
  await client.connect(transport);

  const tools = await client.listTools();
  if (!(tools.tools ?? []).some((tool) => tool.name === "swee_pulse_snapshot")) {
    throw new Error("Remote smoke did not find swee_pulse_snapshot.");
  }

  const prompts = await client.listPrompts();
  if (!(prompts.prompts ?? []).some((prompt) => prompt.name === "recipe-pulse_overview")) {
    throw new Error("Remote smoke did not find Pulse recipe prompts.");
  }

  const resource = await client.readResource({ uri: "sg://runtime" });
  const runtimeText = resource.contents.find((content) => "text" in content && typeof content.text === "string")?.text;
  if (runtimeText === undefined) {
    throw new Error("Remote smoke could not read sg://runtime.");
  }

  process.stdout.write("remote smoke test passed\n");
} finally {
  await client.close().catch(() => undefined);
}
