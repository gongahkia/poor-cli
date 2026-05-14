import Link from "next/link";
import { getRomeStatutePart } from "../../../../lib/api-server";

type PartArticle = {
  article_number: string;
  article_title: string;
};

type PartResponse = {
  part_number: string;
  part_title: string;
  articles: PartArticle[];
};

export default async function RomePartPage({
  params,
}: {
  params: {
    number: string;
  };
}) {
  const part = (await getRomeStatutePart(params.number)) as PartResponse | null;

  if (!part) {
    return (
      <section>
        <h2>Rome Statute Part Not Found</h2>
        <p>Part {params.number} could not be loaded.</p>
        <Link href="/rome-statute" className="chip">
          Back to Rome Statute
        </Link>
      </section>
    );
  }

  return (
    <section>
      <h2>
        Part {part.part_number}: {part.part_title}
      </h2>
      <p>{part.articles.length} articles in this part.</p>

      <div className="chip-row">
        <Link href="/rome-statute" className="chip">
          All Parts
        </Link>
      </div>

      <ul className="results-list">
        {part.articles.map((article) => (
          <li key={`article-${article.article_number}`} className="result-card">
            <Link href={`/rome-statute/article/${encodeURIComponent(article.article_number)}`}>
              <strong>
                Article {article.article_number}: {article.article_title}
              </strong>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
