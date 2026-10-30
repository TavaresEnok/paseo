import { assignTaskNotificationReplayIds } from "./task-notification-tool-call.js";
import fs from "node:fs";
import path from "node:path";
import { normalizeProviderReplayTimestamp } from "../../provider-history-timestamps.js";
import { parseClaudeSubagentMeta, } from "./subagents/replay-source.js";
import { parseClaudeWorkflowRun, } from "./subagents/workflow-replay-source.js";
/** Chunk in bytes so UTF-8 and multi-chunk records are decoded once, at a line boundary. */
function* locatedRecords(file, fd) {
    const stat = fs.fstatSync(fd);
    // Opening a directory succeeds on some platforms; it must never look like empty history.
    if (stat.isDirectory()) {
        throw Object.assign(new Error(`EISDIR: illegal operation on a directory, read '${file}'`), {
            code: "EISDIR",
            syscall: "read",
            path: file,
        });
    }
    let remaining = stat.size;
    let offset = 0;
    let pieces = [];
    let length = 0;
    while (remaining > 0) {
        const buffer = Buffer.allocUnsafe(Math.min(64 * 1024, remaining));
        const count = fs.readSync(fd, buffer, 0, buffer.length, null);
        if (count === 0)
            break;
        remaining -= count;
        let start = 0;
        let end;
        while ((end = buffer.indexOf(10, start)) !== -1 && end < count) {
            pieces.push(buffer.subarray(start, end));
            length += end - start;
            const entry = parseRecord(Buffer.concat(pieces, length).toString("utf8"));
            const location = {
                file,
                offset,
                length,
                timestamp: normalizeProviderReplayTimestamp(entry?.timestamp),
            };
            offset += length + 1;
            pieces = [];
            length = 0;
            if (entry)
                yield { entry, location };
            start = end + 1;
        }
        if (start < count) {
            pieces.push(buffer.subarray(start, count));
            length += count - start;
        }
    }
    const entry = parseRecord(Buffer.concat(pieces, length).toString("utf8"));
    if (entry)
        yield {
            entry,
            location: {
                file,
                offset,
                length,
                timestamp: normalizeProviderReplayTimestamp(entry.timestamp),
            },
        };
}
/** Indexed sources parse only their own records using descriptors owned by this replay. */
function indexedRecords(locations, descriptors) {
    return {
        *[Symbol.iterator]() {
            yield* assignTaskNotificationReplayIds(readEntries());
        },
    };
    function* readEntries() {
        for (const location of locations) {
            const fd = descriptors.get(location.file);
            const buffer = Buffer.allocUnsafe(location.length);
            let read = 0;
            while (read < buffer.length) {
                const count = fs.readSync(fd, buffer, read, buffer.length - read, location.offset + read);
                if (count === 0)
                    throw new Error(`Claude transcript was truncated during replay: ${location.file}`);
                read += count;
            }
            const entry = parseRecord(buffer.toString("utf8"));
            if (entry)
                yield entry;
        }
    }
}
function isToolResult(entry) {
    return (Array.isArray(entry.message?.content) &&
        entry.message.content.some((block) => block?.type === "tool_result"));
}
function parseRecord(line) {
    try {
        const value = JSON.parse(line);
        return value !== null && typeof value === "object" && !Array.isArray(value)
            ? value
            : null;
    }
    catch {
        return null;
    }
}
function readOptionalFile(file) {
    try {
        return fs.readFileSync(file, "utf8");
    }
    catch {
        return null;
    }
}
/** Own descriptors through every pass so unlink or rename cannot invalidate discovered history.
 * Sources must be consumed before the callback returns. No transcript copies are needed. */
export function withClaudeReplayHistory(historyPath, consume) {
    const descriptors = new Map();
    try {
        return consume(indexHistory(historyPath, descriptors));
    }
    finally {
        for (const fd of descriptors.values())
            fs.closeSync(fd);
    }
}
function indexHistory(historyPath, descriptors) {
    const sessionDirectory = path.join(path.dirname(historyPath), path.basename(historyPath, ".jsonl"));
    const sidechainDirectory = path.join(sessionDirectory, "subagents");
    const sidechainFiles = [historyPath];
    const workflowFiles = new Map();
    const metaByAgentId = new Map();
    const directories = [sidechainDirectory];
    while (directories.length) {
        const directory = directories.pop();
        if (!fs.existsSync(directory))
            continue;
        for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
            const file = path.join(directory, entry.name);
            if (entry.isDirectory()) {
                directories.push(file);
                continue;
            }
            if (!entry.isFile())
                continue;
            if (entry.name.endsWith(".jsonl")) {
                const parts = path.relative(sidechainDirectory, file).split(path.sep);
                if (parts[0] === "workflows" && parts.length >= 3) {
                    const runId = parts[1];
                    const files = workflowFiles.get(runId) ?? [];
                    files.push(file);
                    workflowFiles.set(runId, files);
                }
                else
                    sidechainFiles.push(file);
                continue;
            }
            const agentId = /^agent-(.+)\.meta\.json$/.exec(entry.name)?.[1];
            if (!agentId)
                continue;
            const contents = readOptionalFile(file);
            const meta = contents === null ? null : parseClaudeSubagentMeta(contents);
            if (meta)
                metaByAgentId.set(agentId, meta);
        }
    }
    const parentLocations = [];
    const locationsByAgentId = new Map();
    function scan(file, visit) {
        const fd = fs.openSync(file, "r");
        descriptors.set(file, fd);
        for (const { entry, location } of locatedRecords(file, fd))
            visit(entry, location);
    }
    for (const file of sidechainFiles) {
        scan(file, (entry, location) => {
            if (file === historyPath && entry.isSidechain !== true)
                parentLocations.push(location);
            if (entry.isSidechain !== true || typeof entry.agentId !== "string")
                return;
            const locations = locationsByAgentId.get(entry.agentId) ?? [];
            locations.push(location);
            locationsByAgentId.set(entry.agentId, locations);
        });
    }
    const workflowEntriesByRunId = new Map();
    for (const [runId, files] of workflowFiles) {
        const locations = [];
        for (const file of files)
            scan(file, (entry, location) => {
                if (entry.type !== "user" || isToolResult(entry))
                    locations.push(location);
            });
        locations.sort((a, b) => {
            if (!a.timestamp && !b.timestamp)
                return 0;
            if (!a.timestamp)
                return 1;
            if (!b.timestamp)
                return -1;
            return Date.parse(a.timestamp) - Date.parse(b.timestamp);
        });
        workflowEntriesByRunId.set(runId, indexedRecords(locations, descriptors));
    }
    return {
        parentEntries: indexedRecords(parentLocations, descriptors),
        subagents: [...locationsByAgentId].map(([agentId, locations]) => ({
            agentId,
            meta: metaByAgentId.get(agentId) ?? null,
            entries: indexedRecords(locations, descriptors),
        })),
        workflows: readWorkflows(sessionDirectory),
        workflowEntriesByRunId,
    };
}
function readWorkflows(sessionDirectory) {
    const workflows = [];
    const workflowDirectory = path.join(sessionDirectory, "workflows");
    if (fs.existsSync(workflowDirectory)) {
        for (const entry of fs.readdirSync(workflowDirectory, { withFileTypes: true })) {
            if (!entry.isFile() || !entry.name.endsWith(".json"))
                continue;
            const contents = readOptionalFile(path.join(workflowDirectory, entry.name));
            const workflow = contents === null ? null : parseClaudeWorkflowRun(contents);
            if (workflow)
                workflows.push(workflow);
        }
    }
    return workflows;
}
//# sourceMappingURL=transcript-history.js.map