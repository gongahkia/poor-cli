import Link from "next/link";
import { getGlossaryTerm, compareGlossaryTerm } from "../../../lib/api-server";

type Definition = {
  jurisdiction: string;
  domain: string;
  definition_html: string;
  definition_text: string;
  source_title: string;
  source_url: string;
};

type TermResponse = {
  phrase: string;
  definitions: Definition[];
};

type CompareResponse = {
  term: string;
  comparisons: Array<{ jurisdiction: string; domain: string; definition_text: string }>;
  available_in: string[];
  not_found_in: string[];
};

async function fetchTerm(phrase: string): Promise<TermResponse> {
  const data = await getGlossaryTerm(phrase);
  return data ?? { phrase, definitions: [] };
}

async function fetchComparison(phrase: string): Promise<CompareResponse> {
  const data = await compareGlossaryTerm(phrase);
  return { term: phrase, comparisons: [], available_in: [], not_found_in: [], ...data } as CompareResponse;
}

export default async function GlossaryTermPage({ params }: { params: { phrase: string } }) {
  const phrase = decodeURIComponent(params.phrase);
  const [term, comparison] = await Promise.all([fetchTerm(phrase), fetchComparison(phrase)]);

  return (
    <section>
      <p>
        <Link href="/glossary">Glossary</Link> / {term.phrase}
      </p>
      <h2>{term.phrase}</h2>
      <p>Definitions across jurisdictions with side-by-side comparison.</p>

      {term.definitions.length === 0 ? <p>No definitions found for this term.</p> : null}

      <div className="result-grid">
        {term.definitions.map((definition) => (
          <article
            key={`${definition.jurisdiction}-${definition.domain}-${definition.source_url}`}
            className="result-card"
          >
            <h3>
              {definition.jurisdiction} <span className="badge muted">{definition.domain}</span>
            </h3>
            <div
              className="definition-html"
              dangerouslySetInnerHTML={{ __html: definition.definition_html }}
            />
            <p className="meta-line">
              Source: <a href={definition.source_url}>{definition.source_title || definition.source_url}</a>
            </p>
          </article>
        ))}
      </div>

      <h3>Comparison View</h3>
      <table className="comparison-table">
        <thead>
          <tr>
            <th>Jurisdiction</th>
            <th>Domain</th>
            <th>Definition</th>
          </tr>
        </thead>
        <tbody>
          {comparison.comparisons.map((row) => (
            <tr key={`${row.jurisdiction}-${row.domain}`}>
              <td>{row.jurisdiction}</td>
              <td>{row.domain}</td>
              <td>{row.definition_text}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <p>Available in: {comparison.available_in.join(", ") || "none"}</p>
      <p>Not found in: {comparison.not_found_in.join(", ") || "none"}</p>
    </section>
  );
}
