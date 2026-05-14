import { useState } from 'react';
import { ExternalLink, Copy, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface D2DiagramProps {
  chart: string;
}

export function D2Diagram({ chart }: D2DiagramProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(chart);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const playgroundUrl = `https://play.d2lang.com/?script=${encodeURIComponent(chart)}`;

  return (
    <div className="my-4 rounded-lg border bg-card p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium text-foreground">D2 Diagram</span>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleCopy}
            className="h-7 text-xs"
          >
            {copied ? <Check className="w-3 h-3 mr-1" /> : <Copy className="w-3 h-3 mr-1" />}
            {copied ? 'Copied' : 'Copy'}
          </Button>
          <Button
            variant="outline"
            size="sm"
            asChild
            className="h-7 text-xs"
          >
            <a href={playgroundUrl} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="w-3 h-3 mr-1" />
              Open in D2 Playground
            </a>
          </Button>
        </div>
      </div>
      <pre className="overflow-x-auto rounded bg-muted p-3 text-xs">
        <code>{chart}</code>
      </pre>
      <p className="mt-2 text-xs text-muted-foreground">
        D2 diagrams require the D2 CLI or playground to render. Click "Open in D2 Playground" to view the rendered diagram.
      </p>
    </div>
  );
}
