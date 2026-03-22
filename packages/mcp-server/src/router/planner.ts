import { classifyIntent, resolveToolInput } from "./classifier.js";

export type QueryStep = {
  readonly tool: string;
  readonly input: Readonly<Record<string, unknown>>;
};

export type QueryPlan =
  | {
      readonly supported: true;
      readonly step: QueryStep;
    }
  | {
      readonly supported: false;
      readonly reason: string;
      readonly suggestion: string;
    };

const buildUnsupportedPlan = (reason: string, suggestion: string): QueryPlan => ({
  supported: false,
  reason,
  suggestion,
});

export const planQuery = (query: string): QueryPlan => {
  const intent = classifyIntent(query);
  const lower = query.toLowerCase();
  const isComparison = /compare|vs\.?|versus|between\s+.+\s+and\s+.+/i.test(lower);

  if (isComparison) {
    return buildUnsupportedPlan(
      "sg_query only routes one direct tool call at a time and does not run comparisons for you.",
      "Call the relevant direct tool separately for each item you want to compare.",
    );
  }

  if (
    intent.extractedParams["postalCode"] !== undefined
    && /population|demographic|age|income|ethnic|dwelling/i.test(lower)
  ) {
    return buildUnsupportedPlan(
      "sg_query does not chain geocoding into population lookups.",
      "Call sg_onemap_geocode first, then pass the resolved planning area into sg_onemap_population.",
    );
  }

  if (intent.tool === "sg_onemap_route") {
    return buildUnsupportedPlan(
      "sg_query cannot infer route endpoints or route type from free-form text reliably enough.",
      "Call sg_onemap_route directly with explicit start/end coordinates and a route type.",
    );
  }

  if (intent.tool === "sg_onemap_population" && intent.extractedParams["planningArea"] === undefined) {
    return buildUnsupportedPlan(
      "sg_query needs a planning area name before it can request demographic data.",
      "Call sg_onemap_population directly with a planningArea value.",
    );
  }

  if (intent.tool === "sg_ura_planning_area" && intent.extractedParams["planningArea"] === undefined) {
    return buildUnsupportedPlan(
      "sg_query needs a planning area name for URA master plan lookups.",
      "Call sg_ura_planning_area directly with planningArea, or provide lat and lng yourself.",
    );
  }

  return {
    supported: true,
    step: resolveToolInput(intent, query),
  };
};
