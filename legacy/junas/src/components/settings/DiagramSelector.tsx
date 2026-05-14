import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { DiagramRenderer } from '@/types/chat';

interface DiagramSelectorProps {
  currentRenderer: DiagramRenderer;
  onRendererChange: (renderer: DiagramRenderer) => void;
}

const renderers: { id: DiagramRenderer; name: string; description: string }[] = [
  {
    id: 'mermaid',
    name: 'Mermaid',
    description: 'Client-side rendering, supports flowcharts, sequence diagrams, ERDs, and more',
  },
  {
    id: 'plantuml',
    name: 'PlantUML',
    description: 'Server-side rendering via PlantUML server, excellent UML support',
  },
  {
    id: 'graphviz',
    name: 'Graphviz',
    description: 'Client-side DOT language rendering, great for directed graphs',
  },
  {
    id: 'd2',
    name: 'D2',
    description: 'Modern declarative diagramming, opens in D2 Playground',
  },
];

export function DiagramSelector({ currentRenderer, onRendererChange }: DiagramSelectorProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Diagram Renderer</CardTitle>
        <CardDescription>
          Choose which diagram rendering system to use for visualizations.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-3">
          {renderers.map((renderer) => (
            <button
              key={renderer.id}
              onClick={() => onRendererChange(renderer.id)}
              className={`p-3 rounded-lg border text-left transition-all ${
                currentRenderer === renderer.id
                  ? 'border-primary bg-primary/5 ring-1 ring-primary'
                  : 'border-border hover:border-primary/50 hover:bg-muted/50'
              }`}
            >
              <div className="font-medium text-sm">{renderer.name}</div>
              <div className="text-xs text-muted-foreground mt-1">
                {renderer.description}
              </div>
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
