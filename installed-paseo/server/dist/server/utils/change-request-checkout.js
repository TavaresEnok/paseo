// upstream for clones where origin is your fork
export function buildPullHeadCheckoutRefs(number) {
    return [
        { remoteName: "origin", remoteRef: `refs/pull/${number}/head` },
        { remoteName: "upstream", remoteRef: `refs/pull/${number}/head` },
    ];
}
// forgejo username pattern, covers github logins too
export function normalizeForgeOwnerForBranch(owner) {
    const normalized = owner?.trim().toLowerCase() ?? "";
    if (!/^[a-z0-9][a-z0-9_.-]*$/.test(normalized)) {
        return null;
    }
    // git refuses .. and .lock, trailing dot too
    if (normalized.includes("..") || normalized.endsWith(".") || normalized.endsWith(".lock")) {
        return null;
    }
    return normalized;
}
export function buildForkLocalBranchName(params) {
    const pullRefFallback = `pr-${params.number}`;
    // headRef is the literal pull ref (e.g. refs/pull/42/head) when there is no
    // real branch to name after, so use the pr number instead
    const headSegment = params.headRefKind === "pull-ref" ? pullRefFallback : params.headRef;
    if (!params.isCrossRepository) {
        return headSegment;
    }
    const owner = normalizeForgeOwnerForBranch(params.headOwnerLogin);
    if (!owner) {
        // don't double up pr-<n>/pr-<n> when the owner is also unknown
        return headSegment === pullRefFallback ? headSegment : `${pullRefFallback}/${headSegment}`;
    }
    return `${owner}/${headSegment}`;
}
//# sourceMappingURL=change-request-checkout.js.map