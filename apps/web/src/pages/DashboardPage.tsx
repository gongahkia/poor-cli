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
  readonly recommendedAction: string;
};

type PulseSourceHealth = {
  readonly source: string;
  readonly sourceTool: string;
  readonly status: "ready" | "stale" | "gap";
  readonly observedAt: string;
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

export function DashboardPage() {
  const [snapshot, setSnapshot] = useState<PulseSnapshot | null>(null);
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
        const pulsePayload = await pulseResponse.json() as { readonly data?: { readonly snapshot?: PulseSnapshot }; readonly snapshot?: PulseSnapshot };
        const auditPayload = auditResponse.ok
          ? await auditResponse.json() as { readonly records?: readonly ShieldAuditRow[] }
          : { records: [] };
        if (!cancelled) {
          setSnapshot(pulsePayload.data?.snapshot ?? pulsePayload.snapshot ?? null);
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
  const mobilitySignals = sortedSignals.filter((signal) => signal.category === "mobility");
  const weatherSignals = sortedSignals.filter((signal) => signal.category === "weather");

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

      <section>
        <h2>Overview</h2>
        <div className="metric-grid">
          <Metric label="Signals" value={String(snapshot?.signals.length ?? 0)} />
          <Metric label="Watch+" value={String(sortedSignals.filter((signal) => signal.severity !== "info").length)} />
          <Metric label="Sources" value={String(snapshot?.sourceHealth.length ?? 0)} />
          <Metric label="Gaps" value={String(snapshot?.gaps.length ?? 0)} />
        </div>
      </section>

      <section>
        <h2>Mobility</h2>
        <SignalList emptyText="No mobility signals returned yet." signals={mobilitySignals} />
      </section>

      <section>
        <h2>Weather</h2>
        <SignalList emptyText="No weather signals returned yet." signals={weatherSignals} />
      </section>

      <section>
        <h2>Sources</h2>
        <table>
          <thead>
            <tr><th>Source</th><th>Status</th><th>Rows</th><th>Observed</th></tr>
          </thead>
          <tbody>
            {(snapshot?.sourceHealth ?? []).map((source) => (
              <tr key={`${source.sourceTool}:${source.observedAt}`}>
                <td>{source.sourceTool}</td>
                <td>{source.status}</td>
                <td>{source.recordCount}</td>
                <td>{formatTime(source.observedAt)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2>Shield Audit</h2>
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
      </section>
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

function SignalList({ emptyText, signals }: { readonly emptyText: string; readonly signals: readonly PulseSignal[] }) {
  if (signals.length === 0) return <p className="muted">{emptyText}</p>;
  return (
    <div className="signal-list">
      {signals.slice(0, 8).map((signal) => (
        <article className={`signal signal-${signal.severity}`} key={signal.id}>
          <div>
            <h3>{signal.title}</h3>
            <p>{signal.description}</p>
            <p className="muted">{signal.sourceTool} · {formatTime(signal.upstreamTimestamp)}</p>
          </div>
          <strong>{signal.severity}</strong>
        </article>
      ))}
    </div>
  );
}
