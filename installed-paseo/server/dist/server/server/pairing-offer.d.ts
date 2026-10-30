import type { Logger } from "pino";
export interface LocalPairingOffer {
    relayEnabled: boolean;
    url: string | null;
    qr: string | null;
}
export declare function generateLocalPairingOffer(args: {
    paseoHome: string;
    relayEnabled?: boolean;
    relayEndpoint?: string;
    relayPublicEndpoint?: string;
    relayUseTls?: boolean;
    relayPublicUseTls?: boolean;
    /** Stamp the offer so new clients require protected endpoint security from their first handshake. */
    relayRequireProtectedSecurity?: boolean;
    appBaseUrl?: string;
    includeQr?: boolean;
    logger?: Logger;
}): Promise<LocalPairingOffer>;
//# sourceMappingURL=pairing-offer.d.ts.map