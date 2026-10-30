import type { ListResult } from "../../output/index.js";
import type { HubStatus } from "./daemon-client.js";
export interface HubRow {
    state: string;
    daemonId: string | null;
    hub: string | null;
    permissions: string;
    connectedAt: string | null;
    error: string | null;
    warning?: string;
}
export declare function hubStatusResult(status: HubStatus, warning?: string, reportedHubOrigin?: string | null): ListResult<HubRow>;
//# sourceMappingURL=status-output.d.ts.map