import { useEffect, useState } from 'react';
import { sanitizeSVG } from '@/lib/sanitize';

interface MermaidDiagramProps {
  chart: string;
}

// Track if mermaid has been initialized globally
let mermaidInitialized = false;

export function MermaidDiagram({ chart }: MermaidDiagramProps) {
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

        // Dynamically import mermaid to avoid SSR issues
        const mermaid = (await import('mermaid')).default;

        // Initialize mermaid only once
        if (!mermaidInitialized) {
          mermaid.initialize({
            startOnLoad: false,
            theme: 'default',
            securityLevel: 'strict',
            fontFamily: 'var(--font-geist-sans), sans-serif',
            flowchart: {
              useMaxWidth: true,
              htmlLabels: false,
              curve: 'basis',
            },
            themeVariables: {
              fontSize: '14px',
            },
            logLevel: 'fatal', // Suppress internal logging
          });
          mermaidInitialized = true;
        }

        // Create a temporary container for rendering
        const tempContainer = document.createElement('div');
        tempContainer.style.position = 'absolute';
        tempContainer.style.visibility = 'hidden';
        tempContainer.style.pointerEvents = 'none';
        document.body.appendChild(tempContainer);

        // Generate unique ID
        const id = `mermaid-${Date.now()}-${Math.random().toString(36).substring(7)}`;

        // Suppress ALL console methods during rendering
        const originalConsole = {
          error: console.error,
          warn: console.warn,
          log: console.log,
        };
        console.error = () => {};
        console.warn = () => {};
        console.log = () => {};

        try {
          // Render the diagram
          const { svg: renderedSvg } = await mermaid.render(id, chart);

          // Check if the rendered SVG contains error indicators
          const hasError =
            renderedSvg.includes('Syntax error') ||
            renderedSvg.includes('Parse error') ||
            renderedSvg.includes('error in text');

          if (hasError) {
            throw new Error('Diagram contains syntax errors');
          }

          const sanitizedSvg = await sanitizeSVG(renderedSvg);

          if (mounted && sanitizedSvg && sanitizedSvg.length > 0) {
            setSvg(sanitizedSvg);
            setIsLoading(false);
          } else {
            throw new Error('Failed to generate diagram');
          }
        } finally {
          // Always restore console and cleanup
          console.error = originalConsole.error;
          console.warn = originalConsole.warn;
          console.log = originalConsole.log;

          // Remove temporary container
          if (tempContainer.parentNode) {
            tempContainer.parentNode.removeChild(tempContainer);
          }

          // Clean up any Mermaid error elements that might have been added to DOM
          const errorElements = document.querySelectorAll('[id^="' + id + '"]');
          errorElements.forEach((el) => {
            if (el.parentNode) {
              el.parentNode.removeChild(el);
            }
          });
        }
      } catch (err) {
        if (mounted) {
          const errorMessage = err instanceof Error ? err.message : 'Failed to render diagram';
          setError(errorMessage);
          setIsLoading(false);
        }
      }
    };

    renderDiagram();

    // Cleanup function
    return () => {
      mounted = false;
    };
  }, [chart]);

  if (isLoading) {
    return (
      <div className="my-4 flex items-center justify-center rounded-lg border bg-card p-8">
        <div className="text-sm text-muted-foreground animate-pulse">Rendering diagram...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="my-4 rounded-lg border border-destructive bg-destructive/10 p-4">
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
      className="my-4 flex items-center justify-center overflow-x-auto rounded-lg border bg-card p-4"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
