import type { QueryBlocker, ToolResult } from "@swee-sg/shared";

export type QueryExecutionContext = {
  readonly results: ReadonlyMap<
    string,
    {
      readonly input: Readonly<Record<string, unknown>>;
      readonly output: ToolResult;
    }
  >;
};

type QueryStepResolver = (
  context: QueryExecutionContext,
) => Promise<Readonly<Record<string, unknown>>> | Readonly<Record<string, unknown>>;

export type QueryStep = {
  readonly id: string;
  readonly purpose: string;
  readonly tool: string;
  readonly input: Readonly<Record<string, unknown>>;
  readonly dependsOn?: readonly string[];
  readonly resolveInput?: QueryStepResolver;
};

type SupportedQueryPlan = {
  readonly supported: true;
  readonly workflow: string;
  readonly intent: string;
  readonly confidence: number;
  readonly apis: readonly string[];
  readonly steps: readonly QueryStep[];
};

type BlockedQueryPlan = {
  readonly supported: false;
  readonly blocked: true;
  readonly workflow: string;
  readonly intent: string;
  readonly confidence: number;
  readonly apis: readonly string[];
  readonly steps: readonly QueryStep[];
  readonly blockers: readonly QueryBlocker[];
  readonly reason: string;
  readonly suggestion: string;
};

type UnsupportedQueryPlan = {
  readonly supported: false;
  readonly blocked?: false;
  readonly reason: string;
  readonly suggestion: string;
};

export type QueryPlan = SupportedQueryPlan | BlockedQueryPlan | UnsupportedQueryPlan;

type QueryPlanContext = Pick<SupportedQueryPlan, "workflow" | "intent" | "confidence" | "apis" | "steps">;

export const buildUnsupportedPlan = (reason: string, suggestion: string): QueryPlan => ({
  supported: false,
  reason,
  suggestion,
});

export const buildBlockedPlan = (
  context: QueryPlanContext,
  blockers: readonly QueryBlocker[],
  reason: string,
  suggestion: string,
): QueryPlan => ({
  supported: false,
  blocked: true,
  ...context,
  blockers,
  reason,
  suggestion,
});

export const createBlocker = (
  field: string,
  reason: string,
  directTool: string,
  exampleInput: Readonly<Record<string, unknown>>,
  suggestedPrompt: string,
): QueryBlocker => ({
  field,
  reason,
  directTool,
  exampleInput,
  suggestedPrompt,
});

export const buildDirectToolBlockedPlan = (
  workflow: string,
  intent: string,
  confidence: number,
  apis: readonly string[],
  tool: string,
  input: Readonly<Record<string, unknown>>,
  blockers: readonly QueryBlocker[],
  reason: string,
  suggestion: string,
): QueryPlan => buildBlockedPlan(
  {
    workflow,
    intent,
    confidence,
    apis,
    steps: [
      {
        id: "direct_tool",
        purpose: `Execute ${tool}.`,
        tool,
        input,
      },
    ],
  },
  blockers,
  reason,
  suggestion,
);
