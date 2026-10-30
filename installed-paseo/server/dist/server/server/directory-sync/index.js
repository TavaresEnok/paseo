import { randomUUID } from "node:crypto";
import { VersionedCollection } from "./internal/versioned-collection.js";
/** Daemon-global latest-state sequence owner for the active app directory. */
export class DirectorySyncService {
    constructor(generation = randomUUID()) {
        this.projects = new VersionedCollection({
            getId: (project) => project.projectId,
        });
        this.workspaces = new VersionedCollection({
            getId: (workspace) => workspace.id,
        });
        this.agents = new VersionedCollection({
            getId: (entry) => entry.agent.id,
        });
        this.generation = generation;
    }
    synchronizeProjects(snapshot, cursor) {
        this.projects.replaceAll(snapshot);
        const read = this.read(this.projects, cursor);
        return {
            projects: read.values.map(({ seq, value }) => ({ ...value, syncSeq: seq })),
            sync: this.metadata(read),
        };
    }
    synchronizeWorkspaces(snapshot, cursor, includeBackground = false) {
        this.workspaces.replaceAll(snapshot);
        const read = this.read(this.workspaces, cursor, includeBackground);
        return {
            entries: read.values.map(({ seq, value }) => ({ ...value, syncSeq: seq })),
            emptyProjects: [],
            pageInfo: { nextCursor: null, prevCursor: null, hasMore: false },
            sync: this.metadata(read, includeBackground),
        };
    }
    synchronizeAgents(snapshot, cursor, includeBackground = false) {
        this.agents.replaceAll(snapshot);
        const read = this.read(this.agents, cursor, includeBackground);
        return {
            entries: read.values.map(({ seq, value }) => ({ ...value, syncSeq: seq })),
            pageInfo: { nextCursor: null, prevCursor: null, hasMore: false },
            sync: this.metadata(read, includeBackground),
        };
    }
    sequenceProjectUpdate(update, includeSequence) {
        if (update.kind === "upsert") {
            this.projects.replace(update.project);
        }
        else {
            this.projects.remove(update.projectId);
        }
        const id = update.kind === "upsert" ? update.project.projectId : update.projectId;
        return this.withVersion(update, includeSequence, this.version(this.projects, id));
    }
    sequenceWorkspaceUpdate(payload, value, id, includeSequence, includeBackground = false) {
        if (value) {
            this.workspaces.replace(value);
        }
        else {
            this.workspaces.remove(id);
        }
        return this.withVersion(payload, includeSequence, this.version(this.workspaces, id), includeBackground);
    }
    sequenceAgentUpdate(payload, value, id, includeSequence, includeBackground = false) {
        if (value) {
            this.agents.replace(value);
        }
        else {
            this.agents.remove(id);
        }
        return this.withVersion(payload, includeSequence, this.version(this.agents, id), includeBackground);
    }
    metadata(read, includeBackground = false) {
        return {
            generation: this.generationFor(includeBackground),
            headSeq: read.headSeq,
            mode: read.mode,
            ...(read.reason ? { reason: read.reason } : {}),
            removals: read.removals,
        };
    }
    withVersion(payload, includeSequence, version, includeBackground = false) {
        return version && includeSequence
            ? { ...payload, ...version, generation: this.generationFor(includeBackground) }
            : payload;
    }
    read(collection, cursor, includeBackground = false) {
        if (cursor.generation !== this.generationFor(includeBackground)) {
            return collection.readSnapshot(cursor.generation === undefined ? "no_cursor" : "generation_changed");
        }
        if (cursor.afterSeq === undefined) {
            return collection.readSnapshot("no_cursor");
        }
        return collection.readAfter(cursor.afterSeq);
    }
    generationFor(includeBackground) {
        return includeBackground ? `${this.generation}:background` : this.generation;
    }
    version(collection, id) {
        const seq = collection.sequenceFor(id);
        return seq === null ? null : { generation: this.generation, seq };
    }
}
//# sourceMappingURL=index.js.map