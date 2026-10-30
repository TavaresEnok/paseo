export interface HubReporter {
    progress(message: string): void;
}
export declare const processHubReporter: HubReporter;
interface HubReportOptions {
    json?: boolean;
}
export declare function reportHubProgress(reporter: HubReporter, options: HubReportOptions, message: string): void;
export {};
//# sourceMappingURL=reporter.d.ts.map