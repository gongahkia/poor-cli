export type {
  BriefArtifact,
  BriefFreshnessItem,
  BriefLimit,
  BriefProvenanceItem,
  BriefSummaryItem,
  EvidenceGap,
  QueryOutcome,
  ToolErrorPayload,
} from "@dude/shared";

export type GatewayHealth = {
  readonly status: "ok" | "degraded" | string;
  readonly readiness?: "ready" | "degraded" | "failing" | string;
  readonly tools: number;
  readonly runtime?: {
    readonly startedAt?: string;
    readonly uptimeSeconds?: number;
    readonly observedAt?: string;
  };
  readonly services?: Readonly<Record<string, unknown>>;
};
