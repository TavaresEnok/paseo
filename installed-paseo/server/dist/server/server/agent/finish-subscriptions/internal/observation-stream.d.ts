import type { HostObservation } from "../../host-operations/index.js";
import type { FinishSubscription, FinishObservationSession } from "../index.js";
interface ObservationScope {
    use<T>(serverId: string | undefined, action: (host: HostObservation) => Promise<T>, signal?: AbortSignal): Promise<T>;
}
/** One continuous source feeds a bounded buffer while the caller awaits dispatch. */
export declare function openFinishObservation(resolver: ObservationScope, record: FinishSubscription, signal: AbortSignal): Promise<FinishObservationSession>;
export {};
//# sourceMappingURL=observation-stream.d.ts.map