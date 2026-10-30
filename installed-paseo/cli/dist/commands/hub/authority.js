import { HubCommandError } from "./error.js";
import { normalizeHubOrigin } from "./origin.js";
export const DEFAULT_HUB_ORIGIN = "https://hub.paseo.sh";
export function resolveHubOrigin(input) {
    const configuredOrigin = input.options.origin ?? input.env.PASEO_HUB_URL;
    const selectedOrigin = configuredOrigin ?? input.credentials.active()?.origin ?? DEFAULT_HUB_ORIGIN;
    return normalizeHubOrigin(selectedOrigin);
}
export function resolveHubCredential(input) {
    const explicitCredential = input.options.apiKey ?? input.env.PASEO_HUB_API_KEY;
    if (explicitCredential !== undefined)
        return explicitCredential;
    const stored = input.credentials.get(input.origin);
    if (stored !== null)
        return stored.credential;
    throw new HubCommandError("HUB_API_KEY_REQUIRED", `No stored Hub login matches ${input.origin}. Run \`paseo hub login ${input.origin}\`, pass --api-key <secret>, or set PASEO_HUB_API_KEY.`);
}
//# sourceMappingURL=authority.js.map