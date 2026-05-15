import { lazy, Suspense } from "react";

import type { BusinessDossier } from "@/types/dossier";

const MarkdownRenderer = lazy(async () => {
  const module = await import("@/components/markdown/MarkdownRenderer");
  return { default: module.MarkdownRenderer };
});

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
    <section className="min-w-0 rounded-lg border border-border bg-card p-4 shadow-sm sm:p-5">
      <h2 className="text-xl font-semibold tracking-normal text-foreground">Agent Handoff</h2>
      <div className="prose prose-sm mt-4 max-w-none break-words text-muted-foreground prose-headings:text-foreground prose-strong:text-foreground">
        <Suspense fallback={<p className="text-sm text-muted-foreground">Loading handoff...</p>}>
          <MarkdownRenderer content={markdown} />
        </Suspense>
      </div>
    </section>
  );
}
