import type { WaitForFinishResult } from "@getpaseo/client/internal/daemon-client";
export type FinishObservationResult = WaitForFinishResult & {
    reason?: "was canceled" | "host unreachable" | "host removed";
};
/** Coalesces duplicate checkpoints and retains one terminal result while delivery is pending. */
export declare function createObservationBuffer(signal: AbortSignal): {
    pushInitial(result: FinishObservationResult): void;
    push: (result: FinishObservationResult) => void;
    resolved(id: string): void;
    fail(error: unknown): void;
    next(): Promise<FinishObservationResult>;
    dispose(): void;
};
//# sourceMappingURL=observation-buffer.d.ts.map