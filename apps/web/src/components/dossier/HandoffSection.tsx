import { MarkdownRenderer } from "@/components/markdown/MarkdownRenderer";
import type { BusinessDossier } from "@/types/dossier";

const getHandoffMarkdown = (dossier: BusinessDossier): string | null => {
  const markdown = dossier.records.handoff?.["markdown"];
  return typeof markdown === "string" && markdown.trim() !== "" ? markdown : null;
};

export function HandoffSection({ dossier }: { dossier: BusinessDossier }) {
  const markdown = getHandoffMarkdown(dossier);
  if (markdown === null) {
    return null;
  }

  return (
    <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
      <h2 className="text-xl font-semibold tracking-normal text-foreground">Agent Handoff</h2>
      <div className="prose prose-sm mt-4 max-w-none text-muted-foreground prose-headings:text-foreground prose-strong:text-foreground">
        <MarkdownRenderer content={markdown} />
      </div>
    </section>
  );
}
