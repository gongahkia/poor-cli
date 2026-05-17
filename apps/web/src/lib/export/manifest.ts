import type { AnalystMemoReady } from "@/types/analyst-memo";
import type { BusinessDossier } from "@/types/dossier";
import type { WebPresence } from "@/lib/api/client";

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
  includedArtifacts: {
    analystMemo: boolean;
    webPresence: boolean;
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
  webPresence?: WebPresence;
}): Promise<DossierExportManifest> {
  const generatedAt = params.generatedAt ?? new Date().toISOString();
  const dossierHash = await sha256Hex(stableStringify(params.dossier));
  const signaturePayload = stableStringify({
    dossierHash,
    generatedAt,
    provenance: params.dossier.provenance,
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
    includedArtifacts: {
      analystMemo: params.analystMemo !== undefined,
      webPresence: params.webPresence !== undefined,
    },
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
