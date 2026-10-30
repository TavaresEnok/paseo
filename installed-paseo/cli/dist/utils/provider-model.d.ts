export interface ResolveProviderAndModelOptions {
    provider?: string;
    model?: string;
    defaultProvider?: string;
}
export interface ResolvedProviderModel {
    provider: string;
    model: string | undefined;
}
export declare function resolveProviderAndModel(options: ResolveProviderAndModelOptions): ResolvedProviderModel;
//# sourceMappingURL=provider-model.d.ts.map