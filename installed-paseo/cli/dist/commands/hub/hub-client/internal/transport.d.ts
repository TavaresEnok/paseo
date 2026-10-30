import type { z } from "zod";
interface HubRequest<T> {
    origin: string;
    path: string;
    method: "GET" | "POST";
    apiKey?: string;
    body?: unknown;
    successStatus: number;
    schema: z.ZodType<T>;
    timeoutMilliseconds?: number;
    failureMessage: string;
}
export declare function requestHub<T>(input: HubRequest<T>): Promise<T>;
export {};
//# sourceMappingURL=transport.d.ts.map