import type { AnalystMemoReady } from "@/types/analyst-memo";
import type { BusinessDossier } from "@/types/dossier";
import type { PeopleDiscovery, WebPresence } from "@/lib/api/client";
import { getAnalystFollowUps } from "@/lib/next-checks";
import { buildSourceUseWarnings, type SourceUseWarning } from "@/lib/source-use-warnings";
import type { CddOrchestrationTrace } from "@/types/orchestration";

export type DossierExportManifest = {
  schemaVersion: "dude-export-manifest/v1";
  generatedAt: string;
  toolVersion: "dude-web/0.0.0";
  dossierHash: string;
  sourceFreshness: {
    source: string;
    observedAt: string;
    upstreamTimestamp?: string | null;
  }[];
  provenance: {
    source: string;
    tool: string;
    recordCount: number;
  }[];
  sourceCoverage: {
    family: string;
    label: string;
    status: string;
    coverageLevel: string;
    recordCount: number;
    reason: string;
  }[];
  sourceUseWarnings: SourceUseWarning[];
  analystFollowUps: {
    id: string;
    priority: string;
    category: string;
    action: string;
    evidenceRefs: string[];
  }[];
  includedArtifacts: {
    analystMemo: boolean;
    orchestrationTrace: boolean;
    peopleDiscovery: boolean;
    webPresence: boolean;
  };
  orchestration?: {
    status: CddOrchestrationTrace["status"];
    strategy: string;
    stages: {
      id: string;
      label: string;
      status: string;
      tools: string[];
    }[];
  };
  signature: {
    algorithm: "sha256";
    value: string;
    note: string;
  };
};

const stableStringify = (value: unknown): string => {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(",")}]`;
  }
  return `{${Object.entries(value as Record<string, unknown>)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, item]) => `${JSON.stringify(key)}:${stableStringify(item)}`)
    .join(",")}}`;
};

const sha256Hex = async (text: string): Promise<string> => {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
};

export async function buildDossierExportManifest(params: {
  analystMemo?: AnalystMemoReady;
  dossier: BusinessDossier;
  generatedAt?: string;
  orchestration?: CddOrchestrationTrace;
  peopleDiscovery?: PeopleDiscovery;
  webPresence?: WebPresence;
}): Promise<DossierExportManifest> {
  const generatedAt = params.generatedAt ?? new Date().toISOString();
  const dossierHash = await sha256Hex(stableStringify(params.dossier));
  const sourceUseWarnings = buildSourceUseWarnings({
    dossier: params.dossier,
    ...(params.peopleDiscovery === undefined ? {} : { peopleDiscovery: params.peopleDiscovery }),
    ...(params.webPresence === undefined ? {} : { webPresence: params.webPresence }),
  });
  const analystFollowUps = getAnalystFollowUps(params.dossier);
  const signaturePayload = stableStringify({
    analystFollowUps,
    dossierHash,
      generatedAt,
      orchestration: params.orchestration,
      peopleDiscovery: params.peopleDiscovery,
      provenance: params.dossier.provenance,
      sourceCoverage: params.dossier.sourceCoverage ?? [],
    sourceUseWarnings,
    sourceFreshness: params.dossier.freshness,
  });
  const signature = await sha256Hex(signaturePayload);

  return {
    schemaVersion: "dude-export-manifest/v1",
    generatedAt,
    toolVersion: "dude-web/0.0.0",
    dossierHash,
    sourceFreshness: params.dossier.freshness.map((item) => ({
      source: item.source,
      observedAt: item.observedAt,
      ...(item.upstreamTimestamp === undefined ? {} : { upstreamTimestamp: item.upstreamTimestamp }),
    })),
    provenance: params.dossier.provenance.map((item) => ({
      source: item.source,
      tool: item.tool,
      recordCount: item.recordCount,
    })),
    sourceCoverage: (params.dossier.sourceCoverage ?? []).map((item) => ({
      family: item.family,
      label: item.label,
      status: item.status,
      coverageLevel: item.coverageLevel,
      recordCount: item.recordCount,
      reason: item.reason,
    })),
    sourceUseWarnings,
    analystFollowUps: analystFollowUps.map((followUp) => ({
      id: followUp.id,
      priority: followUp.priority,
      category: followUp.category,
      action: followUp.action,
      evidenceRefs: followUp.evidenceBasis.map((basis) => basis.ref),
    })),
    includedArtifacts: {
      analystMemo: params.analystMemo !== undefined,
      orchestrationTrace: params.orchestration !== undefined,
      peopleDiscovery: params.peopleDiscovery !== undefined,
      webPresence: params.webPresence !== undefined,
    },
    ...(params.orchestration === undefined ? {} : {
      orchestration: {
        status: params.orchestration.status,
        strategy: params.orchestration.strategy,
        stages: (params.orchestration.stages ?? []).map((stage) => ({
          id: stage.id,
          label: stage.label,
          status: stage.status,
          tools: stage.tools,
        })),
      },
    }),
    signature: {
      algorithm: "sha256",
      value: signature,
      note: "Local deterministic SHA-256 manifest signature for downstream integrity checks; it is not a third-party digital certificate.",
    },
  };
}

export function verifyDossierExportManifest(params: {
  manifest: DossierExportManifest;
  dossier: BusinessDossier;
}): Promise<boolean> {
  return sha256Hex(stableStringify(params.dossier)).then((hash) => hash === params.manifest.dossierHash);
}
