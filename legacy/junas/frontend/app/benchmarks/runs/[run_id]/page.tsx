import Link from "next/link";
import { getBenchmarkRun, getBenchmarkLeaderboard } from "../../../../lib/api-server";

const taskOrder = ["ecthr_a", "ecthr_b", "scotus", "eurlex", "ledgar", "unfair_tos", "case_hold"];

type RunScore = {
  task_name: string;
  task: string;
  micro_f1: number | null;
  macro_f1: number | null;
  error: string | null;
};

type RunDetailResponse = {
  run_id: string;
  run_name: string;
  model_name: string;
  status: string;
  requested_tasks: string[];
  results: {
    tasks?: Record<string, Record<string, unknown>>;
    aggregate?: {
      avg_micro_f1?: number;
      avg_macro_f1?: number;
      tasks_completed?: number;
      tasks_total?: number;
    };
  };
  scores: RunScore[];
  error: string | null;
  tasks_completed: number;
  tasks_total: number;
  avg_micro_f1: number | null;
  avg_macro_f1: number | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string | null;
  updated_at: string | null;
};

type LeaderboardResponse = {
  baselines: Array<{
    name: string;
    source: string;
    task_scores: Record<string, number>;
  }>;
  task_labels: Record<string, string>;
};

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  return null;
}

function pointsForRadar(values: number[], radius = 92, center = 110): string {
  const size = values.length;
  if (size === 0) {
    return "";
  }
  return values
    .map((value, index) => {
      const angle = -Math.PI / 2 + (index * 2 * Math.PI) / size;
      const distance = Math.max(0, Math.min(1, value)) * radius;
      const x = center + Math.cos(angle) * distance;
      const y = center + Math.sin(angle) * distance;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

function verticesForRing(size: number, radius: number, center = 110): string {
  return Array.from({ length: size })
    .map((_, index) => {
      const angle = -Math.PI / 2 + (index * 2 * Math.PI) / size;
      const x = center + Math.cos(angle) * radius;
      const y = center + Math.sin(angle) * radius;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

export default async function BenchmarkRunDetailPage({ params }: { params: { run_id: string } }) {
  const runId = params.run_id;
  const rawRun = await getBenchmarkRun(runId);
  const runResult = rawRun?.error
    ? { data: null as RunDetailResponse | null, error: rawRun.error as string }
    : { data: rawRun as RunDetailResponse | null, error: null as string | null };
  const baselines = (await getBenchmarkLeaderboard()) as LeaderboardResponse | null;

  if (!runResult.data) {
    return (
      <section className="benchmarks-grid">
        <div>
          <h2>Benchmark run unavailable</h2>
          <p>{runResult.error ?? "Unknown error"}</p>
          <p>
            <Link href="/benchmarks">Back to benchmarks</Link>
          </p>
        </div>
      </section>
    );
  }

  const run = runResult.data;
  const resultTasks = run.results.tasks ?? {};

  const taskLabels = baselines?.task_labels ?? {};
  const availableTaskIds = taskOrder.filter((taskId) => taskId in resultTasks || run.requested_tasks.includes(taskId));

  const taskRows = availableTaskIds.map((taskId) => {
    const taskPayload = resultTasks[taskId] ?? {};
    const scoreRow = run.scores.find((row) => row.task === taskId);
    const micro = toNumber(taskPayload.micro_f1) ?? scoreRow?.micro_f1 ?? null;
    const macro = toNumber(taskPayload.macro_f1) ?? scoreRow?.macro_f1 ?? null;
    const error = (typeof taskPayload.error === "string" ? taskPayload.error : scoreRow?.error) ?? null;
    return {
      task: taskId,
      task_name:
        (typeof taskPayload.task_name === "string" && taskPayload.task_name) ||
        scoreRow?.task_name ||
        taskLabels[taskId] ||
        taskId,
      micro,
      macro,
      error,
    };
  });

  const baselineCandidate =
    baselines?.baselines.find((entry) => entry.name.includes("Legal-BERT")) ?? baselines?.baselines[0] ?? null;

  const runRadarValues = taskRows.map((row) => row.micro ?? 0);
  const baselineRadarValues = taskRows.map((row) => baselineCandidate?.task_scores[row.task] ?? 0);
  const ringCount = 4;

  const aggregate = run.results.aggregate ?? {};
  const avgMicro = toNumber(aggregate.avg_micro_f1) ?? run.avg_micro_f1;
  const avgMacro = toNumber(aggregate.avg_macro_f1) ?? run.avg_macro_f1;

  return (
    <section className="benchmarks-grid">
      <div>
        <h2>{run.run_name}</h2>
        <p>
          Model: <strong>{run.model_name}</strong>
        </p>
        <p className="meta-line">
          Status: {run.status} | run_id: {run.run_id}
        </p>

        <div className="chip-row">
          <span className="chip">avg μ-F1: {typeof avgMicro === "number" ? avgMicro.toFixed(3) : "-"}</span>
          <span className="chip">avg M-F1: {typeof avgMacro === "number" ? avgMacro.toFixed(3) : "-"}</span>
          <span className="chip">
            progress: {run.tasks_completed}/{run.tasks_total}
          </span>
        </div>

        {run.error ? (
          <article className="result-card">
            <h3>Run error</h3>
            <p>{run.error}</p>
          </article>
        ) : null}

        <h3>Per-task Results</h3>
        <div className="result-grid">
          {taskRows.map((row) => (
            <article key={row.task} className="result-card">
              <h4>{row.task_name}</h4>
              <p className="meta-line">{row.task}</p>

              {row.error ? (
                <p>{row.error}</p>
              ) : (
                <>
                  <div className="distribution-row">
                    <span>μ-F1</span>
                    <strong>{row.micro !== null ? row.micro.toFixed(3) : "-"}</strong>
                  </div>
                  <div className="distribution-track">
                    <div
                      className="distribution-bar"
                      style={{ width: `${Math.round((row.micro ?? 0) * 100)}%`, background: "#16a34a" }}
                    />
                  </div>

                  <div className="distribution-row">
                    <span>M-F1</span>
                    <strong>{row.macro !== null ? row.macro.toFixed(3) : "-"}</strong>
                  </div>
                  <div className="distribution-track">
                    <div
                      className="distribution-bar"
                      style={{ width: `${Math.round((row.macro ?? 0) * 100)}%`, background: "#2563eb" }}
                    />
                  </div>
                </>
              )}
            </article>
          ))}
        </div>
      </div>

      <aside>
        <h3>Model vs Baseline</h3>
        {taskRows.length > 2 ? (
          <div className="radar-wrap">
            <svg viewBox="0 0 220 220" width="220" height="220" role="img" aria-label="Benchmark radar chart">
              {Array.from({ length: ringCount }).map((_, index) => {
                const radius = ((index + 1) / ringCount) * 92;
                return (
                  <polygon
                    key={`ring-${radius}`}
                    points={verticesForRing(taskRows.length, radius)}
                    fill="none"
                    stroke="#cbd5e1"
                    strokeWidth="1"
                  />
                );
              })}

              <polygon points={pointsForRadar(runRadarValues)} fill="rgba(37,99,235,0.22)" stroke="#1d4ed8" strokeWidth="2" />
              <polygon
                points={pointsForRadar(baselineRadarValues)}
                fill="rgba(22,163,74,0.16)"
                stroke="#15803d"
                strokeWidth="2"
                strokeDasharray="4 3"
              />
            </svg>

            <ul className="chapter-list">
              <li>
                <span className="legend-dot legend-run" /> Current run
              </li>
              <li>
                <span className="legend-dot legend-baseline" /> {baselineCandidate?.name ?? "Published baseline"}
              </li>
            </ul>
          </div>
        ) : (
          <p>Radar comparison needs at least 3 task scores.</p>
        )}

        <h3>Timestamps</h3>
        <ul className="chapter-list">
          <li>created: {run.created_at ?? "-"}</li>
          <li>started: {run.started_at ?? "-"}</li>
          <li>completed: {run.completed_at ?? "-"}</li>
          <li>updated: {run.updated_at ?? "-"}</li>
        </ul>

        <p>
          <Link href="/benchmarks">Back to benchmarks</Link>
        </p>
      </aside>
    </section>
  );
}
