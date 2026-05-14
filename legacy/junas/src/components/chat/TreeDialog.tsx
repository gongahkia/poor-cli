import { useEffect, useState, useRef } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Message } from '@/types/chat';
import { generateDotTree } from '@/lib/chat-tree';
import { GitGraph } from 'lucide-react';

interface TreeDialogProps {
  isOpen: boolean;
  onClose: () => void;
  nodeMap: Record<string, Message>;
  currentLeafId?: string;
  onSelectNode: (nodeId: string) => void;
}

export function TreeDialog({ isOpen, onClose, nodeMap, currentLeafId, onSelectNode }: TreeDialogProps) {
  const [svg, setSvg] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;

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

        if (mounted) {
          setSvg(result);
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
  }, [isOpen, nodeMap, currentLeafId]);

  // Attach click listeners
  useEffect(() => {
    if (!containerRef.current || !svg) return;

    const nodes = containerRef.current.querySelectorAll('.node');
    const handlers: { element: Element, handler: () => void }[] = [];

    nodes.forEach(node => {
        const id = node.id.replace('node_', '');
        // Apply cursor pointer
        (node as HTMLElement).style.cursor = 'pointer';
        
        const handler = () => {
            onSelectNode(id);
            onClose();
        };
        
        node.addEventListener('click', handler);
        handlers.push({ element: node, handler });
    });

    return () => {
        handlers.forEach(({ element, handler }) => {
            element.removeEventListener('click', handler);
        });
    };
  }, [svg, onSelectNode, onClose]);

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden flex flex-col font-mono">
        <DialogHeader>
          <DialogTitle className="text-sm font-mono uppercase tracking-widest flex items-center gap-2">
            <GitGraph className="h-4 w-4" />
            Conversation Tree
          </DialogTitle>
        </DialogHeader>

        <div className="flex-1 overflow-auto bg-muted/10 rounded-md p-4 flex items-center justify-center min-h-[300px]">
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
      </DialogContent>
    </Dialog>
  );
}
