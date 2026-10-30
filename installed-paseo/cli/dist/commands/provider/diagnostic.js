import { connectToDaemon } from "../../utils/client.js";
export const providerDiagnosticSchema = {
    idField: "provider",
    columns: [
        { header: "PROVIDER", field: "provider" },
        { header: "DIAGNOSTIC", field: "diagnostic" },
    ],
    renderHuman(result) {
        if (result.type === "single")
            return result.data.diagnostic;
        return result.data.map((entry) => entry.diagnostic).join("\n\n");
    },
};
export async function runDiagnosticCommand(provider, options, _command) {
    const client = await connectToDaemon({ target: options.daemonTarget });
    try {
        const result = await client.getProviderDiagnostic(provider.trim().toLowerCase());
        return {
            type: "single",
            data: {
                provider: result.provider,
                diagnostic: result.diagnostic,
            },
            schema: providerDiagnosticSchema,
        };
    }
    finally {
        await client.close();
    }
}
//# sourceMappingURL=diagnostic.js.map