import { formatResponse, validateInput } from "@dude/shared";
import type { ToolResult } from "@dude/shared";
import { z } from "zod";
import {
  buildDossierInputFromResolutionCandidate,
  isResolutionCandidate,
  resolveCounterparty,
  type CounterpartyResolutionResult,
} from "../dude/counterparty-resolver.js";
import {
  normalizeCddOrchestratorInput,
  runCddOrchestrator,
  type CddOrchestratorResponse,
} from "../dude/cdd-orchestrator.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const BusinessDossierModuleSchema = z.enum(["acra", "bca", "cea", "gebiz", "boa", "hsa", "hlb"]);
const BusinessSectorHintSchema = z.enum(["construction", "real_estate", "architecture", "healthcare", "hospitality", "procurement"]);

const ResolveCounterpartySchema = z.object({
  identifier: z.string().min(1),
  modules: z.array(BusinessDossierModuleSchema).min(1).optional(),
  sectorHints: z.array(BusinessSectorHintSchema).min(1).optional(),
  limit: z.number().int().positive().max(20).optional(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

const CddReportSchema = z.object({
  identifier: z.string().min(1).optional(),
  entityName: z.string().min(1).optional(),
  uen: z.string().min(1).optional(),
  salespersonName: z.string().min(1).optional(),
  registrationNo: z.string().min(1).optional(),
  estateAgentName: z.string().min(1).optional(),
  estateAgentLicenseNo: z.string().min(1).optional(),
  classCode: z.string().min(1).optional(),
  workhead: z.string().min(1).optional(),
  grade: z.string().min(1).optional(),
  modules: z.array(BusinessDossierModuleSchema).min(1).optional(),
  sectorHints: z.array(BusinessSectorHintSchema).min(1).optional(),
  confirmedCandidate: z.unknown().optional(),
  includeContextIds: z.boolean().optional(),
  format: z.enum(["json", "markdown"]).optional(),
}).strict();

const renderResolutionMarkdown = (resolution: CounterpartyResolutionResult): string => [
  `## Counterparty resolution: ${resolution.status}`,
  "",
  `Input: ${resolution.originalInput}`,
  `Normalized input: ${resolution.normalizedInput || "not available"}`,
  "",
  "### Candidates",
  resolution.candidates.length === 0
    ? "_No retained CDD registry candidates matched._"
    : formatResponse(resolution.candidates.map((candidate) => ({
        label: candidate.label,
        source: candidate.sourceRegistry,
        identifier: candidate.uen ?? candidate.officialIdentifier,
        score: candidate.score,
        method: candidate.matchMethod,
        reason: candidate.matchReason,
      })), "markdown"),
  "",
  "### Confidence blockers",
  resolution.confidenceBlockers.length === 0
    ? "_No confidence blockers reported._"
    : formatResponse(resolution.confidenceBlockers.map((message) => ({ message })), "markdown"),
].join("\n");

const renderCddReportMarkdown = (response: CddOrchestratorResponse): string => [
  `## ${response.dossier.title}`,
  "",
  "### Summary",
  formatResponse(response.dossier.summary.map((item) => ({
    label: item.label,
    value: item.value,
    source: item.source,
  })), "markdown"),
  "",
  "### Orchestration",
  formatResponse(response.orchestration.stages.map((stage) => ({
    stage: stage.label,
    status: stage.status,
    detail: stage.detail,
  })), "markdown"),
  "",
  "### Gaps",
  response.dossier.gaps.length === 0
    ? "_No gaps reported._"
    : formatResponse(response.dossier.gaps.map((gap) => ({
        code: gap.code,
        message: gap.message,
      })), "markdown"),
].join("\n");

const toResolutionToolResult = (
  resolution: CounterpartyResolutionResult,
  format: "json" | "markdown" | undefined,
): ToolResult => ({
  content: [{
    type: "text",
    text: format === "json"
      ? formatResponse(resolution as unknown as Record<string, unknown>, "json")
      : renderResolutionMarkdown(resolution),
  }],
  structuredContent: resolution as unknown as Record<string, unknown>,
});

const toCddReportToolResult = (
  response: CddOrchestratorResponse,
  format: "json" | "markdown" | undefined,
): ToolResult => ({
  content: [{
    type: "text",
    text: format === "json"
      ? formatResponse(response as unknown as Record<string, unknown>, "json")
      : renderCddReportMarkdown(response),
  }],
  structuredContent: {
    status: "completed",
    record: response.dossier,
    dossier: response.dossier,
    webPresence: response.webPresence,
    peopleDiscovery: response.peopleDiscovery,
    memo: response.memo,
    orchestration: response.orchestration,
    generatedAt: response.generatedAt,
    ...(response.resolution === undefined ? {} : { resolution: response.resolution }),
  },
});

export const cddToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_resolve_counterparty",
    description: "Resolve a raw Singapore counterparty name or UEN into official CDD registry candidates before running a report.",
    surface: "canonical",
    preferred: true,
    positioning: "Safe entity-resolution preflight for agent and web CDD workflows.",
    inputSchema: ResolveCounterpartySchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const params = validateInput(ResolveCounterpartySchema, input);
      const resolution = await resolveCounterparty({
        identifier: params.identifier,
        ...(params.modules === undefined ? {} : { modules: params.modules }),
        ...(params.sectorHints === undefined ? {} : { sectorHints: params.sectorHints }),
        ...(params.limit === undefined ? {} : { limit: params.limit }),
      });
      return toResolutionToolResult(resolution, params.format);
    },
  },
  {
    name: "sg_cdd_report",
    description: "Run the CDD orchestrator after safe counterparty resolution, returning dossier, memo, evidence, gaps, provenance, freshness, and limits.",
    surface: "canonical",
    preferred: true,
    positioning: "Structured MCP-first CDD report interface for agents.",
    inputSchema: CddReportSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const params = validateInput(CddReportSchema, input);
      const confirmedCandidate = isResolutionCandidate(params.confirmedCandidate) ? params.confirmedCandidate : null;
      const dossierInput = confirmedCandidate === null
        ? normalizeCddOrchestratorInput(params)
        : {
            ...buildDossierInputFromResolutionCandidate(confirmedCandidate),
            ...(params.modules === undefined ? {} : { modules: params.modules }),
            ...(params.sectorHints === undefined ? {} : { sectorHints: params.sectorHints }),
            includeExternalDiligence: true,
          };
      const identifier = params.identifier ?? params.entityName;
      const shouldResolve = confirmedCandidate === null && params.uen === undefined && identifier !== undefined;
      const resolution = shouldResolve
        ? await resolveCounterparty({
            identifier,
            ...(params.modules === undefined ? {} : { modules: params.modules }),
            ...(params.sectorHints === undefined ? {} : { sectorHints: params.sectorHints }),
          })
        : null;

      if (resolution !== null && resolution.status !== "resolved") {
        return {
          content: [{
            type: "text",
            text: renderResolutionMarkdown(resolution),
          }],
          structuredContent: {
            status: resolution.status,
            resolution,
          },
        };
      }

      const effectiveInput = resolution?.selectedCandidate === undefined || resolution.selectedCandidate === null
        ? dossierInput
        : {
            ...buildDossierInputFromResolutionCandidate(resolution.selectedCandidate),
            ...(params.modules === undefined ? {} : { modules: params.modules }),
            ...(params.sectorHints === undefined ? {} : { sectorHints: params.sectorHints }),
            includeExternalDiligence: true,
          };
      const response = await runCddOrchestrator(effectiveInput, {
        ...(resolution === null ? {} : { resolution }),
      });
      return toCddReportToolResult(response, params.format);
    },
  },
];
