import Link from "next/link";
import { searchSSO, searchStatutes, listStatuteChapters } from "../../lib/api-server";

type SgResult = { title: string; url: string; snippet: string; source: string };

type StatuteResult = {
  number: string;
  name: string;
  chapter_number: string;
  text_html: string;
  text_plain: string;
  cross_references: string[];
  score: number;
  search_mode: string;
};

type StatuteSearchResponse = {
  total: number;
  results: StatuteResult[];
};

type ChapterItem = {
  chapter_number: string;
  section_count: number;
  first_section: string;
};

type ChaptersResponse = {
  chapters: ChapterItem[];
};

export default async function StatutesPage({
  searchParams,
}: {
  searchParams?: {
    q?: string;
    chapter?: string;
    mode?: "hybrid" | "keyword" | "semantic";
    jurisdiction?: string;
    page?: string;
    per_page?: string;
  };
}) {
  const q = searchParams?.q ?? "";
  const chapter = searchParams?.chapter ?? "";
  const mode = searchParams?.mode ?? "hybrid";
  const jurisdiction = searchParams?.jurisdiction ?? "us";
  const page = Number(searchParams?.page ?? "1") || 1;
  const perPage = Number(searchParams?.per_page ?? "20") || 20;

  const isSg = jurisdiction === "sg";
  const [searchRaw, chaptersRaw, sgResultsRaw] = await Promise.all([
    isSg ? Promise.resolve({ total: 0, results: [] }) : q.trim() ? searchStatutes(q, chapter, mode, page, perPage) : Promise.resolve({ total: 0, results: [] }),
    isSg ? Promise.resolve({ chapters: [] }) : listStatuteChapters(),
    isSg && q.trim() ? searchSSO(q) : Promise.resolve([]),
  ]);
  const search = searchRaw as StatuteSearchResponse;
  const chapters = chaptersRaw as ChaptersResponse;
  const sgResults = sgResultsRaw as SgResult[];

  return (
    <section className="statute-grid">
      <div>
        <h2>Statute Browser</h2>
        <p>Search statutes across jurisdictions</p>

        <form method="get" action="/statutes" className="glossary-form">
          <label htmlFor="jurisdiction">Jurisdiction</label>
          <select id="jurisdiction" name="jurisdiction" defaultValue={jurisdiction}>
            <option value="us">Oregon (US)</option>
            <option value="sg">Singapore (SSO)</option>
          </select>

          <label htmlFor="q">Search statutes</label>
          <input id="q" name="q" defaultValue={q} placeholder={isSg ? "employment act" : "naturopathic physician"} />

          {!isSg && <>
            <label htmlFor="mode">Mode</label>
            <select id="mode" name="mode" defaultValue={mode}>
              <option value="hybrid">hybrid</option>
              <option value="keyword">keyword</option>
              <option value="semantic">semantic</option>
            </select>
            <label htmlFor="chapter">Chapter filter</label>
            <input id="chapter" name="chapter" defaultValue={chapter} placeholder="685" />
          </>}

          <button type="submit">Search</button>
        </form>

        {isSg ? (
          <>
            <h3>Singapore Statutes ({sgResults.length})</h3>
            <ul className="results-list">
              {sgResults.map((row: SgResult, i: number) => (
                <li key={i} className="result-card">
                  <div className="result-header">
                    <a href={row.url} target="_blank" rel="noopener noreferrer"><strong>{row.title}</strong></a>
                    <span className="badge muted">{row.source}</span>
                  </div>
                  {row.snippet && <p className="meta-line">{row.snippet}</p>}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <>
            <h3>Results ({search.total})</h3>
            <ul className="results-list">
              {search.results.map((row: StatuteResult) => (
                <li key={`${row.number}-${row.search_mode}`} className="result-card">
                  <div className="result-header">
                    <Link href={`/statutes/section/${encodeURIComponent(row.number)}`}><strong>{row.number}</strong></Link>
                    <span>{row.name}</span>
                  </div>
                  <p><Link href={`/statutes/chapter/${encodeURIComponent(row.chapter_number)}`}>Chapter {row.chapter_number}</Link></p>
                  <p>{row.text_plain.slice(0, 400)}...</p>
                  <p className="meta-line">mode: {row.search_mode} | score: {row.score.toFixed(4)}</p>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      <aside>
        <h3>Chapters</h3>
        <ul className="chapter-list">
          {chapters.chapters.map((item: ChapterItem) => (
            <li key={item.chapter_number}>
              <Link href={`/statutes/chapter/${encodeURIComponent(item.chapter_number)}`}>
                {item.chapter_number}
              </Link>{" "}
              ({item.section_count})
            </li>
          ))}
        </ul>
      </aside>
    </section>
  );
}
