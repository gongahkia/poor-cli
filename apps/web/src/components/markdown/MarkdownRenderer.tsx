import { memo } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";
import { DiagramBlock } from "@/components/diagrams/DiagramBlock";

type MarkdownRendererProps = {
  content: string;
};

const DIAGRAM_LANGUAGES = new Set(["mermaid", "diagram"]);

function MarkdownRendererInner({ content }: MarkdownRendererProps) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeKatex]}
      components={{
        code({ className, children, ...props }) {
          const text = String(children).replace(/\n$/, "");
          const language = /language-(\w+)/.exec(className ?? "")?.[1] ?? "";
          const isBlock = language !== "" || text.includes("\n");

          if (isBlock && DIAGRAM_LANGUAGES.has(language)) {
            return <DiagramBlock language={language} code={text} />;
          }

          if (isBlock) {
            return (
              <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
                <code className={className}>{text}</code>
              </pre>
            );
          }

          return (
            <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-sm" {...props}>
              {children}
            </code>
          );
        },
        table({ children }) {
          return (
            <div className="overflow-x-auto">
              <table className="min-w-full border-collapse border border-border text-sm">{children}</table>
            </div>
          );
        },
        th({ children }) {
          return <th className="border border-border bg-muted px-3 py-2 text-left font-semibold">{children}</th>;
        },
        td({ children }) {
          return <td className="border border-border px-3 py-2 align-top">{children}</td>;
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

export const MarkdownRenderer = memo(MarkdownRendererInner);
