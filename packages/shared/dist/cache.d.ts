export declare class Cache {
    private readonly db;
    private hits;
    private misses;
    constructor(dbPath?: string);
    get(key: string): string | null;
    set(key: string, value: string, ttl: number): void;
    invalidate(pattern: string): number;
    stats(): {
        entries: number;
        hits: number;
        misses: number;
        sizeBytes: number;
    };
    clear(): void;
    close(): void;
}
//# sourceMappingURL=cache.d.ts.map