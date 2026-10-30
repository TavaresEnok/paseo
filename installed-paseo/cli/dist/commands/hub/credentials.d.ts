export interface StoredHubCredential {
    origin: string;
    credential: string;
}
export interface HubCredentialStore {
    active(): StoredHubCredential | null;
    get(origin: string): StoredHubCredential | null;
    save(credential: StoredHubCredential): void;
    logoutActive(): StoredHubCredential | null;
}
export declare class PrivateHubCredentialStore implements HubCredentialStore {
    private readonly filePath;
    constructor(env?: Readonly<Record<string, string | undefined>>);
    active(): StoredHubCredential | null;
    get(origin: string): StoredHubCredential | null;
    save(credential: StoredHubCredential): void;
    logoutActive(): StoredHubCredential | null;
    private read;
    private write;
}
//# sourceMappingURL=credentials.d.ts.map