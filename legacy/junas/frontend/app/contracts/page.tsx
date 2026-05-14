"use client";

import type { FormEvent } from "react";
import { useState } from "react";
import { classifyContract as classifyContractApi, scanToS as scanToSApi } from "../../lib/api-client";

type ClauseResult = {
  segment_index: number;
  text: string;
  start: number;
  end: number;
  clause_type: string;
  confidence: number;
  alternatives: Array<{ type: string; confidence: number }>;
};

type ContractClassifyResponse = {
  total_clauses: number;
  clauses: ClauseResult[];
  clause_distribution: Record<string, number>;
};

type ToSSentence = {
  index: number;
  text: string;
  is_unfair: boolean;
  unfair_categories: Array<{ category: string; confidence: number }>;
};

type ToSResponse = {
  total_sentences: number;
  unfair_count: number;
  fair_count: number;
  severity_score: number;
  sentences: ToSSentence[];
  summary: Record<string, number>;
};

const sampleContract = `SECTION 1. DEFINITIONS. As used in this Agreement, "Confidential Information" means all non-public business information.

SECTION 2. GOVERNING LAW. This Agreement shall be governed by the laws of the State of New York.

SECTION 3. INDEMNIFICATION. The Company shall indemnify and hold harmless the Contractor against all claims arising from performance.`;

const sampleToS = `By using our service, you agree to these terms. We may terminate your account at any time without notice. We may update these terms unilaterally by posting changes on our website.`;

export default function ContractsPage() {
  const [tab, setTab] = useState<"classify" | "tos">("classify");
  const [text, setText] = useState(sampleContract);
  const [topKTypes, setTopKTypes] = useState(3);
  const [threshold, setThreshold] = useState(0.5);

  const [classifyResult, setClassifyResult] = useState<ContractClassifyResponse | null>(null);
  const [tosResult, setTosResult] = useState<ToSResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const onTabChange = (nextTab: "classify" | "tos") => {
    setTab(nextTab);
    setError(null);
    setClassifyResult(null);
    setTosResult(null);
    setText(nextTab === "classify" ? sampleContract : sampleToS);
  };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const normalizedText = text.trim();
    if (!normalizedText) {
      setError("Enter contract text before running analysis.");
      setClassifyResult(null);
      setTosResult(null);
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      if (tab === "classify") {
        const data = await classifyContractApi(
          normalizedText,
          Math.min(5, Math.max(1, Number(topKTypes) || 3)),
        );
        if (data?.error) {
          setError(String(data.error));
          setClassifyResult(null);
        } else {
          setClassifyResult(data as ContractClassifyResponse);
        }
        setTosResult(null);
        return;
      }

      const data = await scanToSApi(normalizedText, Math.min(1, Math.max(0, Number(threshold) || 0.5)));
      if (data?.error) {
        setError(String(data.error));
        setTosResult(null);
      } else {
        setTosResult(data as ToSResponse);
      }
      setClassifyResult(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Contract analysis request failed.");
      setClassifyResult(null);
      setTosResult(null);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <section className="contracts-grid">
      <div>
        <h2>Contract Analysis</h2>
        <p>Classify contract clauses and detect potentially unfair Terms of Service language.</p>

        <div className="chip-row">
          <button
            type="button"
            className={`chip ${tab === "classify" ? "chip-active" : ""}`}
            onClick={() => onTabChange("classify")}
          >
            Clause Classification
          </button>
          <button
            type="button"
            className={`chip ${tab === "tos" ? "chip-active" : ""}`}
            onClick={() => onTabChange("tos")}
          >
            ToS Scanner
          </button>
        </div>

        <form className="ner-form" onSubmit={onSubmit}>
          {tab === "classify" ? (
            <>
              <label htmlFor="text">Contract text</label>
              <textarea id="text" name="text" rows={12} value={text} onChange={(event) => setText(event.target.value)} />

              <label htmlFor="top_k_types">Top clause types per segment</label>
              <input
                id="top_k_types"
                name="top_k_types"
                type="number"
                min={1}
                max={5}
                value={topKTypes}
                onChange={(event) => setTopKTypes(Number(event.target.value) || 3)}
              />

              <button type="submit" disabled={isLoading}>
                {isLoading ? "Analyzing..." : "Analyze Contract"}
              </button>
            </>
          ) : (
            <>
              <label htmlFor="text">Terms of service text</label>
              <textarea id="text" name="text" rows={12} value={text} onChange={(event) => setText(event.target.value)} />

              <label htmlFor="threshold">Unfair confidence threshold</label>
              <input
                id="threshold"
                name="threshold"
                type="number"
                step={0.05}
                min={0}
                max={1}
                value={threshold}
                onChange={(event) => setThreshold(Number(event.target.value) || 0.5)}
              />

              <button type="submit" disabled={isLoading}>
                {isLoading ? "Scanning..." : "Scan for Unfair Clauses"}
              </button>
            </>
          )}
        </form>

        {error ? (
          <article className="result-card">
            <p>{error}</p>
          </article>
        ) : null}

        {tab === "classify" && classifyResult ? (
          <>
            <h3>Classified Clauses ({classifyResult.total_clauses})</h3>
            <ul className="results-list">
              {classifyResult.clauses.map((clause) => (
                <li key={`${clause.segment_index}-${clause.start}`} className="result-card">
                  <div className="result-header">
                    <strong>{clause.clause_type}</strong>
                    <span className="badge">{clause.confidence.toFixed(4)}</span>
                  </div>
                  <p>{clause.text.slice(0, 420)}...</p>
                  <div className="chip-row">
                    {clause.alternatives.map((alt) => (
                      <span key={`${clause.segment_index}-${alt.type}`} className="chip">
                        {alt.type} ({alt.confidence.toFixed(3)})
                      </span>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </>
        ) : null}

        {tab === "tos" && tosResult ? (
          <>
            <h3>
              ToS Scan ({tosResult.unfair_count}/{tosResult.total_sentences} unfair)
            </h3>
            <ul className="results-list">
              {tosResult.sentences.map((sentence) => {
                const highest = Math.max(
                  0,
                  ...sentence.unfair_categories.map((item) => Number(item.confidence ?? 0)),
                );
                const severityClass =
                  highest > 0.8 ? "unfair-high" : sentence.is_unfair ? "unfair-medium" : "unfair-none";

                return (
                  <li key={`sentence-${sentence.index}`} className={`result-card ${severityClass}`}>
                    <p>{sentence.text}</p>
                    {sentence.unfair_categories.length > 0 ? (
                      <div className="chip-row">
                        {sentence.unfair_categories.map((item) => (
                          <span key={`${sentence.index}-${item.category}`} className="chip">
                            {item.category} ({item.confidence.toFixed(3)})
                          </span>
                        ))}
                      </div>
                    ) : (
                      <p className="meta-line">No unfair category detected.</p>
                    )}
                  </li>
                );
              })}
            </ul>
          </>
        ) : null}
      </div>

      <aside>
        <h3>Summary</h3>
        {tab === "classify" && classifyResult ? (
          <ul className="chapter-list">
            {Object.entries(classifyResult.clause_distribution).map(([clauseType, count]) => (
              <li key={clauseType}>
                {clauseType}: {count}
              </li>
            ))}
          </ul>
        ) : null}

        {tab === "tos" && tosResult ? (
          <>
            <p>Severity score: {tosResult.severity_score.toFixed(3)}</p>
            <ul className="chapter-list">
              {Object.entries(tosResult.summary).map(([category, count]) => (
                <li key={category}>
                  {category}: {count}
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </aside>
    </section>
  );
}
