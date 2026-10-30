import { Command } from "commander";
import type { DaemonTarget } from "../../utils/daemon-target.js";
interface PairOptions {
    daemonTarget: DaemonTarget;
    home?: string;
    json?: boolean;
    relay?: boolean;
}
export interface PairCommandOutput {
    columns: number | undefined;
    writeStdout(message: string): void;
    writeStderr(message: string): void;
    setExitCode(code: number): void;
    success(message: string): void;
}
export interface PairingOffer {
    relayEnabled: boolean;
    url: string | null;
    qr: string | null;
}
export declare function pairCommand(): Command;
export declare function resolveLocalPairingOffer(options: {
    paseoHome: string;
    enableRelay?: boolean;
}): Promise<PairingOffer>;
export declare function confirmRelayPairing(): Promise<boolean>;
export declare function printDirectConnectionGuidance(): void;
export declare function runPairCommand(options: PairOptions): Promise<void>;
export {};
//# sourceMappingURL=pair.d.ts.map