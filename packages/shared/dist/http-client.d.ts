export type HttpOptions = {
    readonly headers?: Readonly<Record<string, string>>;
    readonly timeout?: number;
    readonly retries?: number;
    readonly apiName: string;
};
export declare const httpGet: <T>(url: string, options: HttpOptions) => Promise<T>;
//# sourceMappingURL=http-client.d.ts.map