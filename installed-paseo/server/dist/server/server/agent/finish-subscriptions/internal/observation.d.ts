import type { Logger } from "pino";
import type { AgentManager } from "../../agent-manager.js";
import type { AgentStorage } from "../../agent-storage.js";
import type { AgentMessageDelivery } from "../../agent-messages/index.js";
import { type ToolHosts } from "../../host-operations/index.js";
import type { FinishObservation } from "../index.js";
export declare function createFinishObservation(input: {
    agentManager: AgentManager;
    agentStorage: AgentStorage;
    messages(): AgentMessageDelivery;
    hosts(): ToolHosts;
    serverId: string;
    logger: Logger;
}): FinishObservation;
//# sourceMappingURL=observation.d.ts.map