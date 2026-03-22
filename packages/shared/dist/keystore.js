import { mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { homedir } from "node:os";
import Database from "better-sqlite3";
export class Keystore {
    db;
    constructor(dbPath) {
        const path = dbPath ?? join(homedir(), ".sg-apis", "keys.db");
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
    setKey(apiName, key) {
        const now = Math.floor(Date.now() / 1000);
        this.db
            .prepare("INSERT OR REPLACE INTO keys (api_name, api_key, added_at, last_used) VALUES (?, ?, ?, NULL)")
            .run(apiName, key, now);
    }
    getKey(apiName) {
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
            .get(apiName);
        if (row === undefined) {
            return null;
        }
        const now = Math.floor(Date.now() / 1000);
        this.db.prepare("UPDATE keys SET last_used = ? WHERE api_name = ?").run(now, apiName);
        return row.api_key;
    }
    listKeys() {
        const rows = this.db
            .prepare("SELECT api_name, api_key, added_at, last_used FROM keys")
            .all();
        return rows.map((row) => ({
            apiName: row.api_name,
            maskedKey: row.api_key.length > 4 ? row.api_key.slice(0, 4) + "****" : "****",
            addedAt: row.added_at,
            lastUsed: row.last_used,
        }));
    }
    deleteKey(apiName) {
        const result = this.db.prepare("DELETE FROM keys WHERE api_name = ?").run(apiName);
        return result.changes > 0;
    }
    close() {
        this.db.close();
    }
}
//# sourceMappingURL=keystore.js.map