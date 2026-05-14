import { useState, useEffect } from 'react';

interface PlantUMLDiagramProps {
  chart: string;
}

// PlantUML text encoding
function encodePlantUML(text: string): string {
  const deflate = (s: string): number[] => {
    const arr: number[] = [];
    for (let i = 0; i < s.length; i++) {
      arr.push(s.charCodeAt(i));
    }
    return arr;
  };

  const encode6bit = (b: number): string => {
    if (b < 10) return String.fromCharCode(48 + b);
    b -= 10;
    if (b < 26) return String.fromCharCode(65 + b);
    b -= 26;
    if (b < 26) return String.fromCharCode(97 + b);
    b -= 26;
    if (b === 0) return '-';
    if (b === 1) return '_';
    return '?';
  };

  const append3bytes = (b1: number, b2: number, b3: number): string => {
    const c1 = b1 >> 2;
    const c2 = ((b1 & 0x3) << 4) | (b2 >> 4);
    const c3 = ((b2 & 0xF) << 2) | (b3 >> 6);
    const c4 = b3 & 0x3F;
    return encode6bit(c1 & 0x3F) + encode6bit(c2 & 0x3F) + encode6bit(c3 & 0x3F) + encode6bit(c4 & 0x3F);
  };

  const bytes = deflate(unescape(encodeURIComponent(text)));
  let encoded = '';

  for (let i = 0; i < bytes.length; i += 3) {
    if (i + 2 === bytes.length) {
      encoded += append3bytes(bytes[i], bytes[i + 1], 0);
    } else if (i + 1 === bytes.length) {
      encoded += append3bytes(bytes[i], 0, 0);
    } else {
      encoded += append3bytes(bytes[i], bytes[i + 1], bytes[i + 2]);
    }
  }

  return encoded;
}

export function PlantUMLDiagram({ chart }: PlantUMLDiagramProps) {
  const [imageUrl, setImageUrl] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    if (!chart) return;

    try {
      setIsLoading(true);
      setError('');

      // Wrap in @startuml/@enduml if not present
      let diagramCode = chart.trim();
      if (!diagramCode.startsWith('@start')) {
        diagramCode = `@startuml\n${diagramCode}\n@enduml`;
      }

      const encoded = encodePlantUML(diagramCode);
      const url = `https://www.plantuml.com/plantuml/svg/${encoded}`;
      setImageUrl(url);
      setIsLoading(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to encode diagram');
      setIsLoading(false);
    }
  }, [chart]);

  if (isLoading) {
    return (
      <div className="my-4 flex items-center justify-center rounded-lg border bg-card p-8">
        <div className="text-sm text-muted-foreground animate-pulse">
          Rendering PlantUML diagram...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="my-4 rounded-lg border border-destructive bg-destructive/10 p-4">
        <p className="text-sm font-medium text-destructive">
          Failed to render PlantUML diagram
        </p>
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
    <div className="my-4 flex flex-col items-center justify-center overflow-x-auto rounded-lg border bg-card p-4">
      <img
        src={imageUrl}
        alt="PlantUML Diagram"
        className="max-w-full h-auto"
        onError={() => setError('Failed to load diagram from PlantUML server')}
      />
      <div className="mt-2 text-xs text-muted-foreground">
        Rendered with PlantUML
      </div>
    </div>
  );
}
