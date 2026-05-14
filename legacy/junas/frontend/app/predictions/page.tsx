"use client";

import type { FormEvent } from "react";
import { useState } from "react";
import {
  predictScotus as apiPredictScotus,
  predictEcthr as apiPredictEcthr,
  predictCasehold as apiPredictCasehold,
  predictEurlex as apiPredictEurlex,
} from "../../lib/api-client";

type PredictionTab = "scotus" | "ecthr" | "casehold" | "eurlex";

type ScotusResponse = {
  prediction: {
    issue_area: string;
    issue_area_id: number | null;
    confidence: number;
  };
  alternatives: Array<{ issue_area: string; issue_area_id: number | null; confidence: number }>;
  model_info: { model: string; input_length: number };
};

type EcthrResponse = {
  predictions: Array<{ article: string; article_id: number; right: string; confidence: number }>;
  no_violation_probability: number;
  task: "violation" | "alleged";
};

type CaseholdResponse = {
  selected_option: number;
  selected_text: string;
  confidence: number;
  option_scores: number[];
};

type EurlexResponse = {
  labels: Array<{ eurovoc_id: number; concept: string; confidence: number }>;
  total_labels: number;
};

const sampleScotus =
  "The Court granted certiorari to decide whether admitting the evidence violated the petitioner's constitutional due process rights.";
const sampleEcthr =
  "The applicant alleged mistreatment in custody and argued that detention conditions violated Convention guarantees.";
const sampleCasehold =
  "In Smith v. Jones, the appellate court clarified that <HOLDING> for negligent misrepresentation claims in this jurisdiction.";
const sampleEurlex =
  "REGULATION (EU) No 1234/2026 of the European Parliament and of the Council on market surveillance and consumer protection requirements.";

const defaultCaseholdOptions = [
  "the claim is always barred when privity is absent",
  "a plaintiff must prove statutory standing before damages",
  "negligent misrepresentation requires foreseeable reliance",
  "punitive damages are mandatory for all violations",
  "federal preemption automatically applies to state contracts",
];

export default function PredictionsPage() {
  const [tab, setTab] = useState<PredictionTab>("scotus");

  const [scotusText, setScotusText] = useState(sampleScotus);
  const [ecthrText, setEcthrText] = useState(sampleEcthr);
  const [caseholdContext, setCaseholdContext] = useState(sampleCasehold);
  const [eurlexText, setEurlexText] = useState(sampleEurlex);

  const [topK, setTopK] = useState(3);
  const [ecthrTask, setEcthrTask] = useState<"violation" | "alleged">("violation");
  const [threshold, setThreshold] = useState(0.5);
  const [maxLabels, setMaxLabels] = useState(10);
  const [caseholdOptions, setCaseholdOptions] = useState<string[]>(defaultCaseholdOptions);

  const [scotusResult, setScotusResult] = useState<ScotusResponse | null>(null);
  const [ecthrResult, setEcthrResult] = useState<EcthrResponse | null>(null);
  const [caseholdResult, setCaseholdResult] = useState<CaseholdResponse | null>(null);
  const [eurlexResult, setEurlexResult] = useState<EurlexResponse | null>(null);
  const [activeError, setActiveError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const onTabChange = (nextTab: PredictionTab) => {
    setTab(nextTab);
    setActiveError(null);
  };

  const onCaseholdOptionChange = (index: number, value: string) => {
    setCaseholdOptions((current) => current.map((option, optionIndex) => (optionIndex === index ? value : option)));
  };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    setActiveError(null);
    setIsLoading(true);

    try {
      if (tab === "scotus") {
        const normalizedText = scotusText.trim();
        if (!normalizedText) {
          setActiveError("Enter opinion text before predicting.");
          setScotusResult(null);
          return;
        }

        const data = await apiPredictScotus(normalizedText, Math.min(14, Math.max(1, Number(topK) || 3)));
        if (data?.error) {
          setActiveError(String(data.error));
          setScotusResult(null);
        } else {
          setScotusResult(data as ScotusResponse);
        }
        return;
      }

      if (tab === "ecthr") {
        const normalizedText = ecthrText.trim();
        if (!normalizedText) {
          setActiveError("Enter case facts before predicting.");
          setEcthrResult(null);
          return;
        }

        const data = await apiPredictEcthr(
          normalizedText,
          ecthrTask,
          Math.min(1, Math.max(0, Number(threshold) || 0.5)),
        );
        if (data?.error) {
          setActiveError(String(data.error));
          setEcthrResult(null);
        } else {
          setEcthrResult(data as EcthrResponse);
        }
        return;
      }

      if (tab === "casehold") {
        const normalizedContext = caseholdContext.trim();
        const normalizedOptions = caseholdOptions.map((option) => option.trim());
        if (!normalizedContext) {
          setActiveError("Enter context with <HOLDING> before prediction.");
          setCaseholdResult(null);
          return;
        }
        if (normalizedOptions.some((option) => !option)) {
          setActiveError("All five candidate options must be provided.");
          setCaseholdResult(null);
          return;
        }

        const data = await apiPredictCasehold(normalizedContext, normalizedOptions);
        if (data?.error) {
          setActiveError(String(data.error));
          setCaseholdResult(null);
        } else {
          setCaseholdResult(data as CaseholdResponse);
        }
        return;
      }

      const normalizedText = eurlexText.trim();
      if (!normalizedText) {
        setActiveError("Enter EU legislation text before classification.");
        setEurlexResult(null);
        return;
      }

      const data = await apiPredictEurlex(
        normalizedText,
        Math.min(1, Math.max(0, Number(threshold) || 0.5)),
        Math.min(100, Math.max(1, Number(maxLabels) || 10)),
      );
      if (data?.error) {
        setActiveError(String(data.error));
        setEurlexResult(null);
      } else {
        setEurlexResult(data as EurlexResponse);
      }
    } catch (requestError) {
      setActiveError(requestError instanceof Error ? requestError.message : "Prediction request failed.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <section className="predictions-grid">
      <div>
        <h2>Court Decision Prediction Suite</h2>
        <p>Run LexGLUE task demos for SCOTUS, ECtHR, CaseHOLD, and EUR-LEX classifiers.</p>

        <div className="chip-row">
          <button
            type="button"
            className={`chip ${tab === "scotus" ? "chip-active" : ""}`}
            onClick={() => onTabChange("scotus")}
          >
            SCOTUS
          </button>
          <button
            type="button"
            className={`chip ${tab === "ecthr" ? "chip-active" : ""}`}
            onClick={() => onTabChange("ecthr")}
          >
            ECtHR
          </button>
          <button
            type="button"
            className={`chip ${tab === "casehold" ? "chip-active" : ""}`}
            onClick={() => onTabChange("casehold")}
          >
            CaseHOLD
          </button>
          <button
            type="button"
            className={`chip ${tab === "eurlex" ? "chip-active" : ""}`}
            onClick={() => onTabChange("eurlex")}
          >
            EUR-LEX
          </button>
        </div>

        <form className="ner-form" onSubmit={onSubmit}>
          {tab === "scotus" ? (
            <>
              <label htmlFor="text">Opinion text</label>
              <textarea id="text" name="text" rows={10} value={scotusText} onChange={(event) => setScotusText(event.target.value)} />

              <label htmlFor="top_k">Top predictions</label>
              <input
                id="top_k"
                name="top_k"
                type="number"
                min={1}
                max={14}
                value={topK}
                onChange={(event) => setTopK(Number(event.target.value) || 3)}
              />

              <button type="submit" disabled={isLoading}>
                {isLoading ? "Predicting..." : "Predict Issue Area"}
              </button>
            </>
          ) : null}

          {tab === "ecthr" ? (
            <>
              <label htmlFor="text">Case facts</label>
              <textarea id="text" name="text" rows={10} value={ecthrText} onChange={(event) => setEcthrText(event.target.value)} />

              <label htmlFor="task">Task</label>
              <select
                id="task"
                name="task"
                value={ecthrTask}
                onChange={(event) => setEcthrTask(event.target.value === "alleged" ? "alleged" : "violation")}
              >
                <option value="violation">Violation (Task A)</option>
                <option value="alleged">Alleged (Task B)</option>
              </select>

              <label htmlFor="threshold">Confidence threshold</label>
              <input
                id="threshold"
                name="threshold"
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={threshold}
                onChange={(event) => setThreshold(Number(event.target.value) || 0.5)}
              />

              <button type="submit" disabled={isLoading}>
                {isLoading ? "Predicting..." : "Predict Articles"}
              </button>
            </>
          ) : null}

          {tab === "casehold" ? (
            <>
              <label htmlFor="context">Context with &lt;HOLDING&gt;</label>
              <textarea
                id="context"
                name="context"
                rows={8}
                value={caseholdContext}
                onChange={(event) => setCaseholdContext(event.target.value)}
              />

              {caseholdOptions.map((option, index) => (
                <div key={`option-${index}`}>
                  <label htmlFor={`option_${index}`}>Option {index}</label>
                  <input
                    id={`option_${index}`}
                    name={`option_${index}`}
                    value={option}
                    onChange={(event) => onCaseholdOptionChange(index, event.target.value)}
                  />
                </div>
              ))}

              <button type="submit" disabled={isLoading}>
                {isLoading ? "Selecting..." : "Select Holding"}
              </button>
            </>
          ) : null}

          {tab === "eurlex" ? (
            <>
              <label htmlFor="text">EU legislation text</label>
              <textarea id="text" name="text" rows={10} value={eurlexText} onChange={(event) => setEurlexText(event.target.value)} />

              <label htmlFor="threshold">Confidence threshold</label>
              <input
                id="threshold"
                name="threshold"
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={threshold}
                onChange={(event) => setThreshold(Number(event.target.value) || 0.5)}
              />

              <label htmlFor="max_labels">Max labels</label>
              <input
                id="max_labels"
                name="max_labels"
                type="number"
                min={1}
                max={100}
                value={maxLabels}
                onChange={(event) => setMaxLabels(Number(event.target.value) || 10)}
              />

              <button type="submit" disabled={isLoading}>
                {isLoading ? "Classifying..." : "Classify EuroVoc Labels"}
              </button>
            </>
          ) : null}
        </form>

        {activeError ? (
          <article className="result-card">
            <h3>Request failed</h3>
            <p>{activeError}</p>
          </article>
        ) : null}

        {tab === "scotus" && scotusResult ? (
          <article className="result-card">
            <h3>Predicted Issue Area</h3>
            <p>
              <strong>{scotusResult.prediction.issue_area}</strong> ({scotusResult.prediction.confidence.toFixed(3)})
            </p>
            <ul className="results-list">
              {scotusResult.alternatives.map((item) => (
                <li key={`${item.issue_area}-${item.issue_area_id}`}>
                  {item.issue_area}: {item.confidence.toFixed(3)}
                </li>
              ))}
            </ul>
          </article>
        ) : null}

        {tab === "ecthr" && ecthrResult ? (
          <article className="result-card">
            <h3>Predicted Articles</h3>
            {ecthrResult.predictions.length === 0 ? (
              <p>No article above threshold. no_violation_probability: {ecthrResult.no_violation_probability.toFixed(3)}</p>
            ) : (
              <ul className="results-list">
                {ecthrResult.predictions.map((item) => (
                  <li key={`${item.article}-${item.article_id}`}>
                    <strong>{item.article}</strong> ({item.confidence.toFixed(3)}) - {item.right}
                  </li>
                ))}
              </ul>
            )}
          </article>
        ) : null}

        {tab === "casehold" && caseholdResult ? (
          <article className="result-card">
            <h3>Selected Holding</h3>
            <p>
              Option {caseholdResult.selected_option}: {caseholdResult.selected_text}
            </p>
            <p className="meta-line">confidence: {caseholdResult.confidence.toFixed(3)}</p>
            <ul className="results-list">
              {caseholdResult.option_scores.map((score, index) => (
                <li
                  key={`score-${index}`}
                  className={index === caseholdResult.selected_option ? "prediction-selected" : undefined}
                >
                  option {index}: {score.toFixed(3)}
                </li>
              ))}
            </ul>
          </article>
        ) : null}

        {tab === "eurlex" && eurlexResult ? (
          <article className="result-card">
            <h3>Predicted EuroVoc Labels ({eurlexResult.total_labels})</h3>
            <ul className="results-list">
              {eurlexResult.labels.map((item) => (
                <li key={`${item.eurovoc_id}-${item.concept}`}>
                  {item.concept} ({item.eurovoc_id}) - {item.confidence.toFixed(3)}
                </li>
              ))}
            </ul>
          </article>
        ) : null}
      </div>

      <aside>
        <h3>Active Task</h3>
        <ul className="chapter-list">
          <li>tab: {tab}</li>
          <li>status: {isLoading ? "running" : "idle"}</li>
          <li>api: client POST</li>
        </ul>

        <h3>Tips</h3>
        <ul className="chapter-list">
          <li>SCOTUS and ECtHR work better with longer factual summaries.</li>
          <li>CaseHOLD requires exactly five candidate options.</li>
          <li>EUR-LEX threshold controls label precision/recall tradeoff.</li>
        </ul>
      </aside>
    </section>
  );
}
