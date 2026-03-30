import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { completable } from "@modelcontextprotocol/sdk/server/completable.js";
import { z } from "zod";
import {
  NORMALIZED_PLAYBOOK_CATALOG,
  NORMALIZED_RECIPE_CATALOG,
  type PromptArgumentDefinition,
  type PromptArgumentValues,
} from "./catalog-surface.js";
import { COORDINATE_SYSTEMS, OUTPUT_FORMATS, PLANNING_AREAS, REGIONS, ROUTE_MODES, toTitleCase } from "../router/domain-constants.js";

const joinSection = (title: string, lines: readonly string[]): string => {
  if (lines.length === 0) {
    return "";
  }
  return `${title}\n${lines.map((line) => `- ${line}`).join("\n")}`;
};

const PROMPT_COMPLETIONS = {
  planningArea: PLANNING_AREAS.map((value) => toTitleCase(value)),
  region: REGIONS.map((value) => toTitleCase(value)),
  routeMode: [...ROUTE_MODES],
  outputFormat: [...OUTPUT_FORMATS],
  coordinateSystem: [...COORDINATE_SYSTEMS],
  communityOutletType: ["community_club", "passion_wave"],
  developmentChargeSector: ["A", "B1", "B2", "C"],
} as const;

const formatPromptArgumentValue = (value: string | number | undefined): string => {
  if (value === undefined) {
    return "(not provided)";
  }
  return typeof value === "number" ? String(value) : value;
};

const buildVariableCompletion = (values: readonly string[]) => {
  return (value: string): string[] => {
    const lower = value.toLowerCase();
    return values.filter((candidate) => candidate.toLowerCase().startsWith(lower));
  };
};

const toPromptArgsSchema = (args: readonly PromptArgumentDefinition[]) => {
  const shape: Record<string, z.ZodTypeAny> = {};

  for (const arg of args) {
    const completionValues = arg.completionSource === undefined ? undefined : PROMPT_COMPLETIONS[arg.completionSource];

    let schema: z.ZodTypeAny;
    switch (arg.kind) {
      case "number":
        schema = z.number().describe(arg.description);
        break;
      case "enum":
        if (arg.enumValues === undefined || arg.enumValues.length === 0) {
          schema = z.string().min(1).describe(arg.description);
          break;
        }
        schema = z.enum([arg.enumValues[0]!, ...arg.enumValues.slice(1)] as [string, ...string[]]).describe(arg.description);
        break;
      default:
        schema = z.string().min(1).describe(arg.description);
        break;
    }

    if (arg.required !== true) {
      schema = schema.optional();
    }

    if (completionValues !== undefined && arg.kind !== "number") {
      schema = completable(schema, buildVariableCompletion(completionValues));
    }

    shape[arg.name] = schema;
  }

  return shape;
};

const buildConcreteInputsSection = (
  args: PromptArgumentValues,
  definitions: readonly PromptArgumentDefinition[] | undefined,
): string => {
  if (definitions === undefined || definitions.length === 0) {
    return "";
  }

  const lines = definitions.map((definition) => (
    `${definition.name}: ${formatPromptArgumentValue(args[definition.name])}`
  ));
  return joinSection("Resolved inputs", lines);
};

const buildRecipePromptText = (
  entry: (typeof NORMALIZED_RECIPE_CATALOG)[number],
  args: PromptArgumentValues,
): string => {
  const starterPrompt = entry.promptMetadata?.buildStarterPrompt(args) ?? entry.prompt;
  const preferredInput = entry.promptMetadata?.buildPreferredEntrypointInput?.(args)
    ?? {
      ...entry.preferredEntrypoint.input,
      ...(typeof entry.preferredEntrypoint.input["query"] === "string" ? { query: starterPrompt } : {}),
    };
  const sections = [
    `Use the "${entry.name}" Singapore workflow recipe.`,
    "",
    `Goal: ${entry.goal}`,
    `Starter prompt: ${starterPrompt}`,
    `Preferred entrypoint: call ${entry.preferredEntrypoint.tool} with ${JSON.stringify(preferredInput)}.`,
    buildConcreteInputsSection(args, entry.promptMetadata?.args),
    joinSection("Fallback tools", entry.fallbackTools),
    joinSection("Required inputs", entry.requiredInputs ?? []),
    joinSection("Blockers", entry.blockerFields ?? []),
    joinSection("Continuation tools", entry.continuationTools ?? []),
    joinSection("Notes", entry.notes),
  ].filter((section) => section !== "");

  return sections.join("\n\n");
};

const buildPlaybookPromptText = (
  entry: (typeof NORMALIZED_PLAYBOOK_CATALOG)[number],
  args: PromptArgumentValues,
): string => {
  const starterPrompt = entry.promptMetadata?.buildStarterPrompt(args);
  const sections = [
    `Use the "${entry.name}" Singapore playbook for a ${entry.persona}.`,
    "",
    ...(starterPrompt === undefined ? [] : [`Starter prompt: ${starterPrompt}`, ""]),
    buildConcreteInputsSection(args, entry.promptMetadata?.args),
    joinSection("Jobs to be done", entry.jobsToBeDone),
    joinSection("Primary workflows", entry.primaryWorkflows),
    joinSection("Starter prompts", entry.starterPrompts),
    joinSection("Direct tools", entry.directTools),
    joinSection("Recommended resources", entry.recommendedResources),
    joinSection("Notes", entry.notes),
  ].filter((section) => section !== "");

  return sections.join("\n\n");
};

export const registerPrompts = (server: McpServer): void => {
  for (const recipe of NORMALIZED_RECIPE_CATALOG) {
    server.registerPrompt(`recipe-${recipe.id}`, {
      title: recipe.name,
      description: recipe.goal,
      ...(recipe.promptMetadata === undefined ? {} : { argsSchema: toPromptArgsSchema(recipe.promptMetadata.args) }),
    }, async (args = {}) => ({
      description: recipe.goal,
      messages: [
        {
          role: "user",
          content: {
            type: "text",
            text: buildRecipePromptText(recipe, args as PromptArgumentValues),
          },
        },
      ],
    }));
  }

  for (const playbook of NORMALIZED_PLAYBOOK_CATALOG) {
    server.registerPrompt(`playbook-${playbook.id}`, {
      title: playbook.name,
      description: `Persona-oriented workflow bundle for ${playbook.persona}.`,
      ...(playbook.promptMetadata === undefined ? {} : { argsSchema: toPromptArgsSchema(playbook.promptMetadata.args) }),
    }, async (args = {}) => ({
      description: `Persona-oriented workflow bundle for ${playbook.persona}.`,
      messages: [
        {
          role: "user",
          content: {
            type: "text",
            text: buildPlaybookPromptText(playbook, args as PromptArgumentValues),
          },
        },
      ],
    }));
  }
};
