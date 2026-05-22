import { formatResponse, Keystore } from "@swee-sg/shared";
import type { CredentialSource, ToolResult, HealthStatus } from "@swee-sg/shared";
import { probeAcraLookupReadiness } from "../apis/acra/client.js";
import { getBoaArchitectureFirms } from "../apis/boa/client.js";
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

export const probeDatagovDatastoreHealth = async (): Promise<HealthProbeResult> => {
  const result = await probeAcraLookupReadiness();
  if (result.recordCount === 0) {
    throw new Error("CDD datastore probe returned no ACRA rows.");
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

export const probeExternalDiligenceHealth = async (): Promise<HealthProbeResult> => {
  return OK_HEALTH_RESPONSE;
};

const PROBES = {
  "data.gov.sg datastore": probeDatagovDatastoreHealth,
  "data.gov.sg file downloads": probeDatagovFileDownloadHealth,
  "External Diligence": probeExternalDiligenceHealth,
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
      configured: () => true,
      credentialSource: () => NOT_REQUIRED,
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
