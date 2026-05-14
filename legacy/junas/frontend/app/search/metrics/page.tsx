import Link from "next/link";
import { getSearchMetrics } from "../../../lib/api-server";

type MetricRow = {
  "NDCG@10": number;
  "NDCG@20": number;
  "NDCG@30": number;
  "P@5": number;
  "P@10": number;
  MAP: number;
};

type MetricsResponse = {
  published: Record<string, MetricRow>;
  computed_baselines: Record<string, MetricRow>;
  latest?: {
    baselines?: Record<string, MetricRow>;
    junas?: {
      bm25_only?: MetricRow;
      three_stage?: MetricRow;
    };
  } | null;
};

function renderMetricValue(value: number | undefined): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return value.toFixed(3);
}

export default async function SearchMetricsPage() {
  const metrics = (await getSearchMetrics()) as MetricsResponse | null;
  const latestOpenlex = metrics?.latest?.junas?.three_stage;

  return (
    <section>
      <p>
        <Link href="/search">Back to search</Link>
      </p>
      <h2>Case Retrieval Metrics</h2>
      <p>Published LeCaRD baselines and locally computed retrieval metrics.</p>

      {!metrics ? (
        <article className="result-card">
          <p>Metrics endpoint is unavailable.</p>
        </article>
      ) : (
        <>
          <h3>Published Baselines</h3>
          <table className="comparison-table">
            <thead>
              <tr>
                <th>Method</th>
                <th>NDCG@10</th>
                <th>NDCG@20</th>
                <th>NDCG@30</th>
                <th>P@5</th>
                <th>P@10</th>
                <th>MAP</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(metrics.published).map(([method, row]) => (
                <tr key={`published-${method}`}>
                  <td>{method}</td>
                  <td>{renderMetricValue(row["NDCG@10"])}</td>
                  <td>{renderMetricValue(row["NDCG@20"])}</td>
                  <td>{renderMetricValue(row["NDCG@30"])}</td>
                  <td>{renderMetricValue(row["P@5"])}</td>
                  <td>{renderMetricValue(row["P@10"])}</td>
                  <td>{renderMetricValue(row.MAP)}</td>
                </tr>
              ))}
              {latestOpenlex ? (
                <tr>
                  <td>OPENLEX (THREE-STAGE)</td>
                  <td>{renderMetricValue(latestOpenlex["NDCG@10"])}</td>
                  <td>{renderMetricValue(latestOpenlex["NDCG@20"])}</td>
                  <td>{renderMetricValue(latestOpenlex["NDCG@30"])}</td>
                  <td>{renderMetricValue(latestOpenlex["P@5"])}</td>
                  <td>{renderMetricValue(latestOpenlex["P@10"])}</td>
                  <td>{renderMetricValue(latestOpenlex.MAP)}</td>
                </tr>
              ) : null}
            </tbody>
          </table>

          <h3>Computed Baselines</h3>
          <table className="comparison-table">
            <thead>
              <tr>
                <th>Method</th>
                <th>NDCG@10</th>
                <th>NDCG@20</th>
                <th>NDCG@30</th>
                <th>P@5</th>
                <th>P@10</th>
                <th>MAP</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(metrics.computed_baselines).map(([method, row]) => (
                <tr key={`computed-${method}`}>
                  <td>{method}</td>
                  <td>{renderMetricValue(row["NDCG@10"])}</td>
                  <td>{renderMetricValue(row["NDCG@20"])}</td>
                  <td>{renderMetricValue(row["NDCG@30"])}</td>
                  <td>{renderMetricValue(row["P@5"])}</td>
                  <td>{renderMetricValue(row["P@10"])}</td>
                  <td>{renderMetricValue(row.MAP)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
