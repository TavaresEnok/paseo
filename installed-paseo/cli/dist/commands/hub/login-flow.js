import { spawn } from "node:child_process";
import { platform } from "node:os";
export class SystemBrowser {
    constructor(options = {}) {
        this.hostPlatform = options.hostPlatform ?? platform();
        this.launch = options.launch ?? launchDetached;
    }
    async open(url) {
        if (this.hostPlatform === "win32") {
            await this.launch("rundll32.exe", ["url.dll,FileProtocolHandler", url]);
            return;
        }
        await this.launch(this.hostPlatform === "darwin" ? "open" : "xdg-open", [url]);
    }
}
export class CliLoginFlow {
    constructor(options) {
        this.options = options;
    }
    async authorize(origin) {
        const authorization = await this.options.hub.startCliAuthorization(origin);
        this.options.instructions(authorization.verificationUri, authorization.userCode);
        if (this.options.openBrowser) {
            await this.options.browser.open(authorization.verificationUriComplete).catch(() => undefined);
        }
        let interval = authorization.interval;
        const expiresAt = Date.parse(authorization.expiresAt);
        while (true) {
            const remaining = expiresAt - this.options.waiter.now();
            if (remaining <= 0)
                throw new Error("Hub CLI login expired");
            await this.options.waiter.wait(Math.min(interval * 1000, remaining));
            const pollLifetime = expiresAt - this.options.waiter.now();
            if (pollLifetime <= 0)
                throw new Error("Hub CLI login expired");
            const outcome = await this.options.hub.pollCliAuthorization(origin, authorization.deviceCode, pollLifetime);
            const credential = approvedCredential(outcome);
            if (credential !== null)
                return credential;
            if (outcome.status === "denied")
                throw new Error("Hub CLI login was denied");
            if (outcome.status === "expired")
                throw new Error("Hub CLI login expired");
            if (outcome.status === "disclosed")
                throw new Error("Hub CLI login was already completed");
            if (outcome.status !== "retry_later")
                interval = outcome.interval;
        }
    }
}
export function createCliLoginFlow(hub) {
    return new CliLoginFlow({
        hub,
        waiter: {
            wait: (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)),
            now: Date.now,
        },
        browser: new SystemBrowser(),
        instructions(verificationUri, userCode) {
            process.stderr.write(`Open ${verificationUri} and enter code ${userCode}\n`);
        },
        openBrowser: process.stderr.isTTY === true,
    });
}
function approvedCredential(outcome) {
    return outcome.status === "authorized" ? outcome.credential : null;
}
async function launchDetached(command, args) {
    await new Promise((resolve, reject) => {
        const child = spawn(command, args, { detached: true, shell: false, stdio: "ignore" });
        child.once("spawn", () => {
            child.unref();
            resolve();
        });
        child.once("error", reject);
    });
}
//# sourceMappingURL=login-flow.js.map