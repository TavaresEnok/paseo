export interface HubBundleFile {
    path: string;
    content: string;
}
export interface HubDeployBundle {
    projectSlug: string;
    files: readonly HubBundleFile[];
    workflowCount: number;
}
interface DiscoverHubBundleInput {
    cwd: string;
    project?: string;
}
export declare function discoverHubBundle(input: DiscoverHubBundleInput): Promise<HubDeployBundle>;
export {};
//# sourceMappingURL=deploy-bundle.d.ts.map