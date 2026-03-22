import type { OutputFormat, GeoFeature } from "../types/index.js";
export declare const formatJson: (data: unknown, pretty?: boolean) => string;
export declare const formatMarkdown: (data: readonly Record<string, unknown>[] | Readonly<Record<string, unknown>>) => string;
export declare const formatCsv: (rows: readonly Record<string, unknown>[], columns?: readonly string[]) => string;
export declare const formatGeoJson: (features: readonly GeoFeature[]) => string;
export declare const formatStream: (rows: AsyncIterable<Readonly<Record<string, unknown>>>, format: OutputFormat) => AsyncIterable<string>;
export declare const formatResponse: (data: unknown, format: OutputFormat) => string;
//# sourceMappingURL=index.d.ts.map