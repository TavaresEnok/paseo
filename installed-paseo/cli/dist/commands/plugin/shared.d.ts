import type { DaemonTarget } from "../../utils/daemon-target.js";
import type { DaemonClient } from "@getpaseo/client/internal/daemon-client";
export declare function withPluginManagementClient<T>(target: DaemonTarget, run: (client: DaemonClient) => Promise<T>): Promise<T>;
export declare function withPluginLogsClient<T>(target: DaemonTarget, run: (client: DaemonClient) => Promise<T>): Promise<T>;
export declare function withPluginSourceClient<T>(target: DaemonTarget, run: (client: DaemonClient) => Promise<T>): Promise<T>;
export declare function withPluginUpdateClient<T>(target: DaemonTarget, run: (client: DaemonClient) => Promise<T>): Promise<T>;
//# sourceMappingURL=shared.d.ts.map