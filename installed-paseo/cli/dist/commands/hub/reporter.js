export const processHubReporter = {
    progress(message) {
        process.stderr.write(`${message}\n`);
    },
};
export function reportHubProgress(reporter, options, message) {
    if (options.json === true)
        return;
    reporter.progress(message);
}
//# sourceMappingURL=reporter.js.map