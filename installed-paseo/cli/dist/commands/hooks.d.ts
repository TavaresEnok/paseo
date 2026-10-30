import { Command } from "commander";
interface HookEnvironment {
    PASEO_TERMINAL_ID?: string;
    PASEO_ACTIVITY_TOKEN?: string;
    PASEO_TERMINAL_ACTIVITY_URL?: string;
}
interface HookInput {
    [Symbol.asyncIterator](): AsyncIterator<string | Buffer>;
    isTTY?: boolean;
}
interface HooksRuntime {
    env: HookEnvironment;
    input: HookInput;
    fetch: typeof fetch;
}
export declare function createHooksCommand(): Command;
export declare function runHooksCommand(agent: string, event: string, runtime?: HooksRuntime): Promise<void>;
export {};
//# sourceMappingURL=hooks.d.ts.map