import { classifyIntent, resolveTools } from "./classifier.js";

export type QueryStep = {
  readonly tool: string;
  readonly input: Readonly<Record<string, unknown>>;
  readonly dependsOn?: number;
};

export type QueryPlan = {
  readonly steps: readonly QueryStep[];
  readonly parallel: boolean;
};

export const planQuery = (query: string): QueryPlan => {
  const intent = classifyIntent(query);
  const tools = resolveTools(intent);

  // Check for comparison queries
  const lower = query.toLowerCase();
  const isComparison = /compare|vs\.?|versus|between.*and/i.test(lower);

  if (isComparison && intent.extractedParams["planningArea"] !== undefined) {
    // Extract multiple areas
    const areas = lower.match(/(?:between\s+)?(\w+)\s+(?:and|vs\.?|versus)\s+(\w+)/i);
    if (areas !== null) {
      return {
        steps: [
          { tool: tools[0]?.tool ?? "sg_datagov_search", input: { ...tools[0]?.input, area: areas[1] } },
          { tool: tools[0]?.tool ?? "sg_datagov_search", input: { ...tools[0]?.input, area: areas[2] } },
        ],
        parallel: true,
      };
    }
  }

  // Check for sequential dependency (geocode then population)
  if (intent.intent === "geospatial" && /population|demographic/i.test(lower)) {
    return {
      steps: [
        { tool: "sg_onemap_geocode", input: { searchVal: (intent.extractedParams["postalCode"] ?? "") as string } },
        { tool: "sg_onemap_population", input: { planningArea: "" }, dependsOn: 0 },
      ],
      parallel: false,
    };
  }

  return {
    steps: tools.map((t) => ({ tool: t.tool, input: t.input })),
    parallel: tools.length > 1,
  };
};
