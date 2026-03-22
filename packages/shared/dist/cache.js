import { mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { homedir } from "node:os";
import Database from "better-sqlite3";
export class Cache {
    db;
    hits = 0;
    misses = 0;
    constructor(dbPath) {
        const path = dbPath ?? join(homedir(), ".sg-apis", "cache.db");
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
    get(key) {
        const row = this.db
            .prepare("SELECT value, cached_at, ttl_seconds FROM cache WHERE key = ?")
            .get(key);
        if (row === undefined) {
            this.misses++;
            return null;
        }
        const now = Math.floor(Date.now() / 1000);
        if (now - row.cached_at > row.ttl_seconds) {
            this.misses++;
            this.db.prepare("DELETE FROM cache WHERE key = ?").run(key);
            return null;
        }
        this.hits++;
        return row.value;
    }
    set(key, value, ttl) {
        const now = Math.floor(Date.now() / 1000);
        this.db
            .prepare("INSERT OR REPLACE INTO cache (key, value, cached_at, ttl_seconds) VALUES (?, ?, ?, ?)")
            .run(key, value, now, ttl);
    }
    invalidate(pattern) {
        const result = this.db.prepare("DELETE FROM cache WHERE key LIKE ?").run(pattern);
        return result.changes;
    }
    stats() {
        const countRow = this.db.prepare("SELECT COUNT(*) as count FROM cache").get();
        const sizeRow = this.db
            .prepare("SELECT COALESCE(SUM(LENGTH(value)), 0) as size FROM cache")
            .get();
        return {
            entries: countRow.count,
            hits: this.hits,
            misses: this.misses,
            sizeBytes: sizeRow.size,
        };
    }
    clear() {
        this.db.exec("DELETE FROM cache");
        this.hits = 0;
        this.misses = 0;
    }
    close() {
        this.db.close();
    }
}
//# sourceMappingURL=cache.js.map