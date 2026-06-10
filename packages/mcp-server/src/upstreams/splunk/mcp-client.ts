import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { ApiError, getTimeout, Keystore } from "@swee-sg/shared";

type EnvMap = Readonly<Record<string, string | undefined>>;
type KeystoreReader = Pick<Keystore, "getKey">;
type SplunkTransport = Parameters<Client["connect"]>[0] & {
  readonly terminateSession?: () => Promise<void>;
};

export type SplunkMcpConfig = {
  readonly url: string;
  readonly token: string;
  readonly timeoutMs: number;
};

export type SplunkMcpTokenSource = "env" | "keystore" | "none";

export type SplunkMcpConfigReadiness = {
  readonly configured: boolean;
  readonly urlConfigured: boolean;
  readonly tokenConfigured: boolean;
  readonly tokenSource: SplunkMcpTokenSource;
  readonly allowedIndexesConfigured: boolean;
};

export type SplunkMcpTransportConfig = SplunkMcpConfig & {
  readonly authorizationHeader: string;
};

export type SplunkMcpTransportFactory = (config: SplunkMcpTransportConfig) => SplunkTransport;

export type SplunkToolListResult = Awaited<ReturnType<Client["listTools"]>>;
export type SplunkToolCallResult = Awaited<ReturnType<Client["callTool"]>>;

export type SplunkMcpClientOptions = {
  readonly config?: SplunkMcpConfig;
  readonly transportFactory?: SplunkMcpTransportFactory;
};

let defaultKeystore: Keystore | null = null;

const getDefaultKeystore = (): Keystore => {
  defaultKeystore ??= new Keystore();
  return defaultKeystore;
};

const readEnvValue = (env: EnvMap, key: string): string | undefined => {
  const value = env[key]?.trim();
  return value === undefined || value === "" ? undefined : value;
};

const missingConfig = (message: string, suggestedAction: string): ApiError =>
  new ApiError({
    apiName: "splunk_mcp",
    source: "Splunk MCP",
    statusCode: 401,
    code: "AUTH_MISSING",
    message,
    retryable: false,
    suggestedAction,
  });

export const resolveSplunkMcpConfig = (options: {
  readonly env?: EnvMap;
  readonly keystore?: KeystoreReader;
  readonly timeoutMs?: number;
} = {}): SplunkMcpConfig => {
  const env = options.env ?? process.env;
  const url = readEnvValue(env, "SPLUNK_MCP_URL");
  if (url === undefined) {
    throw missingConfig("SPLUNK_MCP_URL is not configured.", "Set SPLUNK_MCP_URL to the Splunk MCP Streamable HTTP endpoint.");
  }

  const envToken = readEnvValue(env, "SPLUNK_MCP_TOKEN");
  const keystore = options.keystore ?? getDefaultKeystore();
  const keyToken = envToken ?? keystore.getKey("splunk_mcp") ?? undefined;
  const token = keyToken?.trim();
  if (token === undefined || token === "") {
    throw missingConfig("SPLUNK_MCP_TOKEN is not configured.", "Set SPLUNK_MCP_TOKEN or run sg_key_set with apiName=splunk_mcp.");
  }

  return {
    url,
    token,
    timeoutMs: options.timeoutMs ?? getTimeout("splunk_mcp"),
  };
};

export const inspectSplunkMcpConfig = (options: {
  readonly env?: EnvMap;
  readonly keystore?: KeystoreReader;
} = {}): SplunkMcpConfigReadiness => {
  const env = options.env ?? process.env;
  const keystore = options.keystore ?? getDefaultKeystore();
  const urlConfigured = readEnvValue(env, "SPLUNK_MCP_URL") !== undefined;
  const envToken = readEnvValue(env, "SPLUNK_MCP_TOKEN");
  const keystoreToken = envToken === undefined ? keystore.getKey("splunk_mcp")?.trim() : undefined;
  const tokenSource: SplunkMcpTokenSource = envToken !== undefined
    ? "env"
    : keystoreToken !== undefined && keystoreToken !== ""
      ? "keystore"
      : "none";
  const tokenConfigured = tokenSource !== "none";
  const allowedIndexesConfigured = readEnvValue(env, "SPLUNK_MCP_ALLOWED_INDEXES") !== undefined;
  return {
    configured: urlConfigured && tokenConfigured,
    urlConfigured,
    tokenConfigured,
    tokenSource,
    allowedIndexesConfigured,
  };
};

export const createSplunkMcpTransport: SplunkMcpTransportFactory = (config) =>
  new StreamableHTTPClientTransport(new URL(config.url), {
    requestInit: {
      headers: {
        Authorization: config.authorizationHeader,
      },
    },
  }) as unknown as SplunkTransport;

const withSplunkClient = async <T>(
  options: SplunkMcpClientOptions,
  callback: (client: Client, config: SplunkMcpConfig) => Promise<T>,
): Promise<T> => {
  const config = options.config ?? resolveSplunkMcpConfig();
  const transportFactory = options.transportFactory ?? createSplunkMcpTransport;
  const transport = transportFactory({
    ...config,
    authorizationHeader: `Bearer ${config.token}`,
  });
  const client = new Client({ name: "swee-shield-splunk-proxy", version: "0.1.0" }, { capabilities: {} });

  try {
    await client.connect(transport as Parameters<typeof client.connect>[0], { timeout: config.timeoutMs });
    return await callback(client, config);
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError({
      apiName: "splunk_mcp",
      source: "Splunk MCP",
      statusCode: 502,
      code: "UPSTREAM_MCP_ERROR",
      message: error instanceof Error ? error.message : String(error),
      retryable: true,
    });
  } finally {
    await transport.terminateSession?.().catch(() => undefined);
    await client.close().catch(() => undefined);
  }
};

export const listSplunkTools = async (options: SplunkMcpClientOptions = {}): Promise<SplunkToolListResult> =>
  withSplunkClient(options, async (client, config) => client.listTools({}, { timeout: config.timeoutMs }));

export const callSplunkTool = async (
  name: string,
  args: Readonly<Record<string, unknown>>,
  options: SplunkMcpClientOptions = {},
): Promise<SplunkToolCallResult> =>
  withSplunkClient(options, async (client, config) =>
    client.callTool({ name, arguments: args }, undefined, { timeout: config.timeoutMs })
  );
