import type { PluginUpdatePreview, PluginUpdateResult, PluginUpdateSelection, PluginUpdateProposal } from "@getpaseo/protocol/messages";
interface UpdateClient {
    previewPluginUpdates(input: {
        pluginId?: string;
        target?: PluginUpdateSelection;
    }): Promise<PluginUpdatePreview[]>;
    applyPluginUpdates(proposals: PluginUpdateProposal[]): Promise<PluginUpdateResult[]>;
}
export interface UpdateOptions {
    pluginId?: string;
    all?: boolean;
    ref?: string;
    version?: string;
    check?: boolean;
    yes?: boolean;
}
export interface UpdateInteraction {
    interactive: boolean;
    structured: boolean;
    write(text: string): void;
    confirm(message: string): Promise<boolean>;
}
export interface UpdateOutcome {
    id: string;
    outcome: PluginUpdatePreview["outcome"] | PluginUpdateResult["outcome"] | "declined";
    current?: PluginUpdatePreview["current"];
    target?: PluginUpdatePreview["target"];
    links?: string[];
    proposal?: PluginUpdateProposal;
    plugin?: PluginUpdateResult["plugin"];
    error?: string;
    warning?: string;
}
export declare function reviewPluginUpdates(client: UpdateClient, options: UpdateOptions, interaction: UpdateInteraction): Promise<UpdateOutcome[]>;
export declare function formatUpdatePreview(items: PluginUpdatePreview[]): string;
export {};
//# sourceMappingURL=update.d.ts.map