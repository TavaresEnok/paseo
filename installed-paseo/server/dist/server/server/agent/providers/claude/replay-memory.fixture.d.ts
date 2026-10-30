/** Full-scale reproduction is opt-in: run this file with ROOT children --generate. */
export declare function generateReplayCorpus(root: string, size?: {
    parentMiB: number;
    childrenMiB: number;
    children: number;
}): {
    cwd: string;
    configDir: string;
};
export declare function generateWorkflowReplayCorpus(root: string, childMiB?: number): {
    cwd: string;
    configDir: string;
};
//# sourceMappingURL=replay-memory.fixture.d.ts.map