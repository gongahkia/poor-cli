import { useEffect, useState } from "react";
import { sanitizeSVG } from "@/lib/sanitize";

type MermaidDiagramProps = {
  chart: string;
};

let mermaidInitialized = false;

export function MermaidDiagram({ chart }: MermaidDiagramProps) {
  const [svg, setSvg] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    async function renderDiagram() {
      if (chart.trim() === "") {
        setIsLoading(false);
        return;
      }

      try {
        setIsLoading(true);
        setError("");
        const mermaid = (await import("mermaid")).default;

        if (!mermaidInitialized) {
          mermaid.initialize({
            startOnLoad: false,
            theme: "default",
            securityLevel: "strict",
            flowchart: {
              useMaxWidth: true,
              htmlLabels: false,
              curve: "basis",
            },
            themeVariables: {
              fontSize: "14px",
            },
            logLevel: "fatal",
          });
          mermaidInitialized = true;
        }

        const id = `mermaid-${Date.now()}-${Math.random().toString(36).slice(2)}`;
        const { svg: renderedSvg } = await mermaid.render(id, chart);
        const sanitizedSvg = await sanitizeSVG(renderedSvg);

        if (mounted) {
          setSvg(sanitizedSvg);
          setIsLoading(false);
        }
      } catch (renderError) {
        if (mounted) {
          setError(renderError instanceof Error ? renderError.message : "Failed to render diagram");
          setIsLoading(false);
        }
      }
    }

    void renderDiagram();
    return () => {
      mounted = false;
    };
  }, [chart]);

  if (isLoading) {
    return (
      <div className="my-4 flex items-center justify-center rounded-md border bg-card p-8">
        <div className="text-sm text-muted-foreground">Rendering diagram...</div>
      </div>
    );
  }

  if (error !== "") {
    return (
      <div className="my-4 rounded-md border border-destructive bg-destructive/10 p-4">
        <p className="text-sm font-medium text-destructive">Failed to render diagram</p>
        <p className="mt-1 text-xs text-muted-foreground">{error}</p>
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
            Show diagram code
          </summary>
          <pre className="mt-2 overflow-x-auto rounded bg-muted p-2 text-xs">
            <code>{chart}</code>
          </pre>
        </details>
      </div>
    );
  }

  return (
    <div
      className="my-4 flex items-center justify-center overflow-x-auto rounded-md border bg-card p-4"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
