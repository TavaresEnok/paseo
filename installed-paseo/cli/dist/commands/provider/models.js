import { connectToDaemon } from "../../utils/client.js";
/** Schema for provider models output */
export const providerModelsSchema = {
    idField: "id",
    columns: [
        { header: "ID", field: "id", width: 30 },
        { header: "MODEL", field: "model", width: 30 },
        { header: "DESCRIPTION", field: "description", width: 40 },
    ],
};
const providerModelsWithThinkingSchema = {
    idField: "id",
    columns: [
        { header: "ID", field: "id", width: 30 },
        { header: "MODEL", field: "model", width: 30 },
        { header: "THINKING IDS", field: "thinkingOptions", width: 40 },
        {
            header: "DEFAULT THINKING",
            field: (item) => item.defaultThinkingOptionId ?? "auto",
            width: 18,
        },
    ],
};
export async function runModelsCommand(provider, options, _command) {
    const normalizedProvider = provider.toLowerCase();
    const client = await connectToDaemon({ target: options.daemonTarget });
    try {
        const result = await client.listProviderModels(normalizedProvider);
        if (result.error) {
            throw {
                code: "PROVIDER_ERROR",
                message: `Failed to fetch models for ${provider}: ${result.error}`,
            };
        }
        const models = (result.models ?? []).map((m) => ({
            model: m.label,
            id: m.id,
            description: m.description ?? "",
            thinkingOptionIds: (m.thinkingOptions ?? []).map((option) => option.id),
            defaultThinkingOptionId: m.defaultThinkingOptionId ?? null,
            thinkingOptions: (m.thinkingOptions ?? []).map((option) => option.id).join(", ") || "none",
        }));
        return {
            type: "list",
            data: models,
            schema: options.thinking ? providerModelsWithThinkingSchema : providerModelsSchema,
        };
    }
    finally {
        await client.close();
    }
}
//# sourceMappingURL=models.js.map