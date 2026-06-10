import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import Database from "better-sqlite3";
import type { KeyInfo } from "./types/index.js";
import { resolveStatePath } from "./state-dir.js";

export class Keystore {
  private readonly db: Database.Database;

  constructor(dbPath?: string) {
    const path = dbPath ?? resolveStatePath("keys.db");
    if (path !== ":memory:") {
      mkdirSync(dirname(path), { recursive: true });
    }
    this.db = new Database(path);
    this.db.pragma("journal_mode = WAL");
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS keys (
        api_name TEXT PRIMARY KEY,
        api_key TEXT NOT NULL,
        added_at INTEGER NOT NULL,
        last_used INTEGER
      )
    `);
  }

  setKey(apiName: string, key: string): void {
    const now = Math.floor(Date.now() / 1000);
    this.db
      .prepare(
        "INSERT OR REPLACE INTO keys (api_name, api_key, added_at, last_used) VALUES (?, ?, ?, NULL)",
      )
      .run(apiName, key, now);
  }

  getKey(apiName: string): string | null {
    const envKey = process.env[`SG_API_${apiName.toUpperCase()}_KEY`];
    if (envKey !== undefined && envKey !== "") {
      return envKey;
    }

    const envEmail = process.env[`SG_API_${apiName.toUpperCase()}_EMAIL`];
    if (envEmail !== undefined && envEmail !== "") {
      return envEmail;
    }

    const row = this.db
      .prepare("SELECT api_key FROM keys WHERE api_name = ?")
      .get(apiName) as { api_key: string } | undefined;

    if (row === undefined) {
      return null;
    }

    const now = Math.floor(Date.now() / 1000);
    this.db.prepare("UPDATE keys SET last_used = ? WHERE api_name = ?").run(now, apiName);
    return row.api_key;
  }

  listKeys(): KeyInfo[] {
    const rows = this.db
      .prepare("SELECT api_name, api_key, added_at, last_used FROM keys")
      .all() as { api_name: string; api_key: string; added_at: number; last_used: number | null }[];

    return rows.map((row) => ({
      apiName: row.api_name,
      maskedKey: row.api_key.length > 4 ? row.api_key.slice(0, 4) + "****" : "****",
      addedAt: row.added_at,
      lastUsed: row.last_used,
    }));
  }

  deleteKey(apiName: string): boolean {
    const result = this.db.prepare("DELETE FROM keys WHERE api_name = ?").run(apiName);
    return result.changes > 0;
  }

  close(): void {
    this.db.close();
  }
}
