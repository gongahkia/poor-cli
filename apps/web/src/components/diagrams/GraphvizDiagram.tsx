type GraphvizDiagramProps = {
  chart: string;
};

export function GraphvizDiagram({ chart }: GraphvizDiagramProps) {
  return (
    <div className="my-4 rounded-md border bg-card p-4">
      <p className="text-sm font-medium text-foreground">Graphviz diagram</p>
      <p className="mt-1 text-xs text-muted-foreground">
        Graphviz rendering is deferred until the client-side viz-js dependency ships with relationship graphs.
      </p>
      <pre className="mt-3 overflow-x-auto rounded bg-muted p-3 text-xs">
        <code>{chart}</code>
      </pre>
    </div>
  );
}
