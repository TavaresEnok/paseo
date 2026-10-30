import type { HubCredentialStore } from "./credentials.js";
export interface HubAuthorityOptions {
    origin?: string;
    apiKey?: string;
}
interface ResolveHubInput {
    options: HubAuthorityOptions;
    env: Readonly<Record<string, string | undefined>>;
    credentials: HubCredentialStore;
}
export declare const DEFAULT_HUB_ORIGIN = "https://hub.paseo.sh";
export declare function resolveHubOrigin(input: ResolveHubInput): string;
export declare function resolveHubCredential(input: ResolveHubInput & {
    origin: string;
}): string;
export {};
//# sourceMappingURL=authority.d.ts.map