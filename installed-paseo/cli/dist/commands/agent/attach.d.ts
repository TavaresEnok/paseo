import type { Command } from "commander";
export declare function addAttachOptions(cmd: Command): Command;
export interface AgentAttachOptions {
    host?: string;
    daemonTarget: import("../../utils/daemon-target.js").DaemonTarget;
    [key: string]: unknown;
}
/**
 * Attach to a running agent's output stream
 */
export declare function runAttachCommand(id: string, options: AgentAttachOptions, _command: Command): Promise<void>;
//# sourceMappingURL=attach.d.ts.map