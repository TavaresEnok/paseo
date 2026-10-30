import type { PromptDispatchDisposition } from "../agent-prompt.js";
import type { AgentPromptInput } from "../agent-sdk-types.js";
import { type AgentPromptSource } from "./envelope.js";
interface Message {
    recipientId: string;
    messageId?: string;
    source: AgentPromptSource;
    prompt: AgentPromptInput;
    sessionMode?: string;
    unarchive?: boolean;
    clearPendingPermissions?: boolean;
    activeTurnBehavior?: "steer" | "interrupt";
    beforeDispatch?: () => void;
    onDispatch?: (disposition: PromptDispatchDisposition) => void;
}
interface Receipt {
    status: "queued";
    messageId: string;
    dispatched: Promise<PromptDispatchDisposition>;
}
interface DispatchRequest {
    recipientId: string;
    messageIds: readonly string[];
    prompt: AgentPromptInput;
    activeTurnBehavior: "steer" | "interrupt";
    sessionMode?: string;
    clearPendingPermissions: boolean;
    unarchive: boolean;
    onDispatch(disposition: PromptDispatchDisposition): void;
}
interface Dependencies {
    dispatch(request: DispatchRequest): Promise<PromptDispatchDisposition>;
    onError(error: unknown, request: DispatchRequest): void;
    /** Return a cancellation function. Production uses the daemon's event loop. */
    schedule?: (delayMs: number, callback: () => void) => () => void;
}
export interface AgentMessageDelivery {
    enqueue(message: Message): Receipt;
    /** Stop admission, flush pending messages, and await provider dispatch acknowledgments. */
    close(): Promise<void>;
    /** Existing completion waits include agent messages admitted before the wait. */
    waitForDispatch(recipientId: string, signal: AbortSignal): Promise<void>;
}
/** Recipient-owned agent delivery. Human prompts never enter this module. */
export declare function createAgentMessageDelivery(dependencies: Dependencies): AgentMessageDelivery;
export {};
//# sourceMappingURL=delivery.d.ts.map