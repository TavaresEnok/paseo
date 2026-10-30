export interface HubDeployTrigger {
    path: string;
    yaml: string;
}
export declare function discoverHubTriggers(cwd: string): Promise<HubDeployTrigger[]>;
//# sourceMappingURL=deploy-triggers.d.ts.map