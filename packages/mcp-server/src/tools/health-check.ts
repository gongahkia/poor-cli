import { formatResponse, Keystore, MasDataset } from "@sg-apis/shared";
import type { CredentialSource, ToolResult, HealthStatus } from "@sg-apis/shared";
import { getHdbResalePrices } from "../apis/hdb/client.js";
import { getBusArrivals } from "../apis/lta/client.js";
import { query as queryMas } from "../apis/mas/client.js";
import { getForecast2Hr } from "../apis/nea/client.js";
import { geocode } from "../apis/onemap/client.js";
import { getTableData as getSingStatTableData } from "../apis/singstat/client.js";
import { getBoaArchitectureFirms } from "../apis/boa/client.js";
import { getGovFeedItems } from "../apis/govfeeds/client.js";
import { uraFetch } from "../apis/ura/client.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";
import { LIVE_API_SURFACE } from "./runtime-surface.js";

type CredentialLookup = Pick<Keystore, "getKey">;
type HealthProbeResult = Readonly<{ ok: boolean; status: number; statusText: string }>;
type HealthClassification = NonNullable<HealthStatus["classification"]>;

type HealthCheckTarget = {
  readonly api: string;
  readonly classification: HealthClassification;
  readonly url: string;
  readonly probeMode: "runtime_client";
  readonly representativeTool: string;
  readonly releaseBlocking: boolean;
  readonly authRequired: boolean;
  readonly configured: (lookup: CredentialLookup) => boolean;
  readonly credentialSource?: (lookup: CredentialLookup) => CredentialSource;
  readonly dependentFamilies?: readonly string[];
  readonly coverageNotes?: readonly string[];
  readonly probe: () => Promise<HealthProbeResult>;
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
const HEALTH_TIMEOUT_MS = 15000;
const OK_HEALTH_RESPONSE: HealthProbeResult = {
  ok: true,
  status: 200,
  statusText: "OK",
};

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

export const probeSingStatHealth = async (): Promise<HealthProbeResult> => {
  const table = await getSingStatTableData("M015631", {
    variables: ["GDP At Current Market Prices"],
  });
  if (table.rows.length === 0) {
    throw new Error("SingStat GDP probe returned no rows.");
  }
  return OK_HEALTH_RESPONSE;
};

export const probeMasHealth = async (): Promise<HealthProbeResult> => {
  const records = await queryMas(MasDataset.INTEREST_RATES_SORA, { limit: 1 });
  if (records.length === 0) {
    throw new Error("MAS SORA probe returned no rows.");
  }
  return OK_HEALTH_RESPONSE;
};

export const probeDatagovDatastoreHealth = async (): Promise<HealthProbeResult> => {
  const rows = await getHdbResalePrices({ town: "Bedok", flatType: "4 ROOM", limit: 1 });
  if (rows.length === 0) {
    throw new Error("data.gov.sg datastore probe returned no rows.");
  }
  return OK_HEALTH_RESPONSE;
};

export const probeDatagovFileDownloadHealth = async (): Promise<HealthProbeResult> => {
  const rows = await getBoaArchitectureFirms({ limit: 1 });
  if (rows.length === 0) {
    throw new Error("data.gov.sg file-download probe returned no rows.");
  }
  return OK_HEALTH_RESPONSE;
};

export const probeNeaHealth = async (): Promise<HealthProbeResult> => {
  const rows = await getForecast2Hr("Tampines");
  if (rows.length === 0) {
    throw new Error("NEA forecast probe returned no rows.");
  }
  return OK_HEALTH_RESPONSE;
};

export const probeGovFeedsHealth = async (): Promise<HealthProbeResult> => {
  const result = await getGovFeedItems({ feedId: "mpa_press_releases", limit: 1 });
  if (result.records.length === 0) {
    throw new Error("Government feeds probe returned no rows.");
  }
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

const PROBES = {
  "SingStat": probeSingStatHealth,
  "MAS": probeMasHealth,
  "OneMap": probeOneMapHealth,
  "URA": probeUraHealth,
  "LTA DataMall": probeLtaHealth,
  "data.gov.sg datastore": probeDatagovDatastoreHealth,
  "data.gov.sg file downloads": probeDatagovFileDownloadHealth,
  "NEA": probeNeaHealth,
  "Government RSS Feeds": probeGovFeedsHealth,
} as const;

export const getHealthCheckTargets = (): readonly HealthCheckTarget[] => {
  return LIVE_API_SURFACE.map((surface) => {
    const probe = PROBES[surface.api as keyof typeof PROBES];
    if (probe === undefined) {
      throw new Error(`Missing health probe for ${surface.api}.`);
    }
    return {
      api: surface.api,
      classification: surface.classification,
      url: surface.productionUrl,
      probeMode: surface.probeMode,
      representativeTool: surface.representativeTool,
      releaseBlocking: surface.releaseBlocking,
      authRequired: surface.authRequired,
      configured:
        surface.api === "OneMap"
          ? hasOneMapCredentials
          : surface.api === "URA"
            ? hasUraKey
            : surface.api === "LTA DataMall"
              ? hasLtaKey
              : () => true,
      credentialSource:
        surface.api === "OneMap"
          ? getOneMapCredentialSource
          : surface.api === "URA"
            ? getUraCredentialSource
            : surface.api === "LTA DataMall"
              ? getLtaCredentialSource
              : () => NOT_REQUIRED,
      ...(surface.dependentFamilies.length === 0 ? {} : { dependentFamilies: surface.dependentFamilies }),
      ...(surface.healthNotes.length === 0 ? {} : { coverageNotes: surface.healthNotes }),
      probe,
    };
  });
};

export const checkApiHealth = async (
  target: HealthCheckTarget,
  lookup: CredentialLookup,
): Promise<HealthStatus> => {
  const configured = target.configured(lookup);
  const credentialSource = target.credentialSource?.(lookup) ?? (target.authRequired ? "none" : NOT_REQUIRED);
  const start = Date.now();
  const controller = new AbortController();

  try {
    const response = await withHealthTimeout(
      target.probe(),
      () => controller.abort(),
    );

    return {
      api: target.api,
      authRequired: target.authRequired,
      configured,
      credentialSource,
      reachable: true,
      latencyMs: Date.now() - start,
      classification: target.classification,
      probeMode: target.probeMode,
      productionUrl: target.url,
      representativeTool: target.representativeTool,
      releaseBlocking: target.releaseBlocking,
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
      classification: target.classification,
      probeMode: target.probeMode,
      productionUrl: target.url,
      representativeTool: target.representativeTool,
      releaseBlocking: target.releaseBlocking,
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
        getHealthCheckTargets().map((target) => checkApiHealth(target, keystore)),
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
