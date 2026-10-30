export interface RunCliOptions {
    cwd?: string;
    nodeArgv?: [string, string];
}
export declare function createCliParseArgv(input: {
    argv: string[];
    cwd: string;
    nodeArgv?: [string, string];
}): string[] | {
    kind: "open-project";
    resolvedPath: string;
};
export declare function runCli(argv: string[], options?: RunCliOptions): Promise<number>;
//# sourceMappingURL=run.d.ts.map