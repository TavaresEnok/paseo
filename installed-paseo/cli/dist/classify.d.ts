export type CliInvocation = {
    kind: "cli";
    argv: string[];
} | {
    kind: "open-project";
    resolvedPath: string;
};
export declare function isPathLikeArg(arg: string): boolean;
export declare function expandUserPath(inputPath: string): string;
export declare function isExistingDirectory(input: {
    pathArg: string;
    cwd: string;
}): boolean;
export declare function classifyInvocation(input: {
    argv: string[];
    knownCommands: ReadonlySet<string>;
    cwd: string;
}): CliInvocation;
//# sourceMappingURL=classify.d.ts.map