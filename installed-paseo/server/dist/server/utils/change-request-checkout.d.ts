import type { PullRequestCheckoutRef } from "../services/forge-service.js";
export declare function buildPullHeadCheckoutRefs(number: number): PullRequestCheckoutRef[];
export declare function normalizeForgeOwnerForBranch(owner: string | null): string | null;
export interface ForkLocalBranchNameInput {
    headRef: string;
    number: number;
    isCrossRepository: boolean;
    headOwnerLogin: string | null;
    /** "pull-ref" when headRef is a synthetic pull ref, not a real branch name (agit PRs, deleted branches); undefined means "branch" */
    headRefKind?: "branch" | "pull-ref";
}
export declare function buildForkLocalBranchName(params: ForkLocalBranchNameInput): string;
//# sourceMappingURL=change-request-checkout.d.ts.map