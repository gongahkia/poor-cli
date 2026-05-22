export type {
  EvidenceGap,
  PulseFreshness,
  PulseFreshnessStatus,
  PulseProvenanceItem,
  PulseSignal,
  PulseSignalCategory,
  PulseSignalSeverity,
  PulseSnapshot,
  PulseSourceHealth,
  ShieldAuditRecord,
  ShieldAuditStatus,
  ShieldPolicyDecision,
  ShieldReplayMetadata,
  ShieldScannerFinding,
  ShieldRiskLevel,
  ToolErrorPayload,
} from "@swee-sg/shared";

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
