import { createHash } from "node:crypto";
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import Database from "better-sqlite3";
import { resolveStatePath } from "@sg-apis/shared";
import type { ToolResult, ToolResultResourceLinkContent } from "@sg-apis/shared";

const JSON_MIME_TYPE = "application/json";
export const ARTIFACT_RESOURCE_BASE_URI = "sg://artifacts";
const TEXT_PREVIEW_THRESHOLD_BYTES = 12 * 1024;
const ROW_PREVIEW_THRESHOLD = 50;
const DEFAULT_TTL_MS = 15 * 60 * 1000;
const REALTIME_TTL_MS = 5 * 60 * 1000;
const CLEANUP_INTERVAL_MS = 60 * 60 * 1000;

type ArtifactRow = {
  readonly uri: string;
  readonly id: string;
  readonly tool_name: string;
  readonly kind: string;
  readonly input_hash: string;
  readonly name: string;
  readonly title: string;
  readonly description: string | null;
  readonly mime_type: typeof JSON_MIME_TYPE;
  readonly payload_json: string;
  readonly preview_text: string;
  readonly created_at: number;
  readonly expires_at: number;
};

export type ArtifactEntry = {
  readonly id: string;
  readonly toolName: string;
  readonly kind: string;
  readonly inputHash: string;
  readonly uri: string;
  readonly name: string;
  readonly title: string;
  readonly description?: string;
  readonly mimeType: typeof JSON_MIME_TYPE;
  readonly payload: unknown;
  readonly previewText: string;
  readonly createdAt: string;
  readonly expiresAt: string;
};

type ArtifactPreview = Readonly<Record<string, unknown>>;

type MaterializedArtifact = {
  readonly entry: ArtifactEntry;
  readonly link: ToolResultResourceLinkContent;
};

const stableStringify = (value: unknown): string => {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(",")}]`;
  }

  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, entryValue]) => `${JSON.stringify(key)}:${stableStringify(entryValue)}`);
    return `{${entries.join(",")}}`;
  }

  return JSON.stringify(value);
};

const getDefaultArtifactDbPath = (): string => {
  return process.env["SG_APIS_ARTIFACT_DB_PATH"] ?? resolveStatePath("artifacts.db");
};

const toInputHash = (
  toolName: string,
  input: Readonly<Record<string, unknown>>,
  kind: string,
): string => {
  return createHash("sha256")
    .update(`${toolName}:${kind}:${stableStringify(input)}`)
    .digest("hex");
};

const toArtifactId = (inputHash: string): string => inputHash.slice(0, 24);

const toIsoTimestamp = (epochMs: number): string => new Date(epochMs).toISOString();

const toArtifactEntry = (row: ArtifactRow): ArtifactEntry => {
  return {
    id: row.id,
    toolName: row.tool_name,
    kind: row.kind,
    inputHash: row.input_hash,
    uri: row.uri,
    name: row.name,
    title: row.title,
    ...(row.description === null ? {} : { description: row.description }),
    mimeType: row.mime_type,
    payload: JSON.parse(row.payload_json) as unknown,
    previewText: row.preview_text,
    createdAt: toIsoTimestamp(row.created_at),
    expiresAt: toIsoTimestamp(row.expires_at),
  };
};

export class ArtifactStore {
  readonly #dbPath: string;
  readonly #db: Database.Database;
  #cleanupTimer: NodeJS.Timeout | undefined;

  constructor(dbPath = getDefaultArtifactDbPath()) {
    this.#dbPath = dbPath;
    if (dbPath !== ":memory:") {
      mkdirSync(dirname(dbPath), { recursive: true });
    }
    this.#db = new Database(dbPath);
    this.#db.pragma("journal_mode = WAL");
    this.#db.exec(`
      CREATE TABLE IF NOT EXISTS artifacts (
        uri TEXT PRIMARY KEY,
        id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        kind TEXT NOT NULL,
        input_hash TEXT NOT NULL,
        name TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        mime_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        preview_text TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL
      );
      CREATE INDEX IF NOT EXISTS artifacts_expires_at_idx ON artifacts (expires_at);
      CREATE INDEX IF NOT EXISTS artifacts_input_hash_idx ON artifacts (input_hash);
    `);
    this.cleanupExpired();
    this.#cleanupTimer = setInterval(() => {
      this.cleanupExpired();
    }, CLEANUP_INTERVAL_MS);
    this.#cleanupTimer.unref();
  }

  get dbPath(): string {
    return this.#dbPath;
  }

  upsert(options: {
    readonly toolName: string;
    readonly input: Readonly<Record<string, unknown>>;
    readonly kind: string;
    readonly title: string;
    readonly description?: string;
    readonly payload: unknown;
    readonly previewText: string;
    readonly realtime?: boolean;
  }): MaterializedArtifact {
    this.cleanupExpired();

    const inputHash = toInputHash(options.toolName, options.input, options.kind);
    const id = toArtifactId(inputHash);
    const uri = `${ARTIFACT_RESOURCE_BASE_URI}/${options.kind}/${id}`;
    const now = Date.now();
    const expiresAt = now + (options.realtime === true ? REALTIME_TTL_MS : DEFAULT_TTL_MS);

    this.#db.prepare(`
      INSERT OR REPLACE INTO artifacts (
        uri,
        id,
        tool_name,
        kind,
        input_hash,
        name,
        title,
        description,
        mime_type,
        payload_json,
        preview_text,
        created_at,
        expires_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      uri,
      id,
      options.toolName,
      options.kind,
      inputHash,
      `sg-artifact-${options.kind}-${id}`,
      options.title,
      options.description ?? null,
      JSON_MIME_TYPE,
      JSON.stringify(options.payload),
      options.previewText,
      now,
      expiresAt,
    );

    const entry = this.read(uri);
    if (entry === null) {
      throw new Error(`Failed to persist artifact ${uri}.`);
    }

    return {
      entry,
      link: {
        type: "resource_link",
        uri: entry.uri,
        name: entry.name,
        title: entry.title,
        ...(entry.description === undefined ? {} : { description: entry.description }),
        mimeType: entry.mimeType,
        annotations: {
          audience: ["assistant", "user"],
          priority: 0.8,
          lastModified: entry.createdAt,
        },
      },
    };
  }

  read(uri: string): ArtifactEntry | null {
    this.cleanupExpired();
    const row = this.#db
      .prepare(`
        SELECT
          uri,
          id,
          tool_name,
          kind,
          input_hash,
          name,
          title,
          description,
          mime_type,
          payload_json,
          preview_text,
          created_at,
          expires_at
        FROM artifacts
        WHERE uri = ?
      `)
      .get(uri) as ArtifactRow | undefined;

    return row === undefined ? null : toArtifactEntry(row);
  }

  cleanupExpired(now = Date.now()): number {
    const result = this.#db
      .prepare("DELETE FROM artifacts WHERE expires_at <= ?")
      .run(now);
    return result.changes;
  }

  clear(): void {
    this.#db.exec("DELETE FROM artifacts");
  }

  close(): void {
    if (this.#cleanupTimer !== undefined) {
      clearInterval(this.#cleanupTimer);
      this.#cleanupTimer = undefined;
    }
    this.#db.close();
  }
}

let artifactStoreSingleton: ArtifactStore | null = null;

const getArtifactStore = (): ArtifactStore => {
  if (artifactStoreSingleton === null) {
    artifactStoreSingleton = new ArtifactStore();
  }
  return artifactStoreSingleton;
};

export const artifactStore = {
  upsert: (options: Parameters<ArtifactStore["upsert"]>[0]) => getArtifactStore().upsert(options),
  read: (uri: string) => getArtifactStore().read(uri),
  clear: () => getArtifactStore().clear(),
  cleanupExpired: (now?: number) => getArtifactStore().cleanupExpired(now),
  close: () => { if (artifactStoreSingleton !== null) { artifactStoreSingleton.close(); artifactStoreSingleton = null; } },
  getDbPath: () => getArtifactStore().dbPath,
};

export const resetArtifactStoreForTests = (dbPath = ":memory:"): void => {
  if (artifactStoreSingleton !== null) { artifactStoreSingleton.close(); }
  artifactStoreSingleton = new ArtifactStore(dbPath);
};

export const shouldUseArtifact = (
  text: string,
  rowCount?: number,
): boolean => {
  return Buffer.byteLength(text, "utf8") > TEXT_PREVIEW_THRESHOLD_BYTES
    || (rowCount !== undefined && rowCount > ROW_PREVIEW_THRESHOLD);
};

export const buildArtifactResult = (options: {
  readonly toolName: string;
  readonly input: Readonly<Record<string, unknown>>;
  readonly kind: string;
  readonly title: string;
  readonly description?: string;
  readonly fullText: string;
  readonly payload: unknown;
  readonly preview: ArtifactPreview;
  readonly structuredContentBase?: Readonly<Record<string, unknown>>;
  readonly isError?: boolean;
  readonly realtime?: boolean;
  readonly _meta?: Readonly<Record<string, unknown>>;
}): ToolResult => {
  const previewText = options.fullText.length <= 900
    ? options.fullText
    : `${options.fullText.slice(0, 900).trimEnd()}\n\n[Truncated preview. Read the linked artifact for the full JSON payload.]`;

  const artifact = artifactStore.upsert({
    toolName: options.toolName,
    input: options.input,
    kind: options.kind,
    title: options.title,
    ...(options.description === undefined ? {} : { description: options.description }),
    payload: options.payload,
    previewText,
    ...(options.realtime === true ? { realtime: true } : {}),
  });

  return {
    content: [
      { type: "text", text: previewText },
      artifact.link,
    ],
    ...(options.isError === undefined ? {} : { isError: options.isError }),
    structuredContent: {
      ...(options.structuredContentBase ?? {}),
      preview: options.preview,
      artifact: {
        uri: artifact.entry.uri,
        kind: artifact.entry.kind,
        mimeType: artifact.entry.mimeType,
        createdAt: artifact.entry.createdAt,
        expiresAt: artifact.entry.expiresAt,
      },
    },
    ...(options._meta === undefined ? {} : { _meta: options._meta }),
  };
};

export const serializeArtifactEntry = (entry: ArtifactEntry): Readonly<Record<string, unknown>> => {
  return {
    id: entry.id,
    toolName: entry.toolName,
    kind: entry.kind,
    inputHash: entry.inputHash,
    uri: entry.uri,
    name: entry.name,
    title: entry.title,
    ...(entry.description === undefined ? {} : { description: entry.description }),
    mimeType: entry.mimeType,
    previewText: entry.previewText,
    createdAt: entry.createdAt,
    expiresAt: entry.expiresAt,
    payload: entry.payload,
  };
};
