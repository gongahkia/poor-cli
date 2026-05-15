import type { EvidenceGap, BriefLimit } from "@/types/dossier";

export type AnalystMemoCitation = {
  id: string;
  label: string;
  source: string;
  text: string;
};

export type AnalystMemoBullet = {
  text: string;
  citationIds: string[];
};

export type AnalystRiskRating = {
  level: "low" | "medium" | "high" | "unknown";
  rationale: string;
  citationIds: string[];
  confidenceBlockers: string[];
};

export type AnalystDecisionAid = {
  nextSteps: string[];
  confidenceBlockers: string[];
  nonAdvisoryReminder: string;
};

export type AnalystMemoReady = {
  status: "ready";
  configured: true;
  provider: "anthropic" | "openai" | "google";
  model: string;
  generatedAt: string;
  evidenceMemo: AnalystMemoBullet[];
  riskRating: AnalystRiskRating;
  decisionAid: AnalystDecisionAid;
  citations: AnalystMemoCitation[];
  gaps: EvidenceGap[];
  limits: BriefLimit[];
  rejectedClaims: {
    claim: string;
    reason: string;
  }[];
};

export type AnalystMemoUnavailable = {
  status: "unavailable";
  configured: false;
  provider: "anthropic" | "openai" | "google";
  model: string;
  generatedAt: string;
  reason: {
    code: string;
    message: string;
  };
  gaps: EvidenceGap[];
  limits: BriefLimit[];
};

export type AnalystMemoError = {
  status: "error";
  configured: true;
  provider: "anthropic" | "openai" | "google";
  model: string;
  generatedAt: string;
  reason: {
    code: string;
    message: string;
  };
  gaps: EvidenceGap[];
  limits: BriefLimit[];
};

export type AnalystMemoResponse = AnalystMemoReady | AnalystMemoUnavailable | AnalystMemoError;
