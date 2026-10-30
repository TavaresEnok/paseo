import type { AgentPermissionRequest } from "../../agent-sdk-types.js";
export type FinishNotificationReason = "host unreachable" | "host removed" | "finished" | "errored" | "needs permission" | "is unavailable" | "was closed" | "was canceled";
export declare const finishNotificationEvents: {
    readonly "host unreachable": "errored";
    readonly "host removed": "errored";
    readonly finished: "finished";
    readonly errored: "errored";
    readonly "needs permission": "permission-required";
    readonly "was closed": "closed";
    readonly "is unavailable": "closed";
    readonly "was canceled": "errored";
};
interface FinishNotificationBodyInput {
    childAgentId: string;
    serverId?: string;
    title: string;
    reason: FinishNotificationReason;
    lastAssistantMessage: string | null;
    permissionRequest?: AgentPermissionRequest;
}
export declare function formatFinishNotificationBody(params: FinishNotificationBodyInput): string;
export {};
//# sourceMappingURL=notification.d.ts.map