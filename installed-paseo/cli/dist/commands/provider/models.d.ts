import type { Command } from "commander";
import type { CommandOptions, ListResult, OutputSchema } from "../../output/index.js";
/** Model list item for display */
export interface ModelListItem {
    model: string;
    id: string;
    description: string;
    thinkingOptionIds: string[];
    defaultThinkingOptionId: string | null;
    thinkingOptions: string;
}
/** Schema for provider models output */
export declare const providerModelsSchema: OutputSchema<ModelListItem>;
export type ProviderModelsResult = ListResult<ModelListItem>;
export interface ProviderModelsOptions extends CommandOptions {
    host?: string;
    thinking?: boolean;
}
export declare function runModelsCommand(provider: string, options: ProviderModelsOptions, _command: Command): Promise<ProviderModelsResult>;
//# sourceMappingURL=models.d.ts.map