import type { CommandOptions } from "../../output/index.js";
import type { DaemonTarget } from "../../utils/daemon-target.js";
import type { Command } from "commander";
import { type SingleResult } from "../../output/index.js";
import type { HubCredentialStore } from "./credentials.js";
import type { CliLoginFlow } from "./login-flow.js";
import { type HubReporter } from "./reporter.js";
interface HubLoginResult {
    origin: string;
    status: "logged_in";
}
interface HubLoginDependencies {
    env: Readonly<Record<string, string | undefined>>;
    credentials: HubCredentialStore;
    flow: Pick<CliLoginFlow, "authorize">;
    reporter: HubReporter;
    isInteractive?(): boolean;
    continueGuidedSetup?(origin: string, daemonTarget: DaemonTarget): Promise<void>;
}
export declare function runHubLogin(originInput: string | undefined, options: Pick<CommandOptions, "json" | "daemonTarget">, dependencies: HubLoginDependencies): Promise<SingleResult<HubLoginResult>>;
export declare function addHubLoginCommand(parent: Command, dependencies: HubLoginDependencies): void;
export {};
//# sourceMappingURL=login.d.ts.map