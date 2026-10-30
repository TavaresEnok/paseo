import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { z } from "zod";
import { writeJsonFileAtomic } from "../../../atomic-file.js";
const recordsSchema = z.array(z.object({
    id: z.string().min(1),
    callerAgentId: z.string().min(1),
    childAgentId: z.string().min(1),
    serverId: z.string().min(1).optional(),
    requireParentOwnership: z.boolean().optional(),
}));
export function createJsonFinishSubscriptionStore(paseoHome) {
    const file = join(paseoHome, "finish-subscriptions.json");
    let records;
    let pending = Promise.resolve();
    async function load() {
        if (records)
            return records;
        try {
            records = recordsSchema.parse(JSON.parse(await readFile(file, "utf8")));
        }
        catch (error) {
            if (error.code !== "ENOENT")
                throw error;
            records = [];
        }
        return records;
    }
    function serialized(action) {
        const result = pending.then(action);
        pending = result.then(() => undefined, () => undefined);
        return result;
    }
    async function mutate(update) {
        const next = update(await load());
        await writeJsonFileAtomic(file, next);
        records = next;
    }
    return {
        list: () => serialized(async () => (await load()).map((record) => Object.assign({}, record))),
        put: (subscription) => serialized(() => mutate((current) => [
            ...current.filter((record) => record.id !== subscription.id),
            { ...subscription },
        ])),
        remove: (id) => serialized(() => mutate((current) => current.filter((record) => record.id !== id))),
    };
}
//# sourceMappingURL=json-store.js.map