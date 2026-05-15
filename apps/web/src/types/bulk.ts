import type { BusinessDossier } from "@/types/dossier";

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

export type ShortlistEntry = {
  canonicalIdentifier: string;
  entity: string | null;
  uen: string | null;
  entityStatus: string | null;
  confidence: string | null;
  risk: BulkDossierRow["risk"];
  riskFlags: string[];
  gapCodes: string[];
  provenanceSources: string[];
  savedAt: string;
};
