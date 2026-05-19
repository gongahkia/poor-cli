import type { BusinessDossier } from "@/types/dossier";
import type { AnalystMemoResponse } from "@/types/analyst-memo";
import type { PeopleDiscovery, WebPresence } from "@/lib/api/client";

export type BulkDossierRow = {
  index: number;
  input: string;
  status: "success" | "not_found" | "error";
  canonicalIdentifier: string | null;
  entity: string | null;
  uen: string | null;
  entityStatus: string | null;
  confidence: string | null;
  risk: "high" | "medium" | "low" | "none";
  riskFlags: string[];
  matchedModules: string[];
  gapCodes: string[];
  upstreamFailure: boolean;
  provenanceSources: string[];
  generatedAt: string;
  dossier?: BusinessDossier;
  webPresence?: WebPresence;
  peopleDiscovery?: PeopleDiscovery;
  memo?: AnalystMemoResponse;
  orchestration?: {
    status: "ready" | "identity_not_resolved";
    strategy: string;
    acraSectorHints: string[];
    webSectorHints: string[];
    effectiveSectorHints: string[];
    officialModules: string[];
    supplementalTools: string[];
    reranDossierForWebSectorHints: boolean;
    limits: string[];
  };
  error?: {
    code: string;
    message: string;
  };
};

export type BulkParseError = {
  index: number;
  input: string;
  code: string;
  message: string;
};

export type BulkDossierResponse = {
  generatedAt: string;
  maxItems: number;
  requestedCount: number;
  executedCount: number;
  parseErrors: BulkParseError[];
  rows: BulkDossierRow[];
  limits: string[];
};
