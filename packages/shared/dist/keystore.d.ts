import type { KeyInfo } from "./types/index.js";
export declare class Keystore {
    private readonly db;
    constructor(dbPath?: string);
    setKey(apiName: string, key: string): void;
    getKey(apiName: string): string | null;
    listKeys(): KeyInfo[];
    deleteKey(apiName: string): boolean;
    close(): void;
}
//# sourceMappingURL=keystore.d.ts.map