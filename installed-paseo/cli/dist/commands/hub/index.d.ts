import { Command } from "commander";
import { HubHttpClient } from "./hub-client/index.js";
import { type HubCredentialStore } from "./credentials.js";
import { type HubDaemonConnection } from "./daemon-client.js";
import { type CliLoginFlow } from "./login-flow.js";
import { type HubReporter } from "./reporter.js";
interface HubCommandEnvironment {
    env: Readonly<Record<string, string | undefined>>;
    credentials: HubCredentialStore;
    hub: HubHttpClient;
    login: Pick<CliLoginFlow, "authorize">;
    daemon: HubDaemonConnection;
    isInteractive(): boolean;
    confirmDisconnect(origin: string): Promise<boolean>;
    reporter: HubReporter;
    cwd(): string;
}
export declare function createHubCommand(overrides?: Partial<HubCommandEnvironment>): Command;
export {};
//# sourceMappingURL=index.d.ts.map