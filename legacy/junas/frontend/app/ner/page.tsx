"use client";

import type { FormEvent, ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { listEntityTypes, extractEntities } from "../../lib/api-client";

type NerEntity = {
  text: string;
  type: string;
  type_label: string;
  start: number;
  end: number;
  confidence: number;
  language?: "de" | "en";
  gazetteer_match?: boolean;
  gazetteer_corrected?: boolean;
};

type NerExtractionResponse = {
  text: string;
  entities: NerEntity[];
  entity_counts: Record<string, number>;
  model_info: {
    model: string;
    language: "de" | "en";
    granularity: "fine" | "coarse";
    gazetteer_applied: boolean;
  };
};

type EntityTypesResponse = {
  fine_grained: Array<{ tag: string; label: string; description: string; category: string }>;
  coarse_grained: Array<{ tag: string; label: string; members: string[] }>;
};

const exampleTextsByLanguage: Record<"de" | "en", string[]> = {
  de: [
    "Der BGH hat in seinem Urteil vom 12. März 2023 (Az. III ZR 100/22) entschieden, dass § 433 BGB im vorliegenden Fall anzuwenden ist.",
    "Die Klägerin Frau Müller wurde von Rechtsanwalt Schneider vor dem Landgericht Berlin vertreten.",
    "Nach Art. 6 DSGVO und der Verordnung (EU) 2016/679 ist die Verarbeitung personenbezogener Daten nur unter bestimmten Voraussetzungen zulässig.",
  ],
  en: [
    "The Supreme Court held in Brown v. Board of Education, 347 U.S. 483 (1954), that racial segregation in public schools is unconstitutional.",
    "Counsel for the claimant argued that Article 7 of the Rome Statute defines crimes against humanity.",
    "Under Regulation (EU) 2016/679, personal data processing requires a lawful basis.",
  ],
};

function renderAnnotatedText(text: string, entities: NerEntity[]): ReactNode[] {
  const sorted = [...entities].sort((a, b) => {
    if (a.start !== b.start) {
      return a.start - b.start;
    }
    return a.end - b.end;
  });

  const nodes: ReactNode[] = [];
  let cursor = 0;

  sorted.forEach((entity, index) => {
    const start = Math.max(cursor, Math.max(0, entity.start));
    const end = Math.max(start, Math.min(text.length, entity.end));
    if (start > cursor) {
      nodes.push(<span key={`text-${index}-${cursor}`}>{text.slice(cursor, start)}</span>);
    }
    if (end > start) {
      nodes.push(
        <span
          key={`ent-${index}-${start}`}
          className={`entity-chip entity-${entity.type}`}
          title={`${entity.type_label} (${entity.confidence.toFixed(2)})`}
        >
          {text.slice(start, end)}
        </span>,
      );
    }
    cursor = end;
  });

  if (cursor < text.length) {
    nodes.push(<span key={`text-tail-${cursor}`}>{text.slice(cursor)}</span>);
  }
  return nodes;
}

export default function NerPage() {
  const [language, setLanguage] = useState<"de" | "en">("de");
  const [granularity, setGranularity] = useState<"fine" | "coarse">("fine");
  const [useGazetteer, setUseGazetteer] = useState(true);
  const [text, setText] = useState(exampleTextsByLanguage.de[0]);

  const [types, setTypes] = useState<EntityTypesResponse>({ fine_grained: [], coarse_grained: [] });
  const [result, setResult] = useState<NerExtractionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [hasRun, setHasRun] = useState(false);

  const examples = useMemo(() => exampleTextsByLanguage[language], [language]);

  useEffect(() => {
    let isActive = true;
    (async () => {
      const data = (await listEntityTypes()) as EntityTypesResponse;
      if (!isActive) return;
      setTypes({
        fine_grained: Array.isArray(data?.fine_grained) ? data.fine_grained : [],
        coarse_grained: Array.isArray(data?.coarse_grained) ? data.coarse_grained : [],
      });
    })();

    return () => {
      isActive = false;
    };
  }, []);

  const runExtraction = async (
    inputText: string,
    selectedLanguage: "de" | "en",
    selectedGranularity: "fine" | "coarse",
    selectedUseGazetteer: boolean,
  ) => {
    const normalizedText = inputText.trim();
    if (!normalizedText) {
      setError("Enter legal text before extraction.");
      setResult(null);
      setHasRun(true);
      return;
    }

    setIsLoading(true);
    setError(null);
    setHasRun(true);
    try {
      const data = await extractEntities(
        normalizedText,
        selectedLanguage,
        selectedGranularity,
        selectedUseGazetteer,
      );
      if (data?.error) {
        setError(String(data.error));
        setResult(null);
      } else {
        setResult(data as NerExtractionResponse);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Extraction request failed.");
      setResult(null);
    } finally {
      setIsLoading(false);
    }
  };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await runExtraction(text, language, granularity, useGazetteer);
  };

  const onLanguageChange = (value: "de" | "en") => {
    setLanguage(value);
    setText(exampleTextsByLanguage[value][0]);
    setResult(null);
    setError(null);
    setHasRun(false);
  };

  const onExampleClick = async (example: string) => {
    setText(example);
    await runExtraction(example, language, granularity, useGazetteer);
  };

  const entityTotal = result ? Object.values(result.entity_counts).reduce((sum, value) => sum + value, 0) : 0;

  return (
    <section className="ner-grid">
      <div>
        <h2>Legal Named Entity Recognition</h2>
        <p>
          Extract people, organizations, legal norms, court references, and other legal entities from
          German and English legal text.
        </p>
        <p className="meta-line">
          Dataset license note: Legal-Entity-Recognition is distributed under CC-BY-NC-SA 4.0.
        </p>

        <form className="ner-form" onSubmit={onSubmit}>
          <label htmlFor="language">Language</label>
          <select
            id="language"
            name="language"
            value={language}
            onChange={(event) => onLanguageChange(event.target.value === "en" ? "en" : "de")}
          >
            <option value="de">German (de)</option>
            <option value="en">English (en)</option>
          </select>

          <label htmlFor="text">Legal text</label>
          <textarea
            id="text"
            name="text"
            rows={10}
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Paste legal text..."
          />

          <label htmlFor="granularity">Entity granularity</label>
          <select
            id="granularity"
            name="granularity"
            value={granularity}
            onChange={(event) => setGranularity(event.target.value === "coarse" ? "coarse" : "fine")}
          >
            <option value="fine">fine (19 entity types)</option>
            <option value="coarse">coarse (7 entity groups)</option>
          </select>

          <label className="checkbox-row">
            <input
              type="checkbox"
              name="use_gazetteer"
              value="true"
              checked={useGazetteer}
              onChange={(event) => setUseGazetteer(event.target.checked)}
            />
            Apply gazetteer post-processing (German only)
          </label>

          <button type="submit" disabled={isLoading}>
            {isLoading ? "Extracting..." : "Extract Entities"}
          </button>
        </form>

        <div className="chip-row">
          {examples.map((example, index) => (
            <button key={`example-${language}-${index}`} className="chip" type="button" onClick={() => onExampleClick(example)}>
              Example {index + 1}
            </button>
          ))}
        </div>

        {error ? (
          <article className="result-card">
            <h3>Extraction unavailable</h3>
            <p>{error}</p>
          </article>
        ) : null}

        {result ? (
          <>
            <h3>Annotated Text</h3>
            <article className="result-card annotated-text">{renderAnnotatedText(result.text, result.entities)}</article>

            <h3>Entities ({result.entities.length})</h3>
            <table className="comparison-table">
              <thead>
                <tr>
                  <th>Text</th>
                  <th>Type</th>
                  <th>Confidence</th>
                  <th>Gazetteer</th>
                </tr>
              </thead>
              <tbody>
                {result.entities.map((entity, index) => (
                  <tr key={`${entity.type}-${entity.start}-${entity.end}-${index}`}>
                    <td>{entity.text}</td>
                    <td>
                      {entity.type} ({entity.type_label})
                    </td>
                    <td>{entity.confidence.toFixed(4)}</td>
                    <td>
                      {entity.gazetteer_corrected
                        ? "corrected"
                        : entity.gazetteer_match
                          ? "matched"
                          : "none"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : hasRun ? (
          <p>No entities extracted.</p>
        ) : null}
      </div>

      <aside>
        <h3>Model Info</h3>
        <ul className="chapter-list">
          <li>model: {result?.model_info.model ?? "-"}</li>
          <li>language: {result?.model_info.language ?? language}</li>
          <li>granularity: {result?.model_info.granularity ?? granularity}</li>
        </ul>

        <h3>Entity Distribution</h3>
        {result ? (
          <ul className="chapter-list">
            {Object.entries(result.entity_counts).map(([tag, count]) => (
              <li key={tag}>
                <div className="distribution-row">
                  <strong>{tag}</strong> <span>{count}</span>
                </div>
                <div className="distribution-track">
                  <div
                    className={`distribution-bar entity-${tag}`}
                    style={{ width: `${Math.max(4, Math.round((count / Math.max(1, entityTotal)) * 100))}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p>Submit text to view extracted entity counts.</p>
        )}

        <h3>Fine-Grained Types</h3>
        <ul className="chapter-list">
          {types.fine_grained.map((item) => (
            <li key={item.tag}>
              <strong>{item.tag}</strong>: {item.label}
            </li>
          ))}
        </ul>

        <h3>Coarse Mapping</h3>
        <ul className="chapter-list">
          {types.coarse_grained.map((item) => (
            <li key={item.tag}>
              <strong>{item.tag}</strong>: {item.members.join(", ")}
            </li>
          ))}
        </ul>
      </aside>
    </section>
  );
}
