export function resolveProviderAndModel(options) {
    const providerInput = options.provider?.trim() || options.defaultProvider;
    const modelInput = options.model?.trim();
    if (!providerInput) {
        const error = {
            code: "MISSING_PROVIDER",
            message: "Provider is required",
            details: "Pass --provider <provider> or --provider <provider>/<model>. Use `paseo provider ls` to see providers and `paseo provider models <provider>` to see models.",
        };
        throw error;
    }
    if (options.model !== undefined && !modelInput) {
        const error = {
            code: "INVALID_MODEL",
            message: "--model cannot be empty",
        };
        throw error;
    }
    const slashIndex = providerInput.indexOf("/");
    if (slashIndex === -1) {
        return {
            provider: providerInput,
            model: modelInput,
        };
    }
    const provider = providerInput.slice(0, slashIndex).trim();
    const modelFromProvider = providerInput.slice(slashIndex + 1).trim();
    if (!provider || !modelFromProvider) {
        const error = {
            code: "INVALID_PROVIDER",
            message: "Invalid --provider value",
            details: "Use --provider <provider> or --provider <provider>/<model>",
        };
        throw error;
    }
    if (modelInput && modelInput !== modelFromProvider) {
        const error = {
            code: "CONFLICTING_MODEL_OPTIONS",
            message: "Conflicting model values provided",
            details: `--provider specifies model ${modelFromProvider}, but --model specifies ${modelInput}`,
        };
        throw error;
    }
    return {
        provider,
        model: modelInput ?? modelFromProvider,
    };
}
//# sourceMappingURL=provider-model.js.map