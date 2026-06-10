import { type FormEvent, useEffect, useMemo, useState } from "react";
import { getGatewayJson, postGatewayJson } from "@/lib/api/client";

type PulseSignal = {
  readonly id: string;
  readonly category: "mobility" | "weather" | "source_health";
  readonly severity: "info" | "watch" | "disrupted" | "critical";
  readonly title: string;
  readonly description: string;
  readonly source: string;
  readonly sourceTool: string;
  readonly observedAt: string;
  readonly upstreamTimestamp: string | null;
  readonly area?: string;
  readonly freshness?: {
    readonly status: "fresh" | "stale" | "unknown";
    readonly ageSeconds: number | null;
  };
  readonly gaps?: readonly { readonly code: string; readonly message: string }[];
  readonly recommendedAction: string;
};

type PulseSourceHealth = {
  readonly source: string;
  readonly sourceTool: string;
  readonly status: "ready" | "stale" | "gap";
  readonly observedAt: string;
  readonly freshness?: {
    readonly status: "fresh" | "stale" | "unknown";
    readonly upstreamTimestamp: string | null;
    readonly ageSeconds: number | null;
  };
  readonly gaps?: readonly { readonly code: string; readonly message: string }[];
  readonly recordCount: number;
};

type PulseSnapshot = {
  readonly generatedAt: string;
  readonly signals: readonly PulseSignal[];
  readonly sourceHealth: readonly PulseSourceHealth[];
  readonly gaps: readonly { readonly code: string; readonly message: string }[];
};

type ShieldAuditRow = {
  readonly auditId: string;
  readonly toolName: string;
  readonly status: string;
  readonly startedAt: string;
  readonly durationMs: number;
  readonly decision: { readonly decision: string; readonly riskLevel: string; readonly reasonCodes?: readonly string[] };
  readonly outputHash?: string | null;
  readonly rawOutputHash?: string | null;
  readonly runtimeFindings?: readonly {
    readonly code: string;
    readonly severity: string;
    readonly action: string;
  }[];
};

type ShieldApprovalRecord = {
  readonly approvalId: string;
  readonly toolName: string;
  readonly status: "pending" | "approved" | "rejected" | "expired";
  readonly createdAt: string;
  readonly expiresAt: string;
  readonly reviewer: string | null;
  readonly comment: string | null;
  readonly requestHash: string;
  readonly request: unknown;
  readonly risk: {
    readonly status?: string;
    readonly riskScore?: number;
    readonly severity?: string;
    readonly ruleCodes?: readonly string[];
  };
};

type SplunkPolicySimulation = {
  readonly status: "allow" | "approval_required" | "deny";
  readonly riskScore: number;
  readonly severity: string;
  readonly ruleCodes: readonly string[];
  readonly suggestedSaferQuery: string;
  readonly limits?: readonly string[];
};

type SplunkRedTeamMatrixRow = {
  readonly id: string;
  readonly category: string;
  readonly label: string;
  readonly expectedStatus: string;
  readonly simulation: SplunkPolicySimulation;
};

type PolicySimulationPayload = {
  readonly simulation: SplunkPolicySimulation;
  readonly redTeamMatrix: readonly SplunkRedTeamMatrixRow[];
};

type SplunkInvestigationPack = {
  readonly schemaVersion: string;
  readonly investigationId: string;
  readonly status: "completed" | "partial" | "blocked";
  readonly mode: "mock" | "live";
  readonly question: string;
  readonly generatedAt: string;
  readonly searches: readonly {
    readonly label: string;
    readonly query: string;
    readonly status: string;
    readonly auditId: string | null;
    readonly rawOutputHash: string | null;
    readonly outputHash: string | null;
    readonly runtimeFindings: readonly { readonly code: string; readonly severity: string; readonly action: string }[];
    readonly eventCount?: number;
  }[];
  readonly timeline: readonly {
    readonly time: string | null;
    readonly source: string | null;
    readonly host: string | null;
    readonly event: string;
    readonly risk: string | null;
    readonly searchLabel: string;
  }[];
  readonly findingSummary?: {
    readonly total: number;
    readonly redacted: number;
    readonly neutralized: number;
    readonly critical: number;
  };
  readonly nextAnalystChecks: readonly string[];
  readonly limits: readonly string[];
};

type PulseShield = {
  readonly auditId: string;
  readonly decision: { readonly decision: string; readonly riskLevel: string; readonly mode?: string; readonly reasonCodes?: readonly string[] };
};

type GatewayToolPayload<T> = {
  readonly data?: T;
};

const severityRank: Record<PulseSignal["severity"], number> = {
  critical: 0,
  disrupted: 1,
  watch: 2,
  info: 3,
};

const formatTime = (value: string | null): string => {
  if (value === null) return "No upstream timestamp";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

const formatDateTime = (value: string | null): string => {
  if (value === null) return "No timestamp";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
};

const plural = (count: number, singular: string, pluralForm = `${singular}s`): string =>
  `${count} ${count === 1 ? singular : pluralForm}`;

const shortId = (value: string): string => value.slice(0, 8);
const severityOrder: Readonly<Record<string, number>> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

const shortHash = (label: string, value: string | null | undefined): string =>
  value === null || value === undefined ? `${label}:none` : `${label}:${value.slice(0, 8)}`;

export function DashboardPage() {
  const [snapshot, setSnapshot] = useState<PulseSnapshot | null>(null);
  const [pulseShield, setPulseShield] = useState<PulseShield | null>(null);
  const [audits, setAudits] = useState<readonly ShieldAuditRow[]>([]);
  const [approvals, setApprovals] = useState<readonly ShieldApprovalRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [opsError, setOpsError] = useState<string | null>(null);
  const [refreshCount, setRefreshCount] = useState(0);
  const [simulatorQuery, setSimulatorQuery] = useState("index=security failed login");
  const [policySimulation, setPolicySimulation] = useState<PolicySimulationPayload | null>(null);
  const [policyLoading, setPolicyLoading] = useState(false);
  const [packQuestion, setPackQuestion] = useState("Investigate recent failed login activity and possible prompt injection.");
  const [investigationPack, setInvestigationPack] = useState<SplunkInvestigationPack | null>(null);
  const [packLoading, setPackLoading] = useState(false);

  const refreshApprovals = async () => {
    const payload = await getGatewayJson<{ readonly records?: readonly ShieldApprovalRecord[] }>("/api/v1/shield/approvals", { limit: "8" });
    setApprovals(payload.records ?? []);
  };

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [pulsePayload, auditPayload, approvalPayload] = await Promise.all([
          getGatewayJson<{ readonly data?: { readonly snapshot?: PulseSnapshot }; readonly snapshot?: PulseSnapshot; readonly shield?: PulseShield }>("/api/v1/pulse/snapshot"),
          getGatewayJson<{ readonly records?: readonly ShieldAuditRow[] }>("/api/v1/shield/audits", { limit: "12" }).catch(() => ({ records: [] })),
          getGatewayJson<{ readonly records?: readonly ShieldApprovalRecord[] }>("/api/v1/shield/approvals", { limit: "8" }).catch(() => ({ records: [] })),
        ]);
        if (!cancelled) {
          setSnapshot(pulsePayload.data?.snapshot ?? pulsePayload.snapshot ?? null);
          setPulseShield(pulsePayload.shield ?? null);
          setAudits(auditPayload.records ?? []);
          setApprovals(approvalPayload.records ?? []);
          setError(null);
        }
      } catch (caught) {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "Pulse snapshot failed.");
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [refreshCount]);

  const runPolicySimulation = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPolicyLoading(true);
    setOpsError(null);
    try {
      const payload = await postGatewayJson<GatewayToolPayload<PolicySimulationPayload>>("/api/v1/shield/policy/simulate", {
        query: simulatorQuery,
        earliest: "-24h",
        latest: "now",
        limit: 25,
      });
      setPolicySimulation(payload.data ?? null);
    } catch (caught) {
      setOpsError(caught instanceof Error ? caught.message : "Policy simulation failed.");
    } finally {
      setPolicyLoading(false);
    }
  };

  const runInvestigationPack = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPackLoading(true);
    setOpsError(null);
    try {
      const payload = await postGatewayJson<GatewayToolPayload<SplunkInvestigationPack>>("/api/v1/shield/splunk/investigation-pack", {
        question: packQuestion,
        mode: "mock",
        limit: 20,
        format: "json",
      });
      setInvestigationPack(payload.data ?? null);
      setRefreshCount((count) => count + 1);
    } catch (caught) {
      setOpsError(caught instanceof Error ? caught.message : "Investigation pack failed.");
    } finally {
      setPackLoading(false);
    }
  };

  const decideApproval = async (approvalId: string, decision: "approved" | "rejected") => {
    setOpsError(null);
    try {
      await postGatewayJson<{ readonly record: ShieldApprovalRecord }>(`/api/v1/shield/approvals/${encodeURIComponent(approvalId)}/decide`, {
        decision,
        reviewer: "dashboard",
      });
      await refreshApprovals();
    } catch (caught) {
      setOpsError(caught instanceof Error ? caught.message : "Approval update failed.");
    }
  };

  const sortedSignals = useMemo(
    () => [...(snapshot?.signals ?? [])].sort((left, right) => severityRank[left.severity] - severityRank[right.severity]),
    [snapshot],
  );
  const actionSignals = sortedSignals.filter((signal) => signal.severity !== "info");
  const mobilitySignals = actionSignals.filter((signal) => signal.category === "mobility");
  const weatherSignals = actionSignals.filter((signal) => signal.category === "weather");
  const normalWeatherSignals = sortedSignals.filter((signal) => signal.category === "weather" && signal.severity === "info");
  const sourceIssues = (snapshot?.sourceHealth ?? []).filter((source) => source.status !== "ready");
  const coverageGapCount = Math.max(sourceIssues.length, snapshot?.gaps.length ?? 0);
  const readySources = (snapshot?.sourceHealth ?? []).filter((source) => source.status === "ready");
  const latestObservedAt = [...(snapshot?.sourceHealth ?? [])]
    .map((source) => source.observedAt)
    .sort()
    .at(-1) ?? snapshot?.generatedAt ?? null;
  const criticalCount = sortedSignals.filter((signal) => signal.severity === "critical").length;
  const disruptedCount = sortedSignals.filter((signal) => signal.severity === "disrupted").length;
  const watchCount = sortedSignals.filter((signal) => signal.severity === "watch").length;
  const cityState = criticalCount > 0
    ? "Critical disruption"
    : disruptedCount > 0
      ? "Disrupted"
      : watchCount > 0
        ? "Watch"
        : coverageGapCount > 0
          ? "Normal signals, limited coverage"
          : "Normal";
  const cityStateDetail = actionSignals.length > 0
    ? `${plural(actionSignals.length, "signal")} need review across mobility and weather.`
    : coverageGapCount > 0
      ? `No active disruptions detected, but ${plural(coverageGapCount, "coverage gap")} ${coverageGapCount === 1 ? "needs" : "need"} attention before trusting mobility coverage.`
      : "No active disruptions detected across checked mobility and weather sources.";
  const confidenceText = coverageGapCount === 0
    ? "All checked sources ready"
    : `${plural(coverageGapCount, "coverage gap")} ${coverageGapCount === 1 ? "limits" : "limit"} confidence`;

  return (
    <main>
      <header className="app-header">
        <div>
          <h1>Swee SG</h1>
          <p className="muted">Live Singapore public-data signals governed by Swee Shield.</p>
        </div>
        <button onClick={() => setRefreshCount((count) => count + 1)} type="button">Refresh</button>
      </header>

      {error === null ? null : <p className="error" role="alert">{error}</p>}

      <section className={`status-panel status-${cityState.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}>
        <div className="status-copy">
          <span className="eyebrow">What matters now</span>
          <h2>{cityState}</h2>
          <p>{cityStateDetail}</p>
          <p className="muted">Last refreshed {formatDateTime(latestObservedAt)}.</p>
        </div>
        <div className="metric-grid">
          <Metric label="Needs review" value={String(actionSignals.length)} />
          <Metric label="Quiet signals" value={String(normalWeatherSignals.length)} />
          <Metric label="Ready sources" value={`${readySources.length}/${snapshot?.sourceHealth.length ?? 0}`} />
          <Metric label="Coverage gaps" value={String(coverageGapCount)} />
        </div>
      </section>

      <section className="takeaway-grid" aria-label="Dashboard takeaways">
        <Takeaway
          label="City state"
          value={actionSignals.length === 0 ? "No disruptions detected" : `${plural(actionSignals.length, "active signal")}`}
        />
        <Takeaway
          label="Confidence"
          value={confidenceText}
        />
        <Takeaway
          label="Weather"
          value={weatherSignals.length === 0
            ? `${plural(normalWeatherSignals.length, "normal area")} hidden`
            : `${plural(weatherSignals.length, "weather signal")} ${weatherSignals.length === 1 ? "needs" : "need"} review`}
        />
      </section>

      <section className="runtime-evidence">
        <div>
          <h2>Runtime Evidence</h2>
          <p className="muted">Pulse values stay deterministic; Shield records the governed call that produced this view.</p>
        </div>
        <div className="evidence-grid">
          <EvidenceItem label="Pulse audit" value={pulseShield?.auditId ?? "No audit returned"} />
          <EvidenceItem
            label="Shield decision"
            value={pulseShield === null ? "unknown" : `${pulseShield.decision.decision} / ${pulseShield.decision.riskLevel}`}
          />
          <EvidenceItem
            label="Replay route"
            value={pulseShield === null ? "Unavailable" : `/api/v1/shield/replay/${pulseShield.auditId}`}
          />
        </div>
      </section>

      {opsError === null ? null : <p className="error" role="alert">{opsError}</p>}

      <section>
        <h2>Security Workbench</h2>
        <div className="ops-grid">
          <InvestigationPackPanel
            pack={investigationPack}
            question={packQuestion}
            loading={packLoading}
            onQuestionChange={setPackQuestion}
            onSubmit={runInvestigationPack}
          />
          <PolicySimulatorPanel
            query={simulatorQuery}
            result={policySimulation}
            loading={policyLoading}
            onQueryChange={setSimulatorQuery}
            onSubmit={runPolicySimulation}
          />
        </div>
      </section>

      <section className={coverageGapCount === 0 ? "source-gaps source-gaps-clear" : "source-gaps"}>
        <div>
          <h2>Coverage Gaps</h2>
          <p className="muted">
            {coverageGapCount === 0
              ? "No source gaps are currently limiting the Pulse view."
              : "These source gaps are more important than quiet weather rows because they limit what Swee Pulse can conclude."}
          </p>
        </div>
        <SourceIssueList sources={sourceIssues} gaps={snapshot?.gaps ?? []} />
      </section>

      <section>
        <h2>Needs Attention</h2>
        <div className="signal-columns">
          <div>
            <h3>Mobility</h3>
            <SignalList emptyText="No mobility disruptions detected from available sources." signals={mobilitySignals} />
          </div>
          <div>
            <h3>Weather</h3>
            <SignalList emptyText="No watch-level weather signals. Normal area forecasts are collapsed below." signals={weatherSignals} />
          </div>
        </div>
      </section>

      <details>
        <summary>Normal Weather Coverage ({normalWeatherSignals.length})</summary>
        <SignalList emptyText="No normal weather rows returned." signals={normalWeatherSignals} compact />
      </details>

      <section>
        <h2>Source Health</h2>
        <SourceTable sources={snapshot?.sourceHealth ?? []} />
      </section>

      <details className="ops-details">
        <summary>Ops: Human Approvals ({approvals.length})</summary>
        <ApprovalQueue approvals={approvals} onDecide={decideApproval} />
      </details>

      <details className="ops-details">
        <summary>Ops: Shield Audit ({audits.length})</summary>
        <ShieldAuditTable audits={audits} />
      </details>
    </main>
  );
}

function Metric({ label, value }: { readonly label: string; readonly value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Takeaway({ label, value }: { readonly label: string; readonly value: string }) {
  return (
    <article className="takeaway">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function EvidenceItem({ label, value }: { readonly label: string; readonly value: string }) {
  return (
    <article className="evidence-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function InvestigationPackPanel({
  loading,
  onQuestionChange,
  onSubmit,
  pack,
  question,
}: {
  readonly loading: boolean;
  readonly onQuestionChange: (value: string) => void;
  readonly onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  readonly pack: SplunkInvestigationPack | null;
  readonly question: string;
}) {
  return (
    <article className="ops-panel">
      <form onSubmit={onSubmit}>
        <h3>Investigation Pack</h3>
        <label htmlFor="splunk-pack-question">Question</label>
        <textarea
          id="splunk-pack-question"
          onChange={(event) => onQuestionChange(event.target.value)}
          rows={3}
          value={question}
        />
        <button disabled={loading || question.trim() === ""} type="submit">{loading ? "Running" : "Run Mock Pack"}</button>
      </form>
      {pack === null ? null : (
        <div className="ops-result">
          <div className="evidence-grid">
            <EvidenceItem label="Investigation" value={`${shortId(pack.investigationId)} / ${pack.status}`} />
            <EvidenceItem label="Timeline" value={`${pack.timeline.length} events`} />
            <EvidenceItem label="Findings" value={`${pack.findingSummary?.total ?? 0} runtime`} />
          </div>
          <table>
            <thead>
              <tr><th>Search</th><th>Status</th><th>Audit</th><th>Findings</th></tr>
            </thead>
            <tbody>
              {pack.searches.map((search) => (
                <tr key={search.label}>
                  <td><strong>{search.label}</strong><span>{search.query}</span></td>
                  <td><strong>{search.status}</strong><span>{search.eventCount ?? 0} events</span></td>
                  <td><strong>{search.auditId === null ? "none" : shortId(search.auditId)}</strong><span>{shortHash("post", search.outputHash)}</span></td>
                  <td><strong>{search.runtimeFindings.length}</strong><span>{search.runtimeFindings.slice(0, 2).map((finding) => finding.code).join(", ") || "none"}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          <TimelineTable timeline={pack.timeline} />
        </div>
      )}
    </article>
  );
}

function PolicySimulatorPanel({
  loading,
  onQueryChange,
  onSubmit,
  query,
  result,
}: {
  readonly loading: boolean;
  readonly onQueryChange: (value: string) => void;
  readonly onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  readonly query: string;
  readonly result: PolicySimulationPayload | null;
}) {
  return (
    <article className="ops-panel">
      <form onSubmit={onSubmit}>
        <h3>Policy Simulator</h3>
        <label htmlFor="splunk-policy-query">SPL</label>
        <textarea
          id="splunk-policy-query"
          onChange={(event) => onQueryChange(event.target.value)}
          rows={3}
          value={query}
        />
        <button disabled={loading || query.trim() === ""} type="submit">{loading ? "Simulating" : "Simulate"}</button>
      </form>
      {result === null ? null : (
        <div className="ops-result">
          <div className="evidence-grid">
            <EvidenceItem label="Decision" value={`${result.simulation.status} / ${result.simulation.severity}`} />
            <EvidenceItem label="Risk score" value={String(result.simulation.riskScore)} />
            <EvidenceItem label="Rules" value={result.simulation.ruleCodes.join(", ")} />
          </div>
          <p className="muted">Safer query: {result.simulation.suggestedSaferQuery}</p>
          <table>
            <thead>
              <tr><th>Case</th><th>Expected</th><th>Actual</th><th>Rules</th></tr>
            </thead>
            <tbody>
              {result.redTeamMatrix.map((row) => (
                <tr key={row.id}>
                  <td><strong>{row.label}</strong><span>{row.category}</span></td>
                  <td>{row.expectedStatus}</td>
                  <td>{row.simulation.status}</td>
                  <td>{row.simulation.ruleCodes.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </article>
  );
}

function TimelineTable({ timeline }: { readonly timeline: SplunkInvestigationPack["timeline"] }) {
  if (timeline.length === 0) return <p className="muted">No timeline events returned.</p>;
  return (
    <table>
      <thead>
        <tr><th>Time</th><th>Host</th><th>Event</th><th>Search</th></tr>
      </thead>
      <tbody>
        {timeline.slice(0, 8).map((event, index) => (
          <tr key={`${event.searchLabel}:${event.time ?? index}`}>
            <td>{formatDateTime(event.time)}</td>
            <td><strong>{event.host ?? "unknown"}</strong><span>{event.source ?? "unknown source"}</span></td>
            <td>{event.event}</td>
            <td><strong>{event.searchLabel}</strong><span>{event.risk ?? "unknown risk"}</span></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ApprovalQueue({
  approvals,
  onDecide,
}: {
  readonly approvals: readonly ShieldApprovalRecord[];
  readonly onDecide: (approvalId: string, decision: "approved" | "rejected") => void;
}) {
  if (approvals.length === 0) return <p className="muted">No Shield approval requests returned yet.</p>;
  return (
    <table>
      <thead>
        <tr><th>Tool</th><th>Status</th><th>Risk</th><th>Request</th><th>Decision</th></tr>
      </thead>
      <tbody>
        {approvals.map((approval) => (
          <tr key={approval.approvalId}>
            <td><strong>{approval.toolName}</strong><span>{shortId(approval.approvalId)}</span></td>
            <td><strong>{approval.status}</strong><span>expires {formatDateTime(approval.expiresAt)}</span></td>
            <td><strong>{approval.risk.status ?? "unknown"} / {approval.risk.severity ?? "unknown"}</strong><span>{approval.risk.ruleCodes?.slice(0, 2).join(", ") ?? "none"}</span></td>
            <td><strong>{approval.requestHash.slice(0, 12)}</strong><span>{JSON.stringify(approval.request)}</span></td>
            <td>
              {approval.status === "pending" ? (
                <span className="button-row">
                  <button onClick={() => onDecide(approval.approvalId, "approved")} type="button">Approve</button>
                  <button onClick={() => onDecide(approval.approvalId, "rejected")} type="button">Reject</button>
                </span>
              ) : (
                <strong>{approval.reviewer ?? "recorded"}</strong>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SignalList({ compact = false, emptyText, signals }: { readonly compact?: boolean; readonly emptyText: string; readonly signals: readonly PulseSignal[] }) {
  if (signals.length === 0) return <p className="muted">{emptyText}</p>;
  return (
    <div className={compact ? "signal-list signal-list-compact" : "signal-list"}>
      {signals.slice(0, 8).map((signal) => (
        <article className={`signal signal-${signal.severity}`} key={signal.id}>
          <div>
            <h3>{signal.title}</h3>
            <p>{signal.description}</p>
            {compact ? null : <p className="action-text">{signal.recommendedAction}</p>}
            <p className="muted">
              {signal.sourceTool} · freshness {signal.freshness?.status ?? "unknown"} · upstream {formatTime(signal.upstreamTimestamp)} · gaps {signal.gaps?.length ?? 0}
            </p>
          </div>
          <strong>{signal.severity}</strong>
        </article>
      ))}
      {signals.length > 8 ? <p className="muted">Showing 8 of {signals.length} quiet rows.</p> : null}
    </div>
  );
}

function SourceIssueList({
  gaps,
  sources,
}: {
  readonly gaps: readonly { readonly code: string; readonly message: string }[];
  readonly sources: readonly PulseSourceHealth[];
}) {
  if (sources.length === 0 && gaps.length === 0) {
    return <p className="source-ok">Coverage is complete for checked sources.</p>;
  }

  return (
    <div className="issue-list">
      {sources.map((source) => (
        <article className="issue" key={`${source.sourceTool}:${source.observedAt}`}>
          <strong>{source.sourceTool}</strong>
          <span>
            {source.status} · freshness {source.freshness?.status ?? "unknown"} · {source.recordCount} rows · observed {formatTime(source.observedAt)}
          </span>
          {(source.gaps ?? []).slice(0, 2).map((gap) => (
            <span key={gap.code}>{gap.code}: {gap.message}</span>
          ))}
        </article>
      ))}
      {gaps.slice(0, 6).map((gap) => (
        <article className="issue" key={gap.code}>
          <strong>{gap.code}</strong>
          <span>{gap.message}</span>
        </article>
      ))}
    </div>
  );
}

function SourceTable({ sources }: { readonly sources: readonly PulseSourceHealth[] }) {
  return (
    <div className="source-health-list">
      {sources.map((source) => (
        <article className="source-health-card" key={`${source.sourceTool}:${source.observedAt}`}>
          <div>
            <strong>{source.sourceTool}</strong>
            <span>{source.recordCount} rows · observed {formatTime(source.observedAt)}</span>
            <span>freshness {source.freshness?.status ?? "unknown"} · upstream {formatTime(source.freshness?.upstreamTimestamp ?? null)} · gaps {source.gaps?.length ?? 0}</span>
          </div>
          <span className={`status-pill status-pill-${source.status}`}>{source.status}</span>
        </article>
      ))}
    </div>
  );
}

export function ShieldAuditTable({ audits }: { readonly audits: readonly ShieldAuditRow[] }) {
  if (audits.length === 0) return <p className="muted">No Shield audit rows returned yet.</p>;
  return (
    <table>
      <thead>
        <tr><th>Tool</th><th>Decision</th><th>Findings</th><th>Status</th><th>Audit</th></tr>
      </thead>
      <tbody>
        {audits.map((audit) => {
          const findings = audit.runtimeFindings ?? [];
          const reasonCodes = audit.decision.reasonCodes ?? [];
          const topFinding = findings
            .slice()
            .sort((left, right) => (severityOrder[left.severity] ?? 9) - (severityOrder[right.severity] ?? 9))[0];
          const hashSummary = `${shortHash("raw", audit.rawOutputHash)} · ${shortHash("post", audit.outputHash)}`;
          return (
            <tr key={audit.auditId}>
              <td>{audit.toolName}</td>
              <td>
                <strong>{audit.decision.decision} / {audit.decision.riskLevel}</strong>
                <span>{reasonCodes.slice(0, 2).join(", ") || "default_allow"}</span>
              </td>
              <td>
                <strong>{findings.length} {topFinding === undefined ? "none" : `${topFinding.severity} ${topFinding.action}`}</strong>
                <span>{findings.slice(0, 2).map((finding) => finding.code).join(", ") || "none"}</span>
              </td>
              <td>
                <strong>{audit.status}</strong>
                <span>{audit.durationMs}ms · {hashSummary}</span>
              </td>
              <td>
                <strong>{shortId(audit.auditId)}</strong>
                <span>{formatDateTime(audit.startedAt)}</span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
