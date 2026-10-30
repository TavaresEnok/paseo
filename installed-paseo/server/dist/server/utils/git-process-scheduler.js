import { setImmediate as scheduleImmediate } from "node:timers";
import pThrottle from "p-throttle";
export const DEFAULT_GIT_PROCESS_POLICY = {
    maxProcessesPerSecond: 64,
    maxProcessConcurrency: 8,
};
function parsePositiveInteger(value) {
    if (value === undefined) {
        return undefined;
    }
    const parsed = Number(value);
    return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}
export function resolveGitProcessPolicy(input) {
    return {
        maxProcessesPerSecond: parsePositiveInteger(input.env.PASEO_GIT_MAX_PROCESSES_PER_SECOND) ??
            input.persisted?.maxProcessesPerSecond ??
            DEFAULT_GIT_PROCESS_POLICY.maxProcessesPerSecond,
        maxProcessConcurrency: parsePositiveInteger(input.env.PASEO_GIT_MAX_PROCESS_CONCURRENCY) ??
            // COMPAT(gitConcurrencyEnv): renamed in v0.2.6; remove after 2027-02-02.
            parsePositiveInteger(input.env.PASEO_GIT_CONCURRENCY) ??
            input.persisted?.maxProcessConcurrency ??
            DEFAULT_GIT_PROCESS_POLICY.maxProcessConcurrency,
    };
}
export class GitProcessScheduler {
    constructor(policy) {
        this.policy = policy;
        this.highPriorityQueue = [];
        this.normalPriorityQueue = [];
        this.admitted = 0;
        this.running = 0;
        this.waiting = 0;
        this.drainScheduled = false;
        const throttle = pThrottle({
            limit: policy.maxProcessesPerSecond,
            interval: 1000,
            strict: true,
        });
        this.startThrottled = throttle((start) => start());
    }
    get activeCount() {
        return this.running;
    }
    get pendingCount() {
        return this.waiting;
    }
    run(start, options) {
        this.waiting += 1;
        return new Promise((resolve, reject) => {
            const admit = () => {
                void this.startThrottled(() => this.execute(start, resolve, reject)).catch((error) => {
                    this.waiting = Math.max(0, this.waiting - 1);
                    this.admitted = Math.max(0, this.admitted - 1);
                    reject(error);
                    this.scheduleDrain();
                });
            };
            const queue = options?.priority === "high" ? this.highPriorityQueue : this.normalPriorityQueue;
            queue.push(admit);
            if (this.admitted === 0 && !this.drainScheduled) {
                this.drainOne();
            }
            else {
                this.scheduleDrain();
            }
        });
    }
    scheduleDrain() {
        if (this.drainScheduled || this.admitted >= this.policy.maxProcessConcurrency) {
            return;
        }
        if (this.highPriorityQueue.length === 0 && this.normalPriorityQueue.length === 0) {
            return;
        }
        this.drainScheduled = true;
        scheduleImmediate(() => this.drainOne());
    }
    drainOne() {
        this.drainScheduled = false;
        if (this.admitted >= this.policy.maxProcessConcurrency) {
            return;
        }
        const admit = this.highPriorityQueue.shift() ?? this.normalPriorityQueue.shift();
        if (!admit) {
            return;
        }
        this.admitted += 1;
        admit();
        // Spawning can be synchronous and expensive on a throttled host. Let timers,
        // sockets, and child exits run before admitting another Git process.
        this.scheduleDrain();
    }
    async execute(start, resolve, reject) {
        this.waiting = Math.max(0, this.waiting - 1);
        this.running += 1;
        try {
            const process = start();
            void process.result.then(resolve, reject);
            await process.exited;
        }
        catch (error) {
            reject(error);
        }
        finally {
            this.running = Math.max(0, this.running - 1);
            this.admitted = Math.max(0, this.admitted - 1);
            this.scheduleDrain();
        }
    }
}
//# sourceMappingURL=git-process-scheduler.js.map