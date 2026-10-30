import type { Command } from "commander";
import type { CommandOptions, ListResult } from "../../output/index.js";
import { type PermissionResponseItem, type PermitClientConnector } from "./allow.js";
export type PermitDenyResult = ListResult<PermissionResponseItem>;
export interface PermitDenyOptions extends CommandOptions {
    all?: boolean;
    message?: string;
    interrupt?: boolean;
    host?: string;
}
export declare function createDenyCommand(connect?: PermitClientConnector): (agentIdOrPrefix: string, reqId: string | undefined, options: PermitDenyOptions, _command: Command) => Promise<PermitDenyResult>;
export declare const runDenyCommand: (agentIdOrPrefix: string, reqId: string | undefined, options: PermitDenyOptions, _command: Command) => Promise<PermitDenyResult>;
//# sourceMappingURL=deny.d.ts.map