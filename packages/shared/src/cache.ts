import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import Database from "better-sqlite3";
import { resolveStatePath } from "./state-dir.js";

export type CacheEntry = {
  readonly ageSeconds: number;
  readonly cachedAt: number;
  readonly expired: boolean;
  readonly ttlSeconds: number;
  readonly value: string;
};

export class Cache {
  private readonly db: Database.Database;
  private hits = 0;
  private misses = 0;

  constructor(dbPath?: string) {
    const path = dbPath ?? resolveStatePath("cache.db");
    if (path !== ":memory:") {
      mkdirSync(dirname(path), { recursive: true });
    }
    this.db = new Database(path);
    this.db.pragma("journal_mode = WAL");
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS cache (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        cached_at INTEGER NOT NULL,
        ttl_seconds INTEGER NOT NULL
      )
    `);
  }

  getEntry(key: string): CacheEntry | null {
    const row = this.db
      .prepare("SELECT value, cached_at, ttl_seconds FROM cache WHERE key = ?")
      .get(key) as { value: string; cached_at: number; ttl_seconds: number } | undefined;

    if (row === undefined) {
      this.misses++;
      return null;
    }

    const now = Math.floor(Date.now() / 1000);
    const ageSeconds = now - row.cached_at;
    const expired = ageSeconds >= row.ttl_seconds;
    if (expired) {
      this.misses++;
    } else {
      this.hits++;
    }

    return {
      ageSeconds,
      cachedAt: row.cached_at,
      expired,
      ttlSeconds: row.ttl_seconds,
      value: row.value,
    };
  }

  get(key: string): string | null {
    const entry = this.getEntry(key);
    if (entry === null) {
      return null;
    }
    if (entry.expired) {
      this.db.prepare("DELETE FROM cache WHERE key = ?").run(key);
      return null;
    }

    return entry.value;
  }

  delete(key: string): void {
    this.db.prepare("DELETE FROM cache WHERE key = ?").run(key);
  }

  compactExpired(): number {
    const now = Math.floor(Date.now() / 1000);
    const result = this.db.prepare("DELETE FROM cache WHERE ? - cached_at >= ttl_seconds").run(now);
    return result.changes;
  }

  getFreshOrStale(key: string): CacheEntry | null {
    return this.getEntry(key);
  }

  getFresh(key: string): string | null {
    const entry = this.getEntry(key);
    if (entry === null || entry.expired) {
      return null;
    }
    return entry.value;
  }

  getStale(key: string): string | null {
    const entry = this.getEntry(key);
    if (entry === null || !entry.expired) {
      return null;
    }
    return entry.value;
  }

  set(key: string, value: string, ttl: number): void {
    const now = Math.floor(Date.now() / 1000);
    this.db
      .prepare(
        "INSERT OR REPLACE INTO cache (key, value, cached_at, ttl_seconds) VALUES (?, ?, ?, ?)",
      )
      .run(key, value, now, ttl);
  }

  invalidate(pattern: string): number {
    const result = this.db.prepare("DELETE FROM cache WHERE key LIKE ?").run(pattern);
    return result.changes;
  }

  stats(): { entries: number; hits: number; misses: number; sizeBytes: number } {
    const countRow = this.db.prepare("SELECT COUNT(*) as count FROM cache").get() as {
      count: number;
    };
    const sizeRow = this.db
      .prepare("SELECT COALESCE(SUM(LENGTH(value)), 0) as size FROM cache")
      .get() as { size: number };

    return {
      entries: countRow.count,
      hits: this.hits,
      misses: this.misses,
      sizeBytes: sizeRow.size,
    };
  }

  clear(): void {
    this.db.exec("DELETE FROM cache");
    this.hits = 0;
    this.misses = 0;
  }

  close(): void {
    this.db.close();
  }
}
