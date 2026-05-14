export type BriefSummaryItem = {
  label: string;
  value: unknown;
  source?: string | null;
};

export type EvidenceGap = {
  code: string;
  message: string;
};

export type BriefProvenanceItem = {
  source: string;
  tool: string;
  coverage: string;
  authRequired: boolean;
  recordCount: number;
};

export type BriefFreshnessItem = {
  source: string;
  observedAt: string;
  upstreamTimestamp?: string | null;
};

export type BriefLimit = {
  code: string;
  message: string;
};

export type BriefArtifact = {
  title: string;
  summary: BriefSummaryItem[];
  evidence: BriefSummaryItem[];
  records: Record<string, unknown>;
  gaps: EvidenceGap[];
  provenance: BriefProvenanceItem[];
  freshness: BriefFreshnessItem[];
  limits: BriefLimit[];
};
