interface PairingInstructions {
    url: string;
    qr: string | null;
    connectionUri?: string | null;
    columns?: number;
}
export declare function formatPairingInstructions({ url, qr, columns, connectionUri, }: PairingInstructions): string;
export {};
//# sourceMappingURL=pairing.d.ts.map