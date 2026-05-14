import { GraphvizDiagram } from "./GraphvizDiagram";
import { MermaidDiagram } from "./MermaidDiagram";

type DiagramBlockProps = {
  language: string;
  code: string;
};

export function DiagramBlock({ language, code }: DiagramBlockProps) {
  const normalizedLanguage = language.toLowerCase();

  if (normalizedLanguage === "mermaid" || normalizedLanguage === "diagram") {
    return <MermaidDiagram chart={code} />;
  }

  if (normalizedLanguage === "graphviz" || normalizedLanguage === "dot") {
    return <GraphvizDiagram chart={code} />;
  }

  return (
    <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
      <code>{code}</code>
    </pre>
  );
}
