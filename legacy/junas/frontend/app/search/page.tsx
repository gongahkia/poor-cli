"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { searchCases, listCharges } from "../../lib/api-client";

type SearchResult = {
  case_id: string;
  case_name: string;
  facts: string;
  judgment: string;
  charges: string[];
  relevance_score?: number;
  retrieval_stage: string;
};

type SearchResponse = {
  query: string;
  results: SearchResult[];
  retrieval_info: {
    stages_used: string[];
    bm25_candidates: number;
    dense_candidates: number;
    total_time_ms: number;
  };
};

type ChargesResponse = {
  charges: string[];
};

const defaultQuery =
  "2018年1月15日14时10分许，被告人莫新国酒后驾驶小型轿车被交警查获，经鉴定血液乙醇含量超过醉驾标准。";

function normalizeStages(raw: string | string[] | undefined): string[] {
  if (Array.isArray(raw)) {
    return raw.filter((stage) => stage === "bm25" || stage === "dense" || stage === "rerank");
  }
  if (typeof raw === "string" && raw.trim()) {
    return raw === "bm25" || raw === "dense" || raw === "rerank" ? [raw] : [];
  }
  return ["bm25", "dense", "rerank"];
}

export default function CaseSearchPage() {
  const [query, setQuery] = useState(defaultQuery);
  const [topK, setTopK] = useState(10);
  const [stages, setStages] = useState<string[]>(normalizeStages(undefined));
  const [includeScores, setIncludeScores] = useState(true);

  const [charges, setCharges] = useState<ChargesResponse>({ charges: [] });
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [hasRun, setHasRun] = useState(false);

  useEffect(() => {
    let isActive = true;
    (async () => {
      const data = (await listCharges()) as ChargesResponse;
      if (!isActive) return;
      if (Array.isArray(data?.charges)) {
        setCharges({ charges: data.charges });
      }
    })();
    return () => {
      isActive = false;
    };
  }, []);

  const toggleStage = (stage: "bm25" | "dense" | "rerank") => {
    setStages((current) => (current.includes(stage) ? current.filter((item) => item !== stage) : [...current, stage]));
  };

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalizedQuery = query.trim();
    if (!normalizedQuery) {
      setError("Enter a case fact description before searching.");
      setResult(null);
      setHasRun(true);
      return;
    }
    if (stages.length === 0) {
      setError("Select at least one retrieval stage.");
      setResult(null);
      setHasRun(true);
      return;
    }

    setIsLoading(true);
    setError(null);
    setHasRun(true);
    try {
      const data = await searchCases(normalizedQuery, Math.min(50, Math.max(1, Number(topK) || 10)), stages, includeScores);
      if (data?.error) {
        setError(String(data.error));
        setResult(null);
      } else {
        setResult(data as SearchResponse);
      }
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Search request failed.");
      setResult(null);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <section className="search-grid">
      <div>
        <h2>Case Retrieval (LeCaRD)</h2>
        <p>
          Search Chinese criminal case facts with a three-stage pipeline: BM25 retrieval, optional dense
          retrieval, and optional cross-encoder re-ranking.
        </p>
        <p className="meta-line">
          Dataset note: LeCaRD is used for retrieval benchmarking and research comparison.
        </p>

        <form className="ner-form" onSubmit={onSubmit}>
          <label htmlFor="query">Case fact description (Chinese)</label>
          <textarea id="query" name="query" rows={10} value={query} onChange={(event) => setQuery(event.target.value)} />

          <label htmlFor="top_k">Results</label>
          <input
            id="top_k"
            name="top_k"
            type="number"
            min={1}
            max={50}
            value={topK}
            onChange={(event) => setTopK(Number(event.target.value) || 10)}
          />

          <div className="chip-row">
            <label className="checkbox-row">
              <input
                type="checkbox"
                name="stages"
                value="bm25"
                checked={stages.includes("bm25")}
                onChange={() => toggleStage("bm25")}
              />
              BM25
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                name="stages"
                value="dense"
                checked={stages.includes("dense")}
                onChange={() => toggleStage("dense")}
              />
              Dense
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                name="stages"
                value="rerank"
                checked={stages.includes("rerank")}
                onChange={() => toggleStage("rerank")}
              />
              Re-rank
            </label>
          </div>

          <label className="checkbox-row">
            <input
              type="checkbox"
              name="include_scores"
              value="true"
              checked={includeScores}
              onChange={(event) => setIncludeScores(event.target.checked)}
            />
            Include relevance scores
          </label>

          <button type="submit" disabled={isLoading}>
            {isLoading ? "Searching..." : "Search Cases"}
          </button>
        </form>

        <p>
          <Link href="/search/metrics">View evaluation metrics</Link>
        </p>

        {error ? (
          <article className="result-card">
            <h3>Search unavailable</h3>
            <p>{error}</p>
          </article>
        ) : null}

        {result ? (
          <>
            <h3>Results ({result.results.length})</h3>
            <ul className="results-list">
              {result.results.map((item) => (
                <li key={item.case_id} className="result-card">
                  <div className="result-header">
                    <strong>{item.case_name || item.case_id}</strong>
                    <span className="badge muted">{item.case_id}</span>
                    <span className="badge">{item.retrieval_stage}</span>
                  </div>
                  <p>{item.facts.slice(0, 320)}...</p>
                  <p className="meta-line">{item.judgment.slice(0, 180)}...</p>
                  {item.charges.length > 0 ? (
                    <div className="chip-row">
                      {item.charges.map((charge) => (
                        <span key={`${item.case_id}-${charge}`} className="chip">
                          {charge}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  {typeof item.relevance_score === "number" ? (
                    <p className="meta-line">score: {item.relevance_score.toFixed(4)}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          </>
        ) : hasRun ? (
          <p>No results.</p>
        ) : (
          <p>Submit a query to run retrieval.</p>
        )}
      </div>

      <aside>
        <h3>Pipeline Stats</h3>
        {result ? (
          <ul className="chapter-list">
            <li>stages: {result.retrieval_info.stages_used.join(" -> ")}</li>
            <li>bm25 candidates: {result.retrieval_info.bm25_candidates}</li>
            <li>dense candidates: {result.retrieval_info.dense_candidates}</li>
            <li>time: {result.retrieval_info.total_time_ms} ms</li>
          </ul>
        ) : (
          <p>No run yet.</p>
        )}

        <h3>Known Charges</h3>
        <div className="chip-row">
          {charges.charges.slice(0, 40).map((charge) => (
            <span key={charge} className="chip">
              {charge}
            </span>
          ))}
        </div>
      </aside>
    </section>
  );
}
