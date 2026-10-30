/**
 * Path utilities for cwd filtering in agent commands.
 */
/**
 * Check if `candidatePath` is the same directory as `basePath` or a descendant of it.
 *
 * Handles both Unix (/) and Windows (\) path separators, including mixed separators.
 * This is important because agent cwd paths come from the agent's OS (could be Windows)
 * while the CLI filter path comes from the user (could also be Windows or Unix).
 */
export declare function isSameOrDescendantPath(basePath: string, candidatePath: string): boolean;
//# sourceMappingURL=paths.d.ts.map