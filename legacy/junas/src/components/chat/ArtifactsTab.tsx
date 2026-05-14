import React from 'react';
import { Artifact } from '@/types/chat';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { FileText, Download, Copy, Check } from 'lucide-react';
import { useToast } from '@/components/ui/toast';

interface ArtifactsTabProps {
  artifacts: Artifact[];
}

export function ArtifactsTab({ artifacts }: ArtifactsTabProps) {
  const { addToast } = useToast();
  const [copiedId, setCopiedId] = React.useState<string | null>(null);

  const handleCopy = async (content: string, id: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
      addToast({
        title: 'Copied',
        description: 'Artifact content copied to clipboard',
        type: 'success',
      });
    } catch (err) {
        addToast({
            title: 'Error',
            description: 'Failed to copy to clipboard',
            type: 'error',
        });
    }
  };

  const handleDownload = (artifact: Artifact) => {
    const blob = new Blob([artifact.content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${artifact.title.replace(/\s+/g, '_')}.${artifact.type === 'markdown' ? 'md' : 'txt'}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  if (artifacts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground p-8 font-mono">
        <p>No artifacts generated yet.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4 h-full overflow-y-auto">
      {artifacts.map((artifact) => (
        <Card key={artifact.id} className="flex flex-col">
          <CardHeader className="pb-2">
            <div className="flex justify-between items-start">
              <div>
                <CardTitle className="text-lg">{artifact.title}</CardTitle>
                <CardDescription>
                    {artifact.type.toUpperCase()} • {new Date(artifact.createdAt).toLocaleString()}
                </CardDescription>
              </div>
              <div className="flex gap-2">
                 <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => handleCopy(artifact.content, artifact.id)}
                  title="Copy content"
                >
                  {copiedId === artifact.id ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => handleDownload(artifact)}
                  title="Download"
                >
                  <Download className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="bg-muted/50 p-3 rounded-md max-h-40 overflow-hidden relative group">
                <pre className="text-xs font-mono whitespace-pre-wrap break-words text-muted-foreground">
                    {artifact.content.slice(0, 300)}
                    {artifact.content.length > 300 && '...'}
                </pre>
                <div className="absolute inset-0 bg-gradient-to-b from-transparent to-muted/10 pointer-events-none" />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
