import { createServer, request, type IncomingMessage, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { exportJWK, generateKeyPair, SignJWT } from "jose";
import { afterEach, describe, expect, it, vi } from "vitest";
import { derivePublicHttpToolsets, HttpAuthController, type HttpAuthMode } from "../http-auth.js";
import { startHttpServer } from "../http-server.js";
import { createServerInstance } from "../server-factory.js";
import { NORMALIZED_PLAYBOOK_CATALOG, NORMALIZED_RECIPE_CATALOG } from "../tools/catalog-surface.js";

vi.mock("../apis/datagov/client.js", () => ({
  searchDatasets: vi.fn(async () => []),
  getDataset: vi.fn(async () => null),
  getDatasetResources: vi.fn(async () => null),
  getDatasetRows: vi.fn(async () => ({
    datasetId: "d_mock_dataset",
    datasetName: "Mock Dataset",
    resourceId: "r_mock_rows",
    total: 75,
    offset: 0,
    limit: 75,
    fields: ["id", "name"],
    records: Array.from({ length: 75 }, (_, index) => ({
      id: index + 1,
      name: `Row ${index + 1}`,
    })),
  })),
  listCollections: vi.fn(async () => []),
}));

vi.mock("../apis/onemap/client.js", () => ({
  geocode: vi.fn(async () => [{
    address: "1 Raffles Place, Singapore 048616",
    building: "1 Raffles Place",
    postal: "048616",
    lat: 1.284,
    lng: 103.851,
    x: 28001,
    y: 38744,
  }]),
  reverseGeocode: vi.fn(async () => ({
    building: "1 Raffles Place",
    address: "1 Raffles Place, Singapore 048616",
    postal: "048616",
    lat: 1.284,
    lng: 103.851,
  })),
  getRoute: vi.fn(async () => ({
    totalDistance: 1200,
    totalTime: 600,
    routeName: "Mock Route",
    instructions: [
      { instruction: "Head north", road: "Mock Street", distance: 600 },
      { instruction: "Arrive at destination", road: "Mock Avenue", distance: 600 },
    ],
  })),
  getPopulationData: vi.fn(async () => ({
    planningArea: "Downtown Core",
    year: "2024",
    data: [],
  })),
  convertSVY21toWGS84: vi.fn(async () => ({ lat: 1.284, lng: 103.851 })),
  convertWGS84toSVY21: vi.fn(async () => ({ x: 28001, y: 38744 })),
}));

type ConnectedClient = {
  readonly client: Client;
  readonly close: () => Promise<void>;
};

type TestIssuer = {
  readonly issuerUrl: URL;
  readonly audience: string;
  readonly signToken: (scopes?: readonly string[]) => Promise<string>;
  readonly close: () => Promise<void>;
};

const createdClosers: Array<() => Promise<void>> = [];
const quietLogger = {
  debug: () => undefined,
  info: () => undefined,
  warn: () => undefined,
  error: () => undefined,
  child: () => quietLogger,
};
const ALL_HTTP_TOOLSETS = new Set(["public", "briefs", "query", "health", "ops", "diligence"] as const);

afterEach(async () => {
  while (createdClosers.length > 0) {
    const close = createdClosers.pop();
    await close?.();
  }
});

const createConnectedInMemoryClient = async (): Promise<ConnectedClient> => {
  const instance = createServerInstance();
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await instance.server.connect(serverTransport);

  const client = new Client(
    { name: "sg-apis-test-client", version: "1.0.0" },
    { capabilities: {} },
  );

  await client.connect(clientTransport);

  const close = async () => {
    await client.close().catch(() => undefined);
    await instance.close();
  };
  createdClosers.push(close);

  return { client, close };
};

const createOidcIssuer = async (): Promise<TestIssuer> => {
  const { publicKey, privateKey } = await generateKeyPair("RS256");
  const jwk = await exportJWK(publicKey);
  const keyId = "test-key";

  const issuerServer = createServer((req: IncomingMessage, res: ServerResponse) => {
    const address = issuerServer.address() as AddressInfo;
    const issuerUrl = `http://127.0.0.1:${address.port}`;

    if (req.url === "/.well-known/openid-configuration" || req.url === "/.well-known/oauth-authorization-server") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({
        issuer: issuerUrl,
        jwks_uri: `${issuerUrl}/jwks`,
      }));
      return;
    }

    if (req.url === "/jwks") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({
        keys: [{ ...jwk, kid: keyId, alg: "RS256", use: "sig" }],
      }));
      return;
    }

    res.writeHead(404).end();
  });

  await new Promise<void>((resolve, reject) => {
    issuerServer.once("error", reject);
    issuerServer.listen(0, "127.0.0.1", () => {
      issuerServer.off("error", reject);
      resolve();
    });
  });

  const issuerAddress = issuerServer.address() as AddressInfo;
  const issuerUrl = new URL(`http://127.0.0.1:${issuerAddress.port}`);
  const audience = "sg-apis-test";

  const close = async () => {
    await new Promise<void>((resolve, reject) => {
      issuerServer.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve();
      });
    });
  };

  return {
    issuerUrl,
    audience,
    signToken: async (scopes = []) => {
      return new SignJWT({
        scope: scopes.join(" "),
      })
        .setProtectedHeader({ alg: "RS256", kid: keyId })
        .setIssuer(issuerUrl.href)
        .setAudience(audience)
        .setSubject("test-user")
        .setIssuedAt()
        .setExpirationTime("2h")
        .sign(privateKey);
    },
    close,
  };
};

const startAuthedHttpServer = async (options: {
  readonly mode: HttpAuthMode;
  readonly requiredScopes?: readonly string[];
}) => {
  const issuer = options.mode === "none" ? null : await createOidcIssuer();
  const auth = new HttpAuthController({
    mode: options.mode,
    ...(issuer === null ? {} : { issuer: issuer.issuerUrl.href, audience: issuer.audience }),
    requiredScopes: options.requiredScopes ?? [],
    clockSkewSec: 60,
    resourceServerUrl: new URL("http://127.0.0.1:0/mcp"),
    fullToolsets: ALL_HTTP_TOOLSETS,
    publicToolsets: derivePublicHttpToolsets(ALL_HTTP_TOOLSETS),
    logger: quietLogger,
  });

  const httpServer = await startHttpServer({
    host: "127.0.0.1",
    port: 0,
    auth,
    useBoundResourceServerUrl: true,
    logger: quietLogger,
  });

  const close = async () => {
    await httpServer.close();
    await issuer?.close().catch(() => undefined);
  };
  createdClosers.push(close);

  return { httpServer, auth, issuer };
};

const createConnectedHttpClient = async (options?: {
  readonly mode?: HttpAuthMode;
  readonly token?: string;
  readonly requiredScopes?: readonly string[];
  readonly tokenFactory?: (issuer: TestIssuer | null) => Promise<string | undefined>;
}): Promise<ConnectedClient & {
  readonly auth: HttpAuthController;
  readonly issuer: TestIssuer | null;
  readonly baseUrl: URL;
}> => {
  const { httpServer, auth, issuer } = await startAuthedHttpServer({
    mode: options?.mode ?? "none",
    ...(options?.requiredScopes === undefined ? {} : { requiredScopes: options.requiredScopes }),
  });

  const address = httpServer.server.address() as AddressInfo;
  const baseUrl = new URL(`http://127.0.0.1:${address.port}/mcp`);
  const token = options?.token ?? await options?.tokenFactory?.(issuer) ?? undefined;
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
    { name: "sg-apis-http-test-client", version: "1.0.0" },
    { capabilities: {} },
  );

  await client.connect(transport as Parameters<typeof client.connect>[0]);

  const close = async () => {
    await transport.terminateSession().catch(() => undefined);
    await client.close().catch(() => undefined);
  };
  createdClosers.push(close);

  return { client, close, auth, issuer, baseUrl };
};

describe("MCP surface", () => {
  it("lists tools with titles, annotations, and output schemas", async () => {
    const { client } = await createConnectedInMemoryClient();
    const result = await client.listTools();

    const pulseTool = result.tools.find((tool) => tool.name === "swee_pulse_snapshot");
    expect(pulseTool).toMatchObject({
      name: "swee_pulse_snapshot",
      title: "Pulse Snapshot",
      annotations: expect.objectContaining({
        readOnlyHint: true,
        openWorldHint: true,
      }),
    });
    expect(pulseTool?.outputSchema).toBeDefined();

    const destructiveTool = result.tools.find((tool) => tool.name === "sg_cache_clear");
    expect(destructiveTool).toMatchObject({
      annotations: expect.objectContaining({
        destructiveHint: true,
        readOnlyHint: false,
      }),
    });
  });

  it("lists prompts, prompt args, and completions for recipe and playbook entries", async () => {
    const { client } = await createConnectedInMemoryClient();
    const prompts = await client.listPrompts();
    const promptNames = new Set(prompts.prompts.map((prompt) => prompt.name));

    expect(prompts.prompts).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          name: "recipe-pulse_overview",
          arguments: expect.arrayContaining([
            expect.objectContaining({ name: "focus", required: false }),
            expect.objectContaining({ name: "area", required: false }),
          ]),
        }),
        expect.objectContaining({
          name: "playbook-city_ops",
          arguments: expect.arrayContaining([
            expect.objectContaining({ name: "focus", required: false }),
          ]),
        }),
      ]),
    );
    expect(promptNames.size).toBe(NORMALIZED_RECIPE_CATALOG.length + NORMALIZED_PLAYBOOK_CATALOG.length);
    for (const recipe of NORMALIZED_RECIPE_CATALOG) {
      expect(promptNames.has(`recipe-${recipe.id}`)).toBe(true);
    }
    for (const playbook of NORMALIZED_PLAYBOOK_CATALOG) {
      expect(promptNames.has(`playbook-${playbook.id}`)).toBe(true);
    }

    const recipePrompt = await client.getPrompt({
      name: "recipe-pulse_overview",
      arguments: {
        area: "Bedok",
        focus: "weather",
      },
    });
    expect(JSON.stringify(recipePrompt.messages)).toContain("Swee Pulse weather snapshot");

    const completion = await client.complete({
      ref: { type: "ref/prompt", name: "playbook-city_ops" },
      argument: { name: "focus", value: "w" },
    });
    expect(completion.completion.values).toContain("weather");
  });

  it("lists root resources, templates, artifacts, and the UI resource", async () => {
    const { client } = await createConnectedInMemoryClient();
    const resources = await client.listResources();
    const templates = await client.listResourceTemplates();

    expect(resources.resources).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          uri: "sg://tools",
          title: "Tool Catalog",
          mimeType: "application/json",
          annotations: expect.objectContaining({ priority: 0.9 }),
        }),
        expect.objectContaining({
          uri: "ui://sg/map-preview",
          mimeType: "text/html;profile=mcp-app",
        }),
      ]),
    );

    expect(templates.resourceTemplates).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ uriTemplate: "sg://apis/{name}" }),
        expect.objectContaining({ uriTemplate: "sg://tools/{name}" }),
        expect.objectContaining({ uriTemplate: "sg://workflows/{id}" }),
        expect.objectContaining({ uriTemplate: "sg://recipes/{id}" }),
        expect.objectContaining({ uriTemplate: "sg://artifacts/{kind}/{id}" }),
      ]),
    );
  });

  it("retains source adapters while excluding removed CDD tools", async () => {
    const { client } = await createConnectedInMemoryClient();
    const tools = await client.listTools();
    const names = tools.tools.map((tool) => tool.name);

    expect(names).toEqual(expect.arrayContaining(["sg_datagov_rows", "sg_onemap_geocode", "swee_pulse_snapshot"]));
    expect(names).not.toEqual(
      expect.arrayContaining(["sg_query", "sg_business_dossier", "sg_cdd_report", "sg_resolve_counterparty"]),
    );
  });

  it("serves the filtered mixed HTTP surface for unauthenticated sessions", async () => {
    const { client } = await createConnectedHttpClient({ mode: "mixed" });
    const tools = await client.listTools();

    expect(tools.tools.find((tool) => tool.name === "sg_key_set")).toBeUndefined();
    expect(tools.tools.find((tool) => tool.name === "swee_pulse_snapshot")).toBeDefined();
  }, 20_000);

  it("serves the full mixed HTTP surface for authenticated sessions", async () => {
    const { client } = await createConnectedHttpClient({
      mode: "mixed",
      tokenFactory: async (issuer) => issuer?.signToken(),
    });
    const tools = await client.listTools();

    expect(tools.tools.find((tool) => tool.name === "sg_key_set")).toBeDefined();
  }, 20_000);

  it("rejects all-mode initialization without a valid token", async () => {
    const { httpServer, auth } = await startAuthedHttpServer({ mode: "all" });
    const address = httpServer.server.address() as AddressInfo;
    const response = await fetch(`http://127.0.0.1:${address.port}/mcp`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        method: "initialize",
        params: {
          protocolVersion: "2025-03-26",
          capabilities: {},
          clientInfo: {
            name: "unauthorized-test",
            version: "1.0.0",
          },
        },
      }),
    });

    expect(response.status).toBe(401);
    expect(response.headers.get("www-authenticate")).toContain(auth.protectedResourceMetadataUrl);
  });

  it("rejects invalid bearer tokens and serves protected-resource metadata", async () => {
    const { httpServer, auth } = await startAuthedHttpServer({
      mode: "mixed",
      requiredScopes: ["ops:write"],
    });
    const address = httpServer.server.address() as AddressInfo;

    const unauthorized = await fetch(`http://127.0.0.1:${address.port}/mcp`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer not-a-real-token",
      },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        method: "initialize",
        params: {
          protocolVersion: "2025-03-26",
          capabilities: {},
          clientInfo: {
            name: "unauthorized-test",
            version: "1.0.0",
          },
        },
      }),
    });

    expect(unauthorized.status).toBe(401);
    expect(unauthorized.headers.get("www-authenticate")).toContain("resource_metadata=");

    const metadata = await fetch(`http://127.0.0.1:${address.port}${auth.protectedResourceMetadataPath}`);
    expect(metadata.status).toBe(200);
    expect(await metadata.json()).toMatchObject({
      resource: `http://127.0.0.1:${address.port}/mcp`,
      scopes_supported: ["ops:write"],
    });
  });

  it("rejects invalid host headers on localhost binds", async () => {
    const { httpServer } = await startAuthedHttpServer({ mode: "none" });
    const address = httpServer.server.address() as AddressInfo;

    const statusCode = await new Promise<number>((resolve, reject) => {
      const req = request({
        host: "127.0.0.1",
        port: address.port,
        path: "/healthz",
        headers: {
          Host: "evil.example.com",
        },
      }, (res) => {
        resolve(res.statusCode ?? 0);
      });
      req.once("error", reject);
      req.end();
    });

    expect(statusCode).toBe(400);
  });
});
