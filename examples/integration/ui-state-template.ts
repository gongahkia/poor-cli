// UI integration template for Swee SG.
// Demonstrates how a frontend state layer can turn Pulse snapshots and Shield
// failures into concise operator states.

type PulseSignal = Readonly<{
  title: string;
  severity: "info" | "watch" | "disrupted";
  sourceTool: string;
  recommendedAction: string;
}>;

type PulseSourceHealth = Readonly<{
  sourceTool: string;
  status: "ready" | "stale" | "gap";
  recordCount: number;
}>;

type PulseSnapshot = Readonly<{
  generatedAt: string;
  signals: readonly PulseSignal[];
  sourceHealth: readonly PulseSourceHealth[];
  gaps: readonly Readonly<{ code: string; message: string }>[];
}>;

type PulseViewState =
  | Readonly<{
      kind: "disrupted";
      headline: string;
      action: string;
      sourceTool: string;
    }>
  | Readonly<{
      kind: "watch";
      headline: string;
      action: string;
      sourceTool: string;
    }>
  | Readonly<{
      kind: "source_gap";
      headline: string;
      gapCount: number;
    }>
  | Readonly<{
      kind: "normal";
      headline: string;
      readySources: number;
    }>;

export const toPulseViewState = (snapshot: PulseSnapshot): PulseViewState => {
  const disrupted = snapshot.signals.find((signal) => signal.severity === "disrupted");
  if (disrupted !== undefined) {
    return {
      kind: "disrupted",
      headline: disrupted.title,
      action: disrupted.recommendedAction,
      sourceTool: disrupted.sourceTool,
    };
  }

  const watch = snapshot.signals.find((signal) => signal.severity === "watch");
  if (watch !== undefined) {
    return {
      kind: "watch",
      headline: watch.title,
      action: watch.recommendedAction,
      sourceTool: watch.sourceTool,
    };
  }

  if (snapshot.gaps.length > 0 || snapshot.sourceHealth.some((source) => source.status === "gap")) {
    return {
      kind: "source_gap",
      headline: "Pulse has source gaps to review.",
      gapCount: Math.max(snapshot.gaps.length, snapshot.sourceHealth.filter((source) => source.status === "gap").length),
    };
  }

  return {
    kind: "normal",
    headline: "Pulse signals are normal.",
    readySources: snapshot.sourceHealth.filter((source) => source.status === "ready").length,
  };
};

export const renderBannerText = (state: PulseViewState): string => {
  if (state.kind === "disrupted") {
    return `${state.headline}. Check ${state.sourceTool}. ${state.action}`;
  }
  if (state.kind === "watch") {
    return `${state.headline}. Monitor ${state.sourceTool}. ${state.action}`;
  }
  if (state.kind === "source_gap") {
    return `${state.headline} ${state.gapCount} source gap(s) need review.`;
  }
  return `${state.headline} ${state.readySources} source(s) ready.`;
};

const demoSnapshots: readonly PulseSnapshot[] = [
  {
    generatedAt: new Date().toISOString(),
    signals: [{
      title: "Bukit Timah: heavy rain",
      severity: "disrupted",
      sourceTool: "sg_nea_rainfall",
      recommendedAction: "Check wet-weather plans for affected outdoor routes and sites.",
    }],
    sourceHealth: [{ sourceTool: "sg_nea_rainfall", status: "ready", recordCount: 12 }],
    gaps: [],
  },
  {
    generatedAt: new Date().toISOString(),
    signals: [],
    sourceHealth: [{ sourceTool: "sg_lta_traffic_incidents", status: "gap", recordCount: 0 }],
    gaps: [{ code: "SG_LTA_TRAFFIC_INCIDENTS_FAILED", message: "LTA request failed." }],
  },
];

for (const snapshot of demoSnapshots) {
  const state = toPulseViewState(snapshot);
  console.log(`[${state.kind}] ${renderBannerText(state)}`);
}
