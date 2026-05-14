import Link from "next/link";
import { listRomeStatuteParts, searchRomeStatute } from "../../lib/api-server";

type RomePart = {
  part_number: string;
  part_title: string;
  article_count: number;
};

type RomeSearchResult = {
  article_number: string;
  article_title: string;
  part_number: string;
  part_title: string;
  text_snippet: string;
  score: number;
};

async function fetchParts(): Promise<RomePart[]> {
  const data = await listRomeStatuteParts();
  return (data as any)?.parts ?? [];
}

async function searchArticles(query: string, topK: number): Promise<RomeSearchResult[]> {
  if (!query.trim()) return [];
  const data = await searchRomeStatute(query.trim(), topK);
  return (data as any)?.results ?? [];
}

export default async function RomeStatutePage({
  searchParams,
}: {
  searchParams?: {
    q?: string;
    top_k?: string;
    run?: "0" | "1";
  };
}) {
  const query = (searchParams?.q ?? "").trim();
  const topK = Math.min(100, Math.max(1, Number(searchParams?.top_k ?? "20") || 20));
  const shouldRunSearch = searchParams?.run === "1";

  const [parts, results] = await Promise.all([
    fetchParts(),
    shouldRunSearch ? searchArticles(query, topK) : Promise.resolve([] as RomeSearchResult[]),
  ]);

  return (
    <section className="statute-grid">
      <div>
        <h2>Rome Statute</h2>
        <p>
          Browse and search the Rome Statute by part and article. Use this reference view for treaty lookup and
          treaty-grounded research answers.
        </p>

        <form method="get" action="/rome-statute" className="glossary-form">
          <input type="hidden" name="run" value="1" />

          <label htmlFor="q">Search query</label>
          <input
            id="q"
            name="q"
            defaultValue={query}
            placeholder="genocide, crimes against humanity, article 7"
          />

          <label htmlFor="top_k">Max results</label>
          <input id="top_k" name="top_k" type="number" min={1} max={100} defaultValue={topK} />

          <button type="submit">Search Articles</button>
        </form>

        <div className="chip-row">
          <Link href="/rome-statute?run=1&q=genocide&top_k=20" className="chip">
            genocide
          </Link>
          <Link href="/rome-statute?run=1&q=crimes%20against%20humanity&top_k=20" className="chip">
            crimes against humanity
          </Link>
          <Link href="/rome-statute?run=1&q=jurisdiction&top_k=20" className="chip">
            jurisdiction
          </Link>
        </div>

        {shouldRunSearch ? (
          <>
            <h3>Search Results ({results.length})</h3>
            {results.length === 0 ? (
              <p>No matching articles found.</p>
            ) : (
              <ul className="results-list">
                {results.map((row) => (
                  <li key={`search-${row.article_number}`} className="result-card">
                    <div className="result-header">
                      <Link href={`/rome-statute/article/${encodeURIComponent(row.article_number)}`}>
                        <strong>
                          Article {row.article_number}: {row.article_title}
                        </strong>
                      </Link>
                      <span className="badge">score {row.score.toFixed(2)}</span>
                    </div>
                    <p>{row.text_snippet.slice(0, 320)}...</p>
                    <p className="meta-line">
                      Part {row.part_number}: {row.part_title}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : null}
      </div>

      <aside>
        <h3>Parts</h3>
        {parts.length === 0 ? (
          <p>Parts are unavailable. Confirm dataset ingestion/API availability.</p>
        ) : (
          <ul className="chapter-list">
            {parts.map((part) => (
              <li key={`part-${part.part_number}`}>
                <Link href={`/rome-statute/part/${encodeURIComponent(part.part_number)}`}>
                  <strong>Part {part.part_number}</strong>
                </Link>
                <div>{part.part_title}</div>
                <div className="meta-line">{part.article_count} articles</div>
              </li>
            ))}
          </ul>
        )}
      </aside>
    </section>
  );
}
