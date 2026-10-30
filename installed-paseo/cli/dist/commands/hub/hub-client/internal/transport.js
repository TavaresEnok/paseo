import { HubCommandError } from "../../error.js";
import { hubRequestFailure } from "./problem.js";
export async function requestHub(input) {
    const signal = AbortSignal.timeout(input.timeoutMilliseconds ?? 15000);
    let response;
    try {
        response = await fetch(`${input.origin}${input.path}`, {
            method: input.method,
            headers: {
                ...(input.apiKey === undefined ? {} : { authorization: `Bearer ${input.apiKey}` }),
                ...(input.body === undefined ? {} : { "content-type": "application/json" }),
            },
            ...(input.body === undefined ? {} : { body: JSON.stringify(input.body) }),
            signal,
        });
    }
    catch {
        throw new HubCommandError("HUB_NETWORK_ERROR", `Could not reach Paseo Hub at ${input.origin}. Check the Hub URL and network connection.`);
    }
    if (response.status !== input.successStatus) {
        throw await hubRequestFailure(response, input.failureMessage, input.apiKey);
    }
    try {
        return input.schema.parse(await response.json());
    }
    catch {
        throw new HubCommandError("HUB_INVALID_RESPONSE", "Hub returned a malformed response.");
    }
}
//# sourceMappingURL=transport.js.map