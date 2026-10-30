export function availableStarterAgentProviders(entries) {
    return entries.flatMap((entry) => {
        if (entry.status !== "ready" || !entry.enabled)
            return [];
        const models = (entry.models ?? [])
            .filter((model) => model.isSelectable !== false)
            .map((model) => ({ id: model.id, label: model.label, suggested: model.isDefault === true }));
        if (models.length === 0)
            return [];
        const modes = (entry.modes ?? []).map((mode) => ({
            id: mode.id,
            label: mode.label,
            suggested: mode.id === entry.defaultModeId,
        }));
        return [
            {
                id: entry.provider,
                label: entry.label ?? entry.provider,
                models,
                modes,
            },
        ];
    });
}
export function starterAgentProviderSnapshotState(entries) {
    const providers = availableStarterAgentProviders(entries);
    if (providers.length > 0)
        return { kind: "ready", providers };
    if (entries.length === 0)
        return { kind: "loading" };
    if (entries.some((entry) => entry.enabled && entry.status === "loading")) {
        return { kind: "loading" };
    }
    return { kind: "unavailable" };
}
export function suggestedStarterAgentChoice(choices) {
    return choices.find((choice) => choice.suggested);
}
export function selectedStarterAgentRuntime(provider, modelId, modeId) {
    if (!provider.models.some((model) => model.id === modelId))
        return undefined;
    if (provider.modes.length === 0) {
        return modeId === undefined ? { provider: provider.id, model: modelId } : undefined;
    }
    if (modeId === undefined || !provider.modes.some((mode) => mode.id === modeId))
        return undefined;
    return { provider: provider.id, model: modelId, mode: modeId };
}
//# sourceMappingURL=starter-agent-runtime.js.map