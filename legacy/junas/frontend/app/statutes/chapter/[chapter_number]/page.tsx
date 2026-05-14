import Link from "next/link";
import { getChapterSections } from "../../../../lib/api-server";

type SectionItem = {
  number: string;
  name: string;
};

type ChapterResponse = {
  chapter_number: string;
  sections: SectionItem[];
};

export default async function ChapterPage({ params }: { params: { chapter_number: string } }) {
  const chapterNumber = decodeURIComponent(params.chapter_number);
  const chapter = ((await getChapterSections(chapterNumber)) ??
    { chapter_number: chapterNumber, sections: [] }) as ChapterResponse;

  return (
    <section>
      <p>
        <Link href="/statutes">Statutes</Link> / Chapter {chapter.chapter_number}
      </p>
      <h2>Chapter {chapter.chapter_number}</h2>
      <p>Section table of contents for this chapter.</p>

      <ul className="chapter-list">
        {chapter.sections.map((section) => (
          <li key={section.number}>
            <Link href={`/statutes/section/${encodeURIComponent(section.number)}`}>
              <strong>{section.number}</strong>
            </Link>{" "}
            {section.name}
          </li>
        ))}
      </ul>
    </section>
  );
}
