import { z } from "zod";
import type { AgentPromptInput, AgentTimelineItem } from "../agent-sdk-types.js";
declare const sourceSchema: z.ZodDiscriminatedUnion<[z.ZodObject<{
    kind: z.ZodLiteral<"agent-message">;
    agentId: z.ZodString;
    serverId: z.ZodOptional<z.ZodString>;
    title: z.ZodOptional<z.ZodString>;
}, z.core.$strip>, z.ZodObject<{
    kind: z.ZodLiteral<"agent-notification">;
    agentId: z.ZodString;
    serverId: z.ZodOptional<z.ZodString>;
    title: z.ZodOptional<z.ZodString>;
    event: z.ZodEnum<{
        finished: "finished";
        closed: "closed";
        errored: "errored";
        "permission-required": "permission-required";
    }>;
}, z.core.$strip>], "kind">;
export type AgentPromptSource = z.infer<typeof sourceSchema>;
interface AgentMessage {
    id: string;
    source: AgentPromptSource | null;
    text: string;
}
export declare function formatAgentMessage(message: AgentMessage): string;
export declare function parseAgentMessage(text: string): AgentMessage | null;
/** Accept only a complete sequence of envelopes; prose around them stays user text. */
export declare function parseAgentMessages(text: string): AgentMessage[] | null;
export declare function prepareAgentMessage(prompt: AgentPromptInput, source?: AgentPromptSource, id?: string): {
    prompt: AgentPromptInput;
    messageId?: string;
};
/** The same projection owns provider echoes, acceptance, import, and replay. */
export declare function projectAgentMessages(item: AgentTimelineItem): AgentTimelineItem[];
/**
 * Wrap a body in <paseo-system>…</paseo-system> so the receiving agent
 * recognizes the prompt as system-injected context — not a user turn.
 * Used by schedule fires; agent messages use the versioned envelope.
 */
export declare function formatSystemNotificationPrompt(reason: string): string;
export declare function isSystemInjectedEnvelope(text: string): boolean;
export {};
//# sourceMappingURL=envelope.d.ts.map