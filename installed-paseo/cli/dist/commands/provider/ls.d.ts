import type { Command } from "commander";
import type { CommandOptions, ListResult, OutputSchema } from "../../output/index.js";
import type { ProviderSnapshotEntry } from "@getpaseo/protocol/agent-types";
export interface ProviderListItem {
    provider: ProviderSnapshotEntry["provider"];
    label: string;
    status: string;
    enabled: "Enabled" | "Disabled";
    defaultMode: string;
    modes: string;
}
/** Schema for provider ls output */
export declare const providerLsSchema: OutputSchema<ProviderListItem>;
export type ProviderLsResult = ListResult<ProviderListItem>;
export interface ProviderLsOptions extends CommandOptions {
    host?: string;
}
export declare function runLsCommand(options: ProviderLsOptions, _command: Command): Promise<ProviderLsResult>;
//# sourceMappingURL=ls.d.ts.map