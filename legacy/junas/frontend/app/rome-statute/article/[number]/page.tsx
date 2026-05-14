import Link from "next/link";
import { getRomeStatuteArticle } from "../../../../lib/api-server";

type ArticleResponse = {
  article_number: string;
  article_title: string;
  text: string;
  part_number: string;
  part_title: string;
};

export default async function RomeArticlePage({
  params,
}: {
  params: {
    number: string;
  };
}) {
  const article = await getRomeStatuteArticle(params.number);

  if (!article) {
    return (
      <section>
        <h2>Rome Statute Article Not Found</h2>
        <p>Article {params.number} could not be loaded.</p>
        <div className="chip-row">
          <Link href="/rome-statute" className="chip">
            Back to Rome Statute
          </Link>
        </div>
      </section>
    );
  }

  return (
    <section>
      <h2>
        Article {article.article_number}: {article.article_title}
      </h2>
      <p className="meta-line">
        Part {article.part_number}: {article.part_title}
      </p>

      <div className="chip-row">
        <Link href="/rome-statute" className="chip">
          All Parts
        </Link>
        <Link href={`/rome-statute/part/${encodeURIComponent(article.part_number)}`} className="chip">
          View Part {article.part_number}
        </Link>
      </div>

      <article className="result-card">
        <p style={{ whiteSpace: "pre-wrap" }}>{article.text}</p>
      </article>
    </section>
  );
}
