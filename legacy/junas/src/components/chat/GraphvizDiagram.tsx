import { useEffect, useState } from 'react';
import { sanitizeSVG } from '@/lib/sanitize';

interface GraphvizDiagramProps {
  chart: string;
}

export function GraphvizDiagram({ chart }: GraphvizDiagramProps) {
  const [svg, setSvg] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    let mounted = true;

    const renderDiagram = async () => {
      if (!chart) return;

      try {
        setIsLoading(true);
        setError('');

        // Dynamically import viz.js
        const { instance } = await import('@viz-js/viz');
        const viz = await instance();

        // Wrap in digraph if not present
        let dotCode = chart.trim();
        if (
          !dotCode.startsWith('digraph') &&
          !dotCode.startsWith('graph') &&
          !dotCode.startsWith('strict')
        ) {
          dotCode = `digraph G {\n${dotCode}\n}`;
        }

        const result = viz.renderString(dotCode, { format: 'svg' });
        const sanitizedResult = await sanitizeSVG(result);

        if (mounted) {
          setSvg(sanitizedResult);
          setIsLoading(false);
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : 'Failed to render diagram');
          setIsLoading(false);
        }
      }
    };

    renderDiagram();

    return () => {
      mounted = false;
    };
  }, [chart]);

  if (isLoading) {
    return (
      <div className="my-4 flex items-center justify-center rounded-lg border bg-card p-8">
        <div className="text-sm text-muted-foreground animate-pulse">
          Rendering Graphviz diagram...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="my-4 rounded-lg border border-destructive bg-destructive/10 p-4">
        <p className="text-sm font-medium text-destructive">Failed to render Graphviz diagram</p>
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
      className="my-4 flex items-center justify-center overflow-x-auto rounded-lg border bg-card p-4"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
