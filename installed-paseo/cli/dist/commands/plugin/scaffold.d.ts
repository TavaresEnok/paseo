export interface PluginScaffold {
    id: string;
    directory: string;
}
export declare function scaffoldPluginDirectory(targetDirectory: string, requestedId?: string): Promise<PluginScaffold>;
//# sourceMappingURL=scaffold.d.ts.map