import { useEffect, useState, useRef } from 'react';
import { Message } from '@/types/chat';
import { generateDotTree } from '@/lib/chat-tree';
import { sanitizeSVG } from '@/lib/sanitize';

interface TreeViewProps {
  nodeMap: Record<string, Message>;
  currentLeafId?: string;
  onSelectNode: (nodeId: string) => void;
}

export function TreeView({ nodeMap, currentLeafId, onSelectNode }: TreeViewProps) {
  const [svg, setSvg] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let mounted = true;

    const renderDiagram = async () => {
      try {
        setIsLoading(true);
        setError('');

        const isDarkMode = document.documentElement.classList.contains('dark');
        const chart = generateDotTree(nodeMap, currentLeafId, isDarkMode);

        // Dynamically import viz.js
        const { instance } = await import('@viz-js/viz');
        const viz = await instance();

        const result = viz.renderString(chart, { format: 'svg' });
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
  }, [nodeMap, currentLeafId]);

  // Attach click listeners using event delegation
  useEffect(() => {
    if (!containerRef.current || !svg) return;

    const container = containerRef.current;

    // Apply cursor pointer to nodes
    const nodes = container.querySelectorAll('[id^="node_"]');
    nodes.forEach((node) => {
      (node as HTMLElement).style.cursor = 'pointer';
    });

    const handleClick = (e: MouseEvent) => {
      let target = e.target as Element | null;

      // Traverse up to find the node group
      while (target && target !== container) {
        if (target.id && target.id.startsWith('node_')) {
          const id = target.id.replace('node_', '');
          onSelectNode(id);
          return;
        }
        target = target.parentElement;
      }
    };

    container.addEventListener('click', handleClick);

    return () => {
      container.removeEventListener('click', handleClick);
    };
  }, [svg, onSelectNode]);

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden p-4">
      <div className="flex-1 overflow-auto bg-muted/10 rounded-md p-4 flex items-center justify-center min-h-[300px] border border-muted-foreground/10 no-scrollbar">
        {isLoading ? (
          <div className="text-sm text-muted-foreground animate-pulse">Generating tree view...</div>
        ) : error ? (
          <div className="text-sm text-red-500">{error}</div>
        ) : (
          <div
            ref={containerRef}
            dangerouslySetInnerHTML={{ __html: svg }}
            className="w-full h-full flex justify-center"
          />
        )}
      </div>

      <div className="mt-2 text-center text-[10px] text-muted-foreground">
        Click on any node to jump to that point in the conversation.
      </div>
    </div>
  );
}
