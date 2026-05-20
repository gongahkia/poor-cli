import type { EvidenceGap, BriefLimit } from "@/types/dossier";

export type SummaryTargetId =
  | "overview.summary"
  | "overview.snapshot"
  | "overview.risk"
  | "overview.memo"
  | "overview.confidence"
  | "evidence.metrics"
  | "evidence.searched"
  | "evidence.notSearched"
  | "evidence.records"
  | "evidence.webPresence"
  | "evidence.peopleDiscovery"
  | "actions.pdpa"
  | "actions.nextChecks"
  | "audit.handoff"
  | "audit.gaps"
  | "audit.provenance";

export type InteractiveSummarySegment = {
  text: string;
  emphasized: boolean;
  targetId: SummaryTargetId;
};

export type InteractiveSummaryPrompt = {
  system: string;
  user: string;
  copyText: string;
};

export type InteractiveSummaryReady = {
  status: "ready";
  configured: true;
  provider: "anthropic" | "openai" | "google";
  model: string;
  generatedAt: string;
  prompt: InteractiveSummaryPrompt;
  sentence: string;
  segments: InteractiveSummarySegment[];
  gaps: EvidenceGap[];
  limits: BriefLimit[];
};

export type InteractiveSummaryUnavailable = {
  status: "unavailable";
  configured: false;
  provider: "anthropic" | "openai" | "google";
  model: string;
  generatedAt: string;
  prompt: InteractiveSummaryPrompt;
  reason: {
    code: string;
    message: string;
  };
  gaps: EvidenceGap[];
  limits: BriefLimit[];
};

export type InteractiveSummaryError = {
  status: "error";
  configured: true;
  provider: "anthropic" | "openai" | "google";
  model: string;
  generatedAt: string;
  prompt: InteractiveSummaryPrompt;
  reason: {
    code: string;
    message: string;
  };
  gaps: EvidenceGap[];
  limits: BriefLimit[];
};

export type InteractiveSummaryResponse =
  | InteractiveSummaryReady
  | InteractiveSummaryUnavailable
  | InteractiveSummaryError;
