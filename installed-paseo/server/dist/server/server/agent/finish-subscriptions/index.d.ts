import type { Logger } from "pino";
import type { FinishObservationResult } from "./internal/observation-buffer.js";
import type { AgentMessageDelivery } from "../agent-messages/index.js";
export { createJsonFinishSubscriptionStore } from "./internal/json-store.js";
export interface FinishSubscription {
    id: string;
    callerAgentId: string;
    childAgentId: string;
    serverId?: string;
    /** Creation subscriptions stop reporting after the child is detached. */
    requireParentOwnership?: boolean;
}
export interface FinishSubscriptionStore {
    list(): Promise<FinishSubscription[]>;
    put(subscription: FinishSubscription): Promise<void>;
    remove(id: string): Promise<void>;
}
export interface FinishObservationSession {
    next(): Promise<FinishObservationResult>;
    close(): Promise<void>;
}
export interface FinishObservation {
    open(subscription: FinishSubscription, signal: AbortSignal): Promise<FinishObservationSession>;
}
interface Dependencies extends FinishObservation {
    store: FinishSubscriptionStore;
    messages(): AgentMessageDelivery;
    callerIsActive(agentId: string): Promise<boolean>;
    serverId: string;
    logger: Logger;
    retryDelayMs?: number;
}
export interface FinishRegistration {
    /** The prompt was accepted. Replaces preceding registrations for this pair. */
    accept(): void;
    /** Rejected dispatch preserves preceding registrations. */
    reject(): Promise<void>;
}
export interface FinishSubscriptions {
    start(): Promise<void>;
    register(input: Omit<FinishSubscription, "id">, pendingDispatch?: boolean): Promise<FinishRegistration>;
    close(): Promise<void>;
}
/** Owns durable intent, live observation, supersession, and dispatch acknowledgment. */
export declare function createFinishSubscriptions(deps: Dependencies): FinishSubscriptions;
export { createFinishObservation } from "./internal/observation.js";
//# sourceMappingURL=index.d.ts.map