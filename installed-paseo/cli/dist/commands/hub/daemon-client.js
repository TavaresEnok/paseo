import { connectToDaemon } from "../../utils/client.js";
export const productionHubDaemonConnection = {
    connect: (target) => connectToDaemon({ target }),
};
export async function withHubDaemon(connection, target, action) {
    const client = await connection.connect(target);
    try {
        return await action(client);
    }
    finally {
        await client.close().catch(() => undefined);
    }
}
//# sourceMappingURL=daemon-client.js.map