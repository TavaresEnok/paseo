import type { HubHttpClient } from "./hub-client/index.js";
export interface LoginWaiter {
    wait(milliseconds: number): Promise<void>;
    now(): number;
}
export interface BrowserOpener {
    open(url: string): Promise<void>;
}
type BrowserLaunch = (command: string, args: string[]) => Promise<void>;
interface SystemBrowserOptions {
    hostPlatform?: NodeJS.Platform;
    launch?: BrowserLaunch;
}
export declare class SystemBrowser implements BrowserOpener {
    private readonly hostPlatform;
    private readonly launch;
    constructor(options?: SystemBrowserOptions);
    open(url: string): Promise<void>;
}
interface CliLoginFlowOptions {
    hub: Pick<HubHttpClient, "startCliAuthorization" | "pollCliAuthorization">;
    waiter: LoginWaiter;
    browser: BrowserOpener;
    instructions(verificationUri: string, userCode: string): void;
    openBrowser: boolean;
}
export declare class CliLoginFlow {
    private readonly options;
    constructor(options: CliLoginFlowOptions);
    authorize(origin: string): Promise<string>;
}
export declare function createCliLoginFlow(hub: HubHttpClient): CliLoginFlow;
export {};
//# sourceMappingURL=login-flow.d.ts.map