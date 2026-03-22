export type Logger = {
    readonly debug: (msg: string, extra?: Readonly<Record<string, unknown>>) => void;
    readonly info: (msg: string, extra?: Readonly<Record<string, unknown>>) => void;
    readonly warn: (msg: string, extra?: Readonly<Record<string, unknown>>) => void;
    readonly error: (msg: string, extra?: Readonly<Record<string, unknown>>) => void;
};
export declare const createLogger: (module: string) => Logger;
//# sourceMappingURL=logger.d.ts.map