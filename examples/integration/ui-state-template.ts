// UI integration template for Dude MCP.
// Demonstrates how a frontend state layer can handle blocked / unsupported / failed
// outcomes from sg_query without treating every non-completed status as a crash.

type QueryBlocker = Readonly<{
  field: string;
  directTool: string;
  suggestedPrompt: string;
}>;

type QueryOutcome = Readonly<{
  status: "planned" | "completed" | "blocked" | "unsupported" | "failed";
  workflow?: string;
  reason?: string;
  suggestion?: string;
  blockers?: readonly QueryBlocker[];
  failedStep?: Readonly<{
    tool?: string;
    error?: Readonly<{
      code?: string;
      message?: string;
      suggestedAction?: string;
    }>;
  }> | null;
  toolsUsed?: readonly string[];
}>;

type QueryViewState =
  | Readonly<{
      kind: "success";
      headline: string;
      workflow?: string;
      toolsUsed: readonly string[];
    }>
  | Readonly<{
      kind: "needs_input";
      headline: string;
      blockerField: string;
      blockerTool: string;
      recoveryPrompt: string;
    }>
  | Readonly<{
      kind: "unsupported";
      headline: string;
      suggestion: string;
    }>
  | Readonly<{
      kind: "error";
      headline: string;
      detail: string;
      retryable: boolean;
    }>;

const fallbackSuggestion = "Try sg://recipes or call a direct sg_* tool with exact parameters.";

export const toQueryViewState = (outcome: QueryOutcome): QueryViewState => {
  if (outcome.status === "completed") {
    return {
      kind: "success",
      headline: "Workflow completed",
      ...(outcome.workflow === undefined ? {} : { workflow: outcome.workflow }),
      toolsUsed: outcome.toolsUsed ?? [],
    };
  }

  if (outcome.status === "blocked") {
    const first = outcome.blockers?.[0];
    return {
      kind: "needs_input",
      headline: outcome.reason ?? "Need one more field before this workflow can run.",
      blockerField: first?.field ?? "unknown",
      blockerTool: first?.directTool ?? "unknown",
      recoveryPrompt: first?.suggestedPrompt ?? "",
    };
  }

  if (outcome.status === "unsupported") {
    return {
      kind: "unsupported",
      headline: outcome.reason ?? "Prompt is outside bounded workflow coverage.",
      suggestion: outcome.suggestion ?? fallbackSuggestion,
    };
  }

  if (outcome.status === "failed") {
    const message = outcome.failedStep?.error?.message
      ?? outcome.reason
      ?? "Workflow execution failed.";
    const code = outcome.failedStep?.error?.code;
    const retryable = code === "TIMEOUT" || code === "NETWORK_ERROR" || code === "RETRY_EXHAUSTED";

    return {
      kind: "error",
      headline: "Workflow failed",
      detail: message,
      retryable,
    };
  }

  return {
    kind: "unsupported",
    headline: `Unhandled sg_query status: ${outcome.status}`,
    suggestion: fallbackSuggestion,
  };
};

export const renderBannerText = (state: QueryViewState): string => {
  if (state.kind === "success") {
    const workflow = state.workflow === undefined ? "unknown-workflow" : state.workflow;
    const tools = state.toolsUsed.length === 0 ? "no direct tools reported" : state.toolsUsed.join(", ");
    return `Completed ${workflow}. Tools used: ${tools}.`;
  }

  if (state.kind === "needs_input") {
    return `${state.headline} Missing "${state.blockerField}" for ${state.blockerTool}.`;
  }

  if (state.kind === "unsupported") {
    return `${state.headline} ${state.suggestion}`;
  }

  return state.retryable
    ? `${state.headline}. ${state.detail} Retry is safe after a short delay.`
    : `${state.headline}. ${state.detail} Manual intervention is required.`;
};

// Example outcomes to quickly test the view-state mapper in isolation.
const demoOutcomes: readonly QueryOutcome[] = [
  {
    status: "blocked",
    reason: "sg_query needs a company name, entity name, UEN, salesperson, or estate-agent identifier to run registry diligence.",
    blockers: [{ field: "entityName", directTool: "sg_business_dossier", suggestedPrompt: "Business dossier for DP Architects" }],
  },
  {
    status: "unsupported",
    reason: "The prompt did not match a bounded Singapore workflow.",
  },
  {
    status: "failed",
    reason: "Business dossier execution failed.",
    failedStep: {
      tool: "sg_business_dossier",
      error: { code: "UPSTREAM_TIMEOUT", message: "ACRA request timed out." },
    },
  },
];

for (const outcome of demoOutcomes) {
  const state = toQueryViewState(outcome);
  console.log(`[${state.kind}] ${renderBannerText(state)}`);
}
