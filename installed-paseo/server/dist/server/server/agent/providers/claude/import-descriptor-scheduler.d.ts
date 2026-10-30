interface ImportDescriptorCandidate {
    cacheKey: string;
}
export declare function createImportDescriptorScheduler<Candidate extends ImportDescriptorCandidate, Descriptor>(read: (candidate: Candidate, signal: AbortSignal) => Promise<Descriptor>): (candidates: Candidate[], signal: AbortSignal) => Promise<Descriptor[]>;
export {};
//# sourceMappingURL=import-descriptor-scheduler.d.ts.map