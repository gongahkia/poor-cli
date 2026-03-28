import { formatResponse, Keystore, getMockApiBaseUrl } from "@sg-apis/shared";
import type { CredentialSource, ToolResult, HealthStatus } from "@sg-apis/shared";
import { getBusArrivals } from "../apis/lta/client.js";
import { geocode } from "../apis/onemap/client.js";
import { uraFetch } from "../apis/ura/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

type CredentialLookup = Pick<Keystore, "getKey">;
type HealthProbeResult = Readonly<{ ok: boolean; status: number; statusText: string }>;

type HealthCheckTarget = {
  readonly api: string;
  readonly url: string;
  readonly authRequired: boolean;
  readonly configured: (lookup: CredentialLookup) => boolean;
  readonly credentialSource?: (lookup: CredentialLookup) => CredentialSource;
  readonly dependentFamilies?: readonly string[];
  readonly coverageNotes?: readonly string[];
  readonly probe?: () => Promise<HealthProbeResult>;
};

type HealthFetch = (
  input: string,
  init?: Readonly<RequestInit>,
) => Promise<HealthProbeResult>;

const getHealthBaseUrl = (apiPath: string, productionUrl: string): string => {
  const mockApiBaseUrl = getMockApiBaseUrl();
  return mockApiBaseUrl !== undefined ? `${mockApiBaseUrl}/${apiPath}` : productionUrl;
};

const hasConfiguredValue = (value: string | null | undefined): boolean => {
  return value !== undefined && value !== null && value !== "";
};

const resolveCredentialSource = (
  envValue: string | undefined,
  keystoreValue: string | null,
): CredentialSource => {
  const hasEnv = hasConfiguredValue(envValue);
  const hasKeystore = hasConfiguredValue(keystoreValue);

  if (hasEnv && hasKeystore) {
    return "mixed";
  }
  if (hasEnv) {
    return "env";
  }
  if (hasKeystore) {
    return "keystore";
  }
  return "none";
};

export const getOneMapCredentialSource = (lookup: CredentialLookup): CredentialSource => {
  const emailSource = resolveCredentialSource(process.env["SG_API_ONEMAP_EMAIL"], lookup.getKey("onemap_email"));
  const passwordSource = resolveCredentialSource(process.env["SG_API_ONEMAP_PASSWORD"], lookup.getKey("onemap_password"));

  if (emailSource === "none" && passwordSource === "none") {
    return "none";
  }
  if (emailSource === "env" && passwordSource === "env") {
    return "env";
  }
  if (emailSource === "keystore" && passwordSource === "keystore") {
    return "keystore";
  }
  return "mixed";
};

export const getUraCredentialSource = (lookup: CredentialLookup): CredentialSource => {
  return resolveCredentialSource(process.env["SG_API_URA_KEY"], lookup.getKey("ura"));
};

export const getLtaCredentialSource = (lookup: CredentialLookup): CredentialSource => {
  return resolveCredentialSource(process.env["SG_API_LTA_KEY"], lookup.getKey("lta"));
};

const NOT_REQUIRED: CredentialSource = "not_required";
const HEALTH_TIMEOUT_MS = 5000;
const OK_HEALTH_RESPONSE: HealthProbeResult = {
  ok: true,
  status: 200,
  statusText: "OK",
};

const DATAGOV_DEPENDENT_FAMILIES = [
  "HDB",
  "CEA",
  "BCA",
  "BOA",
  "ACRA",
  "PA",
  "Sport Singapore",
  "ECDA",
  "MSF Family Services",
  "MSF Student Care Services",
  "MSF Social Service Offices",
  "GeBIZ",
  "Hawker Centres",
  "MOE Schools",
  "MOH Healthcare",
  "HSA",
  "SFA",
  "NParks",
  "PUB",
  "MOM",
  "STB",
  "HLB",
] as const;

const withHealthTimeout = async <T>(
  task: Promise<T>,
  onTimeout?: () => void,
): Promise<T> => {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => {
      onTimeout?.();
      reject(new Error(`Health check timed out after ${HEALTH_TIMEOUT_MS}ms`));
    }, HEALTH_TIMEOUT_MS);

    task.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error: unknown) => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
};

export const probeOneMapHealth = async (): Promise<HealthProbeResult> => {
  await geocode("049178", 1);
  return OK_HEALTH_RESPONSE;
};

export const probeUraHealth = async (): Promise<HealthProbeResult> => {
  await uraFetch<{ readonly Status?: string; readonly Result?: readonly unknown[] }>("DC_Rates");
  return OK_HEALTH_RESPONSE;
};

export const probeLtaHealth = async (): Promise<HealthProbeResult> => {
  await getBusArrivals("83139");
  return OK_HEALTH_RESPONSE;
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

export const hasLtaKey = (lookup: CredentialLookup): boolean => {
  const key = process.env["SG_API_LTA_KEY"] ?? lookup.getKey("lta");
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
      credentialSource: () => NOT_REQUIRED,
    },
    {
      api: "MAS",
      url: getHealthBaseUrl(
        "mas/search.json?resource_id=95932927-c8bc-4e7a-b484-68a66a24edfe&limit=1",
        "https://eservices.mas.gov.sg/api/action/datastore/search.json?resource_id=95932927-c8bc-4e7a-b484-68a66a24edfe&limit=1",
      ),
      authRequired: false,
      configured: () => true,
      credentialSource: () => NOT_REQUIRED,
    },
    {
      api: "OneMap",
      url: getHealthBaseUrl(
        "onemap/common/elastic/search?searchVal=Singapore&returnGeom=Y&getAddrDetails=Y&pageNum=1",
        "https://www.onemap.gov.sg/api/common/elastic/search?searchVal=Singapore&returnGeom=Y&getAddrDetails=Y&pageNum=1",
      ),
      authRequired: true,
      configured: hasOneMapCredentials,
      credentialSource: getOneMapCredentialSource,
      probe: probeOneMapHealth,
    },
    {
      api: "URA",
      url: getHealthBaseUrl(
        "ura/insertNewToken.action",
        "https://www.ura.gov.sg/uraDataService/insertNewToken.action",
      ),
      authRequired: true,
      configured: hasUraKey,
      credentialSource: getUraCredentialSource,
      probe: probeUraHealth,
    },
    {
      api: "LTA",
      url: getHealthBaseUrl(
        "lta/v3/BusArrival?BusStopCode=83139",
        "https://datamall2.mytransport.sg/ltaodataservice/v3/BusArrival?BusStopCode=83139",
      ),
      authRequired: true,
      configured: hasLtaKey,
      credentialSource: getLtaCredentialSource,
      probe: probeLtaHealth,
    },
    {
      api: "data.gov.sg",
      url: getHealthBaseUrl(
        "datagov/datasets?page=0&resultSize=1",
        "https://api-production.data.gov.sg/v2/public/api/datasets?page=0&resultSize=1",
      ),
      authRequired: false,
      configured: () => true,
      credentialSource: () => NOT_REQUIRED,
      dependentFamilies: DATAGOV_DEPENDENT_FAMILIES,
      coverageNotes: [
        "This target also covers curated registry, civic-directory, amenity, procurement, and statistics families backed by the shared data.gov.sg API or official file-download path.",
      ],
    },
    {
      api: "NEA",
      url: getHealthBaseUrl(
        "nea/two-hr-forecast",
        "https://api-open.data.gov.sg/v2/real-time/api/two-hr-forecast",
      ),
      authRequired: false,
      configured: () => true,
      credentialSource: () => NOT_REQUIRED,
    },
  ];
};

export const checkApiHealth = async (
  target: HealthCheckTarget,
  fetchFn: HealthFetch,
  lookup: CredentialLookup,
): Promise<HealthStatus> => {
  const configured = target.configured(lookup);
  const credentialSource = target.credentialSource?.(lookup) ?? (target.authRequired ? "none" : NOT_REQUIRED);
  const start = Date.now();
  const controller = new AbortController();

  try {
    const response = await withHealthTimeout(
      target.probe !== undefined
        ? target.probe()
        : fetchFn(target.url, { signal: controller.signal }),
      () => controller.abort(),
    );

    return {
      api: target.api,
      authRequired: target.authRequired,
      configured,
      credentialSource,
      reachable: true,
      latencyMs: Date.now() - start,
      ...(target.dependentFamilies === undefined ? {} : { dependentFamilies: target.dependentFamilies }),
      ...(target.coverageNotes === undefined ? {} : { coverageNotes: target.coverageNotes }),
      ...(response.ok ? {} : { error: `HTTP ${response.status} ${response.statusText}` }),
    };
  } catch (error) {
    return {
      api: target.api,
      authRequired: target.authRequired,
      configured,
      credentialSource,
      reachable: false,
      latencyMs: Date.now() - start,
      ...(target.dependentFamilies === undefined ? {} : { dependentFamilies: target.dependentFamilies }),
      ...(target.coverageNotes === undefined ? {} : { coverageNotes: target.coverageNotes }),
      error: error instanceof Error ? error.message : String(error),
    };
  }
};

export const healthCheckToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_health_check",
    description: "Check connectivity and credential status for all Singapore government APIs.",
    surface: "operational",
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
      return {
        content: [{ type: "text", text }],
        structuredContent: { records: statuses },
      };
    },
  },
];
