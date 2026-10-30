import type { Command } from "commander";
import type { CommandOptions, SingleResult } from "../../output/index.js";
interface SetPasswordResult {
    action: "password_set";
    configPath: string;
    restartCommand: string;
    message: string;
}
export type PromptPassword = (message: string) => Promise<string | symbol>;
export interface SetPasswordOptions {
    home?: string;
    promptPassword?: PromptPassword;
}
export declare function setDaemonPasswordInConfig(newPassword: string, options?: SetPasswordOptions): Promise<SetPasswordResult>;
export declare function runSetPasswordCommand(options: CommandOptions, _command: Command): Promise<SingleResult<SetPasswordResult>>;
export {};
//# sourceMappingURL=set-password.d.ts.map