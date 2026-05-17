import { z } from "zod";
import type { ToolResult } from "@dude/shared";
import type { RegisteredToolDefinition } from "./tool-definition.js";
import {
  buildAdverseMediaLiteArtifact,
  buildOpenCorporatesLinksArtifact,
  buildRelationshipGraphArtifact,
  buildSanctionsScreenArtifact,
  toBriefToolResult,
} from "../diligence/external-diligence.js";

const OutputFormatSchema = z.enum(["json", "markdown"]).optional();

const SanctionsScreenSchema = z.object({
  name: z.string().min(1),
  uen: z.string().min(1).optional(),
  threshold: z.number().min(0).max(1).optional(),
  limit: z.number().int().positive().max(25).optional(),
  dataset: z.string().min(1).optional(),
  format: OutputFormatSchema,
}).strict();

const OpenCorporatesSchema = z.object({
  entityName: z.string().min(1),
  uen: z.string().min(1).optional(),
  jurisdictionCode: z.string().min(2).max(8).optional(),
  limit: z.number().int().positive().max(25).optional(),
  format: OutputFormatSchema,
}).strict();

const AdverseMediaLiteSchema = z.object({
  keyword: z.string().min(1),
  feedIds: z.array(z.string().min(1)).min(1).optional(),
  limitPerFeed: z.number().int().positive().max(25).optional(),
  format: OutputFormatSchema,
}).strict();

const RelationshipGraphSchema = z.object({
  records: z.record(z.unknown()),
  format: OutputFormatSchema,
}).strict();

export const externalDiligenceToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_sanctions_screen",
    description: "Screen a company name and optional UEN against OpenSanctions candidate matches with provenance, freshness, gaps, and license-aware limits.",
    surface: "canonical",
    positioning: "Bounded external diligence adapter; candidate screening only.",
    inputSchema: SanctionsScreenSchema.shape,
    toolsets: ["diligence"],
    handler: async (input: unknown): Promise<ToolResult> => {
      const params = SanctionsScreenSchema.parse(input);
      return toBriefToolResult(await buildSanctionsScreenArtifact(params), params.format ?? "json");
    },
  },
  {
    name: "sg_opencorporates_links",
    description: "Find OpenCorporates company cross-links for a Singapore entity without inferring ownership or control.",
    surface: "canonical",
    positioning: "Bounded external identifier cross-link adapter.",
    inputSchema: OpenCorporatesSchema.shape,
    toolsets: ["diligence"],
    handler: async (input: unknown): Promise<ToolResult> => {
      const params = OpenCorporatesSchema.parse(input);
      return toBriefToolResult(await buildOpenCorporatesLinksArtifact(params), params.format ?? "json");
    },
  },
  {
    name: "sg_adverse_media_lite",
    description: "Search bounded official Singapore public feeds for keyword evidence without open-web crawling or unsupported NLP claims.",
    surface: "canonical",
    positioning: "Official-feed adverse-media triage, not general media monitoring.",
    inputSchema: AdverseMediaLiteSchema.shape,
    toolsets: ["diligence"],
    handler: async (input: unknown): Promise<ToolResult> => {
      const params = AdverseMediaLiteSchema.parse(input);
      return toBriefToolResult(await buildAdverseMediaLiteArtifact(params), params.format ?? "json");
    },
  },
  {
    name: "sg_relationship_graph",
    description: "Build a shallow relationship graph from supplied public dossier records with strict limits against ownership or control claims.",
    surface: "canonical",
    positioning: "Evidence-backed and heuristic graph export over supplied public data only.",
    inputSchema: RelationshipGraphSchema.shape,
    toolsets: ["diligence"],
    handler: async (input: unknown): Promise<ToolResult> => {
      const params = RelationshipGraphSchema.parse(input);
      return toBriefToolResult(buildRelationshipGraphArtifact(params), params.format ?? "json");
    },
  },
];
