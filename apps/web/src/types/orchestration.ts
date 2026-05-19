export type CddOrchestratorStage = {
  id: string;
  label: string;
  status: "completed" | "skipped" | "blocked" | "unavailable";
  detail: string;
  tools: string[];
};

export type CddOrchestrationTrace = {
  status: "ready" | "identity_not_resolved";
  strategy: string;
  acraSectorHints: string[];
  webSectorHints: string[];
  effectiveSectorHints: string[];
  officialModules: string[];
  supplementalTools: string[];
  reranDossierForWebSectorHints: boolean;
  stages?: CddOrchestratorStage[];
  limits: string[];
};
