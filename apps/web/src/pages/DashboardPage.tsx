import { useEffect, useMemo, useState } from "react";

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
  readonly decision: { readonly decision: string; readonly riskLevel: string };
};

type PulseShield = {
  readonly auditId: string;
  readonly decision: { readonly decision: string; readonly riskLevel: string; readonly mode?: string; readonly reasonCodes?: readonly string[] };
};

const apiBase = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:3000";

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

export function DashboardPage() {
  const [snapshot, setSnapshot] = useState<PulseSnapshot | null>(null);
  const [pulseShield, setPulseShield] = useState<PulseShield | null>(null);
  const [audits, setAudits] = useState<readonly ShieldAuditRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [refreshCount, setRefreshCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [pulseResponse, auditResponse] = await Promise.all([
          fetch(`${apiBase}/api/v1/pulse/snapshot`),
          fetch(`${apiBase}/api/v1/shield/audits?limit=12`),
        ]);
        if (!pulseResponse.ok) throw new Error(`Pulse API returned ${pulseResponse.status}`);
        const pulsePayload = await pulseResponse.json() as { readonly data?: { readonly snapshot?: PulseSnapshot }; readonly snapshot?: PulseSnapshot; readonly shield?: PulseShield };
        const auditPayload = auditResponse.ok
          ? await auditResponse.json() as { readonly records?: readonly ShieldAuditRow[] }
          : { records: [] };
        if (!cancelled) {
          setSnapshot(pulsePayload.data?.snapshot ?? pulsePayload.snapshot ?? null);
          setPulseShield(pulsePayload.shield ?? null);
          setAudits(auditPayload.records ?? []);
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

function ShieldAuditTable({ audits }: { readonly audits: readonly ShieldAuditRow[] }) {
  if (audits.length === 0) return <p className="muted">No Shield audit rows returned yet.</p>;
  return (
    <table>
      <thead>
        <tr><th>Tool</th><th>Decision</th><th>Status</th><th>Duration</th></tr>
      </thead>
      <tbody>
        {audits.map((audit) => (
          <tr key={audit.auditId}>
            <td>{audit.toolName}</td>
            <td>{audit.decision.decision} / {audit.decision.riskLevel}</td>
            <td>{audit.status}</td>
            <td>{audit.durationMs}ms</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
