import type { AnalystMemoDossier } from "./analyst-memo.js";

export const MAX_BULK_DOSSIER_ITEMS = 25;
const UEN_PATTERN = /^(?:\d{8,9}[a-z]|[a-z]\d{2}[a-z]{2}\d{4}[a-z])$/i;

type ToolResult = {
  readonly isError?: boolean;
  readonly structuredContent?: Record<string, unknown>;
};

type DossierHandler = (input: { readonly uen: string } | { readonly entityName: string }) => Promise<ToolResult>;

export type BulkParseError = {
  readonly index: number;
  readonly input: string;
  readonly code: "EMPTY_IDENTIFIER" | "IDENTIFIER_TOO_LONG" | "INVALID_ITEM";
  readonly message: string;
};

export type BulkDossierRow =
  | {
      readonly index: number;
      readonly input: string;
      readonly status: "success" | "not_found";
      readonly canonicalIdentifier: string;
      readonly entity: string | null;
      readonly uen: string | null;
      readonly entityStatus: string | null;
      readonly confidence: string | null;
      readonly risk: "high" | "medium" | "low" | "none";
      readonly riskFlags: readonly string[];
      readonly matchedModules: readonly string[];
      readonly gapCodes: readonly string[];
      readonly upstreamFailure: boolean;
      readonly provenanceSources: readonly string[];
      readonly generatedAt: string;
      readonly dossier: AnalystMemoDossier;
    }
  | {
      readonly index: number;
      readonly input: string;
      readonly status: "error";
      readonly canonicalIdentifier: null;
      readonly entity: null;
      readonly uen: null;
      readonly entityStatus: null;
      readonly confidence: null;
      readonly risk: "none";
      readonly riskFlags: readonly [];
      readonly matchedModules: readonly [];
      readonly gapCodes: readonly string[];
      readonly upstreamFailure: boolean;
      readonly provenanceSources: readonly [];
      readonly generatedAt: string;
      readonly error: {
        readonly code: string;
        readonly message: string;
      };
    };

export type BulkDossierResponse = {
  readonly generatedAt: string;
  readonly maxItems: number;
  readonly requestedCount: number;
  readonly executedCount: number;
  readonly parseErrors: readonly BulkParseError[];
  readonly rows: readonly BulkDossierRow[];
  readonly limits: readonly string[];
};

type ParsedItem = {
  readonly index: number;
  readonly identifier: string;
};

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;

const asString = (value: unknown): string | null =>
  typeof value === "string" && value.trim() !== "" ? value.trim() : null;

const getSummaryString = (dossier: AnalystMemoDossier, label: string): string | null => {
  const value = dossier.summary.find((item) => item.label.toLowerCase() === label.toLowerCase())?.value;
  return asString(value);
};

const getStringArray = (value: unknown): readonly string[] =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];

const getConfidence = (dossier: AnalystMemoDossier): string | null => {
  const quality = asRecord(dossier.records["quality"]);
  const confidence = asRecord(quality?.["dossierConfidence"]);
  return asString(confidence?.["level"]);
};

const getRisk = (dossier: AnalystMemoDossier): BulkDossierRow["risk"] => {
  const flags = dossier.riskFlags ?? [];
  if (flags.some((flag) => flag.severity === "high")) return "high";
  if (flags.some((flag) => flag.severity === "medium")) return "medium";
  if (flags.some((flag) => flag.severity === "low")) return "low";
  return "none";
};

const isDossier = (value: unknown): value is AnalystMemoDossier =>
  asRecord(value) !== null
  && typeof asRecord(value)?.["title"] === "string"
  && Array.isArray(asRecord(value)?.["summary"])
  && Array.isArray(asRecord(value)?.["evidence"])
  && asRecord(asRecord(value)?.["records"]) !== null
  && Array.isArray(asRecord(value)?.["gaps"])
  && Array.isArray(asRecord(value)?.["provenance"])
  && Array.isArray(asRecord(value)?.["freshness"])
  && Array.isArray(asRecord(value)?.["limits"]);

const buildInput = (identifier: string): { readonly uen: string } | { readonly entityName: string } =>
  UEN_PATTERN.test(identifier)
    ? { uen: identifier.toUpperCase() }
    : { entityName: identifier };

export const parseBulkDossierItems = (input: unknown): {
  readonly items: readonly ParsedItem[];
  readonly errors: readonly BulkParseError[];
  readonly requestedCount: number;
} => {
  const record = asRecord(input);
  const rawItems = Array.isArray(record?.["items"]) ? record["items"] : [];
  const limitedItems = rawItems.slice(0, MAX_BULK_DOSSIER_ITEMS);
  const errors: BulkParseError[] = [];
  const items: ParsedItem[] = [];

  limitedItems.forEach((item, index) => {
    const identifier = typeof item === "string"
      ? item.trim()
      : asString(asRecord(item)?.["identifier"]);
    const inputText = typeof item === "string"
      ? item
      : JSON.stringify(item);
    if (identifier === null || identifier === "") {
      errors.push({
        code: "EMPTY_IDENTIFIER",
        index,
        input: inputText,
        message: "Identifier is required.",
      });
      return;
    }
    if (identifier.length > 128) {
      errors.push({
        code: "IDENTIFIER_TOO_LONG",
        index,
        input: identifier,
        message: "Identifier must be 128 characters or fewer.",
      });
      return;
    }
    items.push({ identifier, index });
  });

  if (rawItems.length > MAX_BULK_DOSSIER_ITEMS) {
    errors.push({
      code: "INVALID_ITEM",
      index: MAX_BULK_DOSSIER_ITEMS,
      input: String(rawItems.length),
      message: `Only the first ${MAX_BULK_DOSSIER_ITEMS} rows can be executed in one batch.`,
    });
  }

  return {
    errors,
    items,
    requestedCount: rawItems.length,
  };
};

export const buildBulkDossierResponse = async (
  input: unknown,
  handler: DossierHandler,
  generatedAt = new Date().toISOString(),
): Promise<BulkDossierResponse> => {
  const parsed = parseBulkDossierItems(input);
  const rows: BulkDossierRow[] = [];

  for (const item of parsed.items) {
    try {
      const result = await handler(buildInput(item.identifier));
      const record = result.structuredContent?.["record"];
      if (result.isError || !isDossier(record)) {
        throw new Error("Dossier handler did not return a structured dossier.");
      }
      const resolution = asRecord(record.records["resolution"]);
      const matchedModules = getStringArray(resolution?.["matchedModules"]);
      const gapCodes = record.gaps.map((gap) => gap.code);
      const uen = getSummaryString(record, "UEN");
      rows.push({
        canonicalIdentifier: uen ?? item.identifier,
        confidence: getConfidence(record),
        dossier: record,
        entity: getSummaryString(record, "Entity"),
        entityStatus: getSummaryString(record, "Entity status"),
        gapCodes,
        generatedAt,
        index: item.index,
        input: item.identifier,
        matchedModules,
        provenanceSources: record.provenance.map((source) => source.source),
        risk: getRisk(record),
        riskFlags: (record.riskFlags ?? []).map((flag) => flag.code),
        status: matchedModules.length === 0 ? "not_found" : "success",
        uen,
        upstreamFailure: gapCodes.some((code) => /UNAVAILABLE|FAILED|TIMEOUT|RATE_LIMIT/i.test(code)),
      });
    } catch (error) {
      rows.push({
        canonicalIdentifier: null,
        confidence: null,
        entity: null,
        entityStatus: null,
        error: {
          code: "DOSSIER_FAILED",
          message: error instanceof Error ? error.message : "Dossier lookup failed.",
        },
        gapCodes: ["DOSSIER_FAILED"],
        generatedAt,
        index: item.index,
        input: item.identifier,
        matchedModules: [],
        provenanceSources: [],
        risk: "none",
        riskFlags: [],
        status: "error",
        uen: null,
        upstreamFailure: true,
      });
    }
  }

  return {
    executedCount: parsed.items.length,
    generatedAt,
    limits: [
      `At most ${MAX_BULK_DOSSIER_ITEMS} rows are executed per batch.`,
      "Bulk rows preserve each dossier's public-data provenance, freshness, gaps, and limits.",
    ],
    maxItems: MAX_BULK_DOSSIER_ITEMS,
    parseErrors: parsed.errors,
    requestedCount: parsed.requestedCount,
    rows,
  };
};
