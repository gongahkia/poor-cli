import Link from "next/link";
import { listBenchmarkTasks, listBenchmarkRuns, getBenchmarkLeaderboard, startBenchmarkRun } from "../../lib/api-server";

const orderedTasks = [
  "ecthr_a",
  "ecthr_b",
  "scotus",
  "eurlex",
  "ledgar",
  "unfair_tos",
  "case_hold",
];

type BenchmarkTask = {
  name: string;
  task: string;
  task_type: string;
  num_labels: number;
};

type RunSummary = {
  run_id: string;
  run_name: string;
  model_name: string;
  status: string;
  tasks_completed: number;
  tasks_total: number;
  avg_micro_f1: number | null;
  avg_macro_f1: number | null;
  completed_at: string | null;
  is_published_baseline: boolean;
};

type LeaderboardEntry = {
  rank?: number;
  run_id?: string;
  run_name: string;
  model_name?: string;
  avg_micro_f1?: number;
  avg_macro_f1?: number;
  task_scores: Record<string, number>;
};

type LeaderboardResponse = {
  leaderboard: LeaderboardEntry[];
  baselines: Array<{
    name: string;
    source: string;
    task_scores: Record<string, number>;
  }>;
  task_labels: Record<string, string>;
};

function normalizeSelectedTasks(raw: string | string[] | undefined): string[] {
  if (Array.isArray(raw)) {
    return raw.filter((task) => orderedTasks.includes(task));
  }
  if (typeof raw === "string" && orderedTasks.includes(raw)) {
    return [raw];
  }
  return [...orderedTasks];
}

function scoreClass(value: number | undefined): string {
  if (typeof value !== "number") {
    return "score-none";
  }
  if (value >= 0.85) {
    return "score-high";
  }
  if (value >= 0.75) {
    return "score-mid";
  }
  return "score-low";
}

async function fetchTasks(): Promise<BenchmarkTask[]> {
  const data = await listBenchmarkTasks();
  return (data as any)?.tasks ?? [];
}

async function fetchRuns(): Promise<RunSummary[]> {
  const data = await listBenchmarkRuns();
  return (data as any)?.runs ?? [];
}

async function fetchLeaderboard(): Promise<LeaderboardResponse | null> {
  const data = await getBenchmarkLeaderboard();
  return data as LeaderboardResponse | null;
}

async function queueRun(
  modelName: string,
  runName: string,
  tasks: string[],
): Promise<{ result: { run_id: string; status: string; message: string } | null; error: string | null }> {
  const data = await startBenchmarkRun(modelName, runName, tasks);
  if (data?.error) return { result: null, error: data.error };
  const payload = data as any;
  return {
    result: {
      run_id: payload.run_id ?? "",
      status: payload.status ?? "pending",
      message: payload.message ?? "Benchmark run queued",
    },
    error: null,
  };
}

export default async function BenchmarksPage({
  searchParams,
}: {
  searchParams?: {
    run?: "0" | "1";
    model_name?: string;
    run_name?: string;
    tasks?: string | string[];
  };
}) {
  const modelName = (searchParams?.model_name ?? "nlpaueb/legal-bert-base-uncased").trim();
  const runName = (searchParams?.run_name ?? "legal-bert-baseline").trim();
  const selectedTasks = normalizeSelectedTasks(searchParams?.tasks);
  const shouldRun = searchParams?.run === "1";

  const runResult =
    shouldRun && modelName && runName
      ? await queueRun(modelName, runName, selectedTasks)
      : { result: null as { run_id: string; status: string; message: string } | null, error: null as string | null };

  const [tasks, runs, leaderboard] = await Promise.all([fetchTasks(), fetchRuns(), fetchLeaderboard()]);
  const activeRuns = runs.filter((run) => run.status === "pending" || run.status === "running");
  const taskLabels = leaderboard?.task_labels ?? {};
  const knownTaskIds = Object.keys(taskLabels).length > 0 ? Object.keys(taskLabels) : orderedTasks;

  return (
    <section className="benchmarks-grid">
      <div>
        <h2>LexGLUE Benchmark Dashboard</h2>
        <p>Queue benchmark runs, compare model scores, and track progress across all seven LexGLUE tasks.</p>

        <form method="get" action="/benchmarks" className="ner-form">
          <input type="hidden" name="run" value="1" />

          <label htmlFor="run_name">Run name</label>
          <input id="run_name" name="run_name" defaultValue={runName} required />

          <label htmlFor="model_name">Model (HF id or local path)</label>
          <input id="model_name" name="model_name" defaultValue={modelName} required />

          <div className="chip-row">
            {(tasks.length > 0 ? tasks : orderedTasks.map((task) => ({ task, name: task, task_type: "unknown", num_labels: 0 }))).map(
              (task) => (
                <label key={task.task} className="checkbox-row">
                  <input type="checkbox" name="tasks" value={task.task} defaultChecked={selectedTasks.includes(task.task)} />
                  {task.name}
                </label>
              ),
            )}
          </div>

          <button type="submit">Queue Benchmark Run</button>
        </form>

        {runResult.error ? (
          <article className="result-card">
            <h3>Queue failed</h3>
            <p>{runResult.error}</p>
          </article>
        ) : null}

        {runResult.result ? (
          <article className="result-card">
            <h3>Run queued</h3>
            <p>{runResult.result.message}</p>
            <p className="meta-line">run_id: {runResult.result.run_id}</p>
          </article>
        ) : null}

        <h3>Leaderboard</h3>
        {leaderboard ? (
          <div className="leaderboard-wrap">
            <table className="leaderboard-table">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Run</th>
                  <th>Model</th>
                  <th>Avg μ-F1</th>
                  {knownTaskIds.map((taskId) => (
                    <th key={taskId}>{taskLabels[taskId] ?? taskId}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {leaderboard.leaderboard.map((entry) => (
                  <tr key={entry.run_id ?? entry.run_name}>
                    <td>{entry.rank ?? "-"}</td>
                    <td>
                      {entry.run_id ? <Link href={`/benchmarks/runs/${entry.run_id}`}>{entry.run_name}</Link> : entry.run_name}
                    </td>
                    <td>{entry.model_name ?? "-"}</td>
                    <td>{typeof entry.avg_micro_f1 === "number" ? entry.avg_micro_f1.toFixed(3) : "-"}</td>
                    {knownTaskIds.map((taskId) => {
                      const score = entry.task_scores[taskId];
                      return (
                        <td key={`${entry.run_name}-${taskId}`} className={scoreClass(score)}>
                          {typeof score === "number" ? score.toFixed(3) : "-"}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>

            <h4>Published Baselines</h4>
            <table className="leaderboard-table baseline-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Source</th>
                  {knownTaskIds.map((taskId) => (
                    <th key={`baseline-${taskId}`}>{taskLabels[taskId] ?? taskId}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {leaderboard.baselines.map((baseline) => (
                  <tr key={baseline.name}>
                    <td>{baseline.name}</td>
                    <td>{baseline.source}</td>
                    {knownTaskIds.map((taskId) => {
                      const score = baseline.task_scores[taskId];
                      return <td key={`${baseline.name}-${taskId}`}>{typeof score === "number" ? score.toFixed(3) : "-"}</td>;
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p>Leaderboard unavailable.</p>
        )}
      </div>

      <aside>
        <h3>Active Runs</h3>
        {activeRuns.length === 0 ? (
          <p>No benchmark run in progress.</p>
        ) : (
          <ul className="chapter-list">
            {activeRuns.map((run) => {
              const percent = run.tasks_total > 0 ? Math.round((run.tasks_completed / run.tasks_total) * 100) : 0;
              return (
                <li key={run.run_id} className="result-card">
                  <strong>{run.run_name}</strong>
                  <p className="meta-line">{run.model_name}</p>
                  <p className="meta-line">
                    {run.tasks_completed}/{run.tasks_total} tasks ({percent}%)
                  </p>
                  <div className="progress-track">
                    <div className="progress-fill" style={{ width: `${percent}%` }} />
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        <h3>Recent Runs</h3>
        <ul className="chapter-list">
          {runs.slice(0, 12).map((run) => (
            <li key={run.run_id}>
              <Link href={`/benchmarks/runs/${run.run_id}`}>{run.run_name}</Link>
              <span className="meta-line"> {run.status}</span>
            </li>
          ))}
        </ul>
      </aside>
    </section>
  );
}
