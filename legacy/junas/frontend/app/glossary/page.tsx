import Link from "next/link";
import { searchGlossary, listGlossaryJurisdictions, suggestGlossary } from "../../lib/api-server";

type SearchResult = {
  phrase: string;
  definition_html: string;
  definition_text: string;
  jurisdiction: string;
  domain: string;
  source_title: string;
  source_url: string;
  score: number;
};
type SearchResponse = {
  total: number;
  page: number;
  per_page: number;
  results: SearchResult[];
  aggregations: { jurisdictions: Record<string, number>; domains: Record<string, number> };
};
type JurisdictionsResponse = {
  jurisdictions: Array<{ code: string; name: string; count: number; domains: string[] }>;
};
type SuggestResponse = { suggestions: string[] };

async function fetchSearch(q: string, jurisdiction: string, domain: string, page: number, perPage: number): Promise<SearchResponse> {
  if (!q.trim()) return { total: 0, page, per_page: perPage, results: [], aggregations: { jurisdictions: {}, domains: {} } };
  const data = await searchGlossary(q, jurisdiction.trim(), domain.trim(), page, perPage);
  return { total: 0, page, per_page: perPage, results: [], aggregations: { jurisdictions: {}, domains: {} }, ...data } as SearchResponse;
}
async function fetchJurisdictions(): Promise<JurisdictionsResponse> {
  return (await listGlossaryJurisdictions()) as JurisdictionsResponse;
}
async function fetchSuggestions(q: string): Promise<SuggestResponse> {
  if (!q.trim()) return { suggestions: [] };
  return (await suggestGlossary(q.trim(), 8)) as SuggestResponse;
}

export default async function GlossaryPage({ searchParams }: { searchParams?: { q?: string; jurisdiction?: string; domain?: string; page?: string; per_page?: string } }) {
  const q = searchParams?.q ?? "";
  const jurisdiction = searchParams?.jurisdiction ?? "";
  const domain = searchParams?.domain ?? "";
  const page = Number(searchParams?.page ?? "1") || 1;
  const perPage = Number(searchParams?.per_page ?? "20") || 20;
  const [search, jurisdictions, suggestions] = await Promise.all([fetchSearch(q, jurisdiction, domain, page, perPage), fetchJurisdictions(), fetchSuggestions(q)]);
  const activeJurisdiction = jurisdiction.toUpperCase();

  return (
    <section>
      <h2 style={{ marginBottom: "0.25rem" }}>Legal Glossary</h2>
      <p className="meta-line" style={{ marginBottom: "1.25rem" }}>
        Search legal definitions across {jurisdictions.jurisdictions.length || 6} jurisdictions.
      </p>

      {/* jurisdiction quick-filter chips */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem", marginBottom: "1rem" }}>
        <Link href={`/glossary?q=${encodeURIComponent(q)}&domain=${encodeURIComponent(domain)}`}
          className={`chip ${!jurisdiction ? "chip-active" : ""}`}>
          All
        </Link>
        {jurisdictions.jurisdictions.map(j => (
          <Link key={j.code}
            href={`/glossary?q=${encodeURIComponent(q)}&jurisdiction=${encodeURIComponent(j.code)}&domain=${encodeURIComponent(domain)}`}
            className={`chip ${activeJurisdiction === j.code.toUpperCase() ? "chip-active" : ""}`}>
            {j.name}
          </Link>
        ))}
      </div>

      {/* search form */}
      <form method="get" action="/glossary" style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem" }}>
        <input type="hidden" name="jurisdiction" value={jurisdiction} />
        <input type="hidden" name="domain" value={domain} />
        <input name="q" defaultValue={q} placeholder="Search for a legal term..." style={{
          flex: 1, padding: "0.6rem 0.8rem", borderRadius: "0.5rem", border: "1px solid #D6D3D1",
          fontFamily: "inherit", fontSize: "0.92rem", outline: "none",
        }} />
        <button type="submit" style={{
          padding: "0.6rem 1.25rem", borderRadius: "0.5rem", border: "none",
          background: "#1C1917", color: "#FAFAF9", fontFamily: "inherit",
          fontSize: "0.85rem", fontWeight: 600, cursor: "pointer",
        }}>
          Search
        </button>
      </form>

      {/* autocomplete suggestions */}
      {suggestions.suggestions.length > 0 && (
        <div style={{ marginBottom: "1.25rem" }}>
          <p className="meta-line" style={{ marginBottom: "0.35rem", fontSize: "0.78rem" }}>Did you mean:</p>
          <div className="chip-row">
            {suggestions.suggestions.map(term => (
              <Link key={term} href={`/glossary?q=${encodeURIComponent(term)}&jurisdiction=${encodeURIComponent(jurisdiction)}&domain=${encodeURIComponent(domain)}`} className="chip">
                {term}
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* results */}
      {q && (
        <p style={{ fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.75rem" }}>
          {search.total > 0 ? `${search.total} result${search.total !== 1 ? "s" : ""} for "${q}"` : `No results for "${q}"`}
        </p>
      )}

      {!q && (
        <div style={{ textAlign: "center", padding: "3rem 1rem", color: "#A8A29E" }}>
          <p style={{ fontSize: "1.1rem", marginBottom: "0.5rem" }}>Search for a legal term above</p>
          <p style={{ fontSize: "0.82rem" }}>Try: acquittal, estoppel, habeas corpus, tort, fiduciary</p>
        </div>
      )}

      <ul className="results-list">
        {search.results.map(result => (
          <li key={`${result.phrase}-${result.jurisdiction}-${result.domain}`} className="result-card">
            <div className="result-header">
              <Link href={`/glossary/${encodeURIComponent(result.phrase)}`}><strong>{result.phrase}</strong></Link>
              <span className="badge">{result.jurisdiction}</span>
              {result.domain && <span className="badge muted">{result.domain}</span>}
            </div>
            <div className="definition-html" style={{ marginTop: "0.35rem", fontSize: "0.88rem", lineHeight: 1.6 }}>
              {result.definition_text.slice(0, 350)}{result.definition_text.length > 350 && "..."}
            </div>
            {result.source_title && (
              <p className="meta-line" style={{ marginTop: "0.35rem" }}>
                Source: {result.source_url ? <a href={result.source_url} target="_blank" rel="noopener noreferrer">{result.source_title}</a> : result.source_title}
              </p>
            )}
          </li>
        ))}
      </ul>

      {/* domain filter sidebar — show only when results have aggregations */}
      {q && Object.keys(search.aggregations.domains).length > 0 && (
        <div style={{ marginTop: "1.5rem" }}>
          <p style={{ fontSize: "0.78rem", fontWeight: 600, marginBottom: "0.35rem" }}>Filter by practice area</p>
          <div className="chip-row">
            {Object.entries(search.aggregations.domains).sort((a, b) => b[1] - a[1]).map(([d, count]) => (
              <Link key={d}
                href={`/glossary?q=${encodeURIComponent(q)}&jurisdiction=${encodeURIComponent(jurisdiction)}&domain=${encodeURIComponent(d)}`}
                className={`chip ${domain === d ? "chip-active" : ""}`}>
                {d} ({count})
              </Link>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
