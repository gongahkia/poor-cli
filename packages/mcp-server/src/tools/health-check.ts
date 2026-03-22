import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { formatResponse, Keystore, getMockApiBaseUrl } from "@sg-apis/shared";
import type { ToolResult, HealthStatus } from "@sg-apis/shared";
import { registerTool } from "./registry.js";

type CredentialLookup = Pick<Keystore, "getKey">;

type HealthCheckTarget = {
  readonly api: string;
  readonly url: string;
  readonly authRequired: boolean;
  readonly configured: (lookup: CredentialLookup) => boolean;
};

type HealthFetch = (
  input: string,
  init?: Readonly<{ signal?: AbortSignal }>,
) => Promise<Readonly<{ ok: boolean; status: number; statusText: string }>>;

const getHealthBaseUrl = (apiPath: string, productionUrl: string): string => {
  const mockApiBaseUrl = getMockApiBaseUrl();
  return mockApiBaseUrl !== undefined ? `${mockApiBaseUrl}/${apiPath}` : productionUrl;
};

const hasConfiguredValue = (value: string | null | undefined): boolean => {
  return value !== undefined && value !== null && value !== "";
};

export const hasOneMapCredentials = (lookup: CredentialLookup): boolean => {
  const email = process.env["SG_API_ONEMAP_EMAIL"] ?? lookup.getKey("onemap_email");
  const password = process.env["SG_API_ONEMAP_PASSWORD"] ?? lookup.getKey("onemap_password");
  return hasConfiguredValue(email) && hasConfiguredValue(password);
};

export const hasUraKey = (lookup: CredentialLookup): boolean => {
  const key = process.env["SG_API_URA_KEY"] ?? lookup.getKey("ura");
  return hasConfiguredValue(key);
};

export const getHealthCheckTargets = (): readonly HealthCheckTarget[] => {
  return [
    {
      api: "SingStat",
      url: getHealthBaseUrl(
        "singstat/resourceId?keyword=test&searchOption=all&limit=1",
        "https://tablebuilder.singstat.gov.sg/api/table/resourceId?keyword=test&searchOption=all&limit=1",
      ),
      authRequired: false,
      configured: () => true,
    },
    {
      api: "MAS",
      url: getHealthBaseUrl(
        "mas/search.json?resource_id=95932927-c8bc-4e7a-b484-68a66a24edfe&limit=1",
        "https://eservices.mas.gov.sg/api/action/datastore/search.json?resource_id=95932927-c8bc-4e7a-b484-68a66a24edfe&limit=1",
      ),
      authRequired: false,
      configured: () => true,
    },
    {
      api: "OneMap",
      url: getHealthBaseUrl(
        "onemap/common/elastic/search?searchVal=Singapore&returnGeom=Y&getAddrDetails=Y&pageNum=1",
        "https://www.onemap.gov.sg/api/common/elastic/search?searchVal=Singapore&returnGeom=Y&getAddrDetails=Y&pageNum=1",
      ),
      authRequired: true,
      configured: hasOneMapCredentials,
    },
    {
      api: "URA",
      url: getHealthBaseUrl(
        "ura/insertNewToken.action",
        "https://www.ura.gov.sg/uraDataService/insertNewToken.action",
      ),
      authRequired: true,
      configured: hasUraKey,
    },
    {
      api: "data.gov.sg",
      url: getHealthBaseUrl(
        "datagov/datasets?page=0&resultSize=1",
        "https://api-production.data.gov.sg/v2/public/api/datasets?page=0&resultSize=1",
      ),
      authRequired: false,
      configured: () => true,
    },
  ];
};

export const checkApiHealth = async (
  target: HealthCheckTarget,
  fetchFn: HealthFetch,
  lookup: CredentialLookup,
): Promise<HealthStatus> => {
  const configured = target.configured(lookup);
  const start = Date.now();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);

  try {
    const response = await fetchFn(target.url, { signal: controller.signal });
    clearTimeout(timeout);

    return {
      api: target.api,
      authRequired: target.authRequired,
      configured,
      reachable: true,
      latencyMs: Date.now() - start,
      ...(response.ok ? {} : { error: `HTTP ${response.status} ${response.statusText}` }),
    };
  } catch (error) {
    clearTimeout(timeout);
    return {
      api: target.api,
      authRequired: target.authRequired,
      configured,
      reachable: false,
      latencyMs: Date.now() - start,
      error: error instanceof Error ? error.message : String(error),
    };
  }
};

export const registerHealthCheckTool = (server: McpServer): void => {
  registerTool(server, {
    name: "sg_health_check",
    description: "Check connectivity and credential status for all Singapore government APIs.",
    inputSchema: {},
    handler: async (_input: unknown): Promise<ToolResult> => {
      const keystore = new Keystore();
      const statuses = await Promise.all(
        getHealthCheckTargets().map((target) =>
          checkApiHealth(target, (url, init) => fetch(url, init), keystore),
        ),
      );
      keystore.close();

      const text = formatResponse(statuses as unknown as Record<string, unknown>[], "markdown");
      return { content: [{ type: "text", text }] };
    },
  });
};
