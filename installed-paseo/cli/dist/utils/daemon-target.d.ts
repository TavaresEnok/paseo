export type DaemonTarget = {
    kind: "instance";
    home: string;
} | {
    kind: "endpoint";
    host: string;
};
export declare function selectDaemonTarget(options: {
    home?: string;
    host?: string;
}, env?: NodeJS.ProcessEnv, localOnly?: boolean): DaemonTarget;
export declare function describeDaemonTarget(target: DaemonTarget): string;
//# sourceMappingURL=daemon-target.d.ts.map