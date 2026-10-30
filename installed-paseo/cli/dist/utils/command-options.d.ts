import type { Command } from "commander";
export declare function addLocalDaemonOptions<T extends Command>(command: T): T;
export declare function collectMultiple(value: string, previous: string[]): string[];
export declare function addJsonOption<T extends Command>(command: T): T;
export declare function addDaemonHostOption<T extends Command>(command: T): T;
export declare function addJsonAndDaemonHostOptions<T extends Command>(command: T): T;
export declare function withGlobalOptions<Args extends unknown[], Result>(handler: (...args: Args) => Result): (...args: Args) => Result;
//# sourceMappingURL=command-options.d.ts.map