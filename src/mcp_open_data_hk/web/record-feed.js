/* A bounded page across independently version-pinned accepted sources.
 * Source failures remain failures. Names and stock codes never join identities. */
export class RecordFeed {
    constructor(sources) { this.sources = sources; this.generation = 0; this.pages = []; this.index = -1; }
    cancel() { this.generation++; this.controller?.abort(); }
    async search(query) {
        this.cancel();
        this.query = query;
        this.pages = [];
        this.index = -1;
        return this.load(Object.fromEntries(this.sources.map(s => [s.id, { cursor: null, version: null, done: false }])));
    }
    async load(inputs) {
        const run = ++this.generation;
        this.controller?.abort();
        this.controller = new AbortController();
        const states = await Promise.all(this.sources.map(async (source) => {
            const state = inputs[source.id];
            if (state.done)
                return { ...state, items: [], error: null };
            try {
                const page = await source.read(this.query, { ...state, signal: this.controller.signal });
                if (!page || !Array.isArray(page.items) || page.items.length > 100 || typeof page.version !== 'string' || !page.version || state.version && page.version !== state.version)
                    throw Error('SOURCE_SCHEMA_CHANGED');
                if (page.nextCursor != null && (typeof page.nextCursor !== 'string' || page.nextCursor === state.cursor))
                    throw Error('INVALID_CURSOR');
                return { items: page.items, version: page.version, cursor: page.nextCursor || null, done: !page.nextCursor, error: null, meta: page.meta };
            }
            catch (error) {
                return { ...state, items: [], error: error.message || 'SOURCE_UNAVAILABLE' };
            }
        }));
        if (run !== this.generation)
            return null;
        const page = { inputs, states: Object.fromEntries(this.sources.map((s, i) => [s.id, states[i]])) };
        this.pages = this.pages.slice(0, this.index + 1);
        this.pages.push(page);
        this.index++;
        return page;
    }
    get current() { return this.pages[this.index] || null; }
    get hasNext() { return Boolean(this.current && Object.values(this.current.states).some(s => !s.done && !s.error)); }
    async next() { if (!this.hasNext)
        return null; return this.load(this.current.states); }
    previous() { this.cancel(); if (this.index > 0)
        this.index--; return this.current; }
    async retry() { if (!this.current)
        return null; const prior = this.current; this.index--; const fresh = await this.load(Object.fromEntries(Object.entries(prior.states).map(([id, state]) => [id, state.error ? prior.inputs[id] : { ...state, done: true }]))); if (fresh)
        for (const [id, state] of Object.entries(prior.states))
            if (!state.error)
                fresh.states[id] = state; return fresh; }
}
export function feedRows(page, locale = 'en') {
    const rows = Object.entries(page?.states || {}).flatMap(([source, s]) => (s.items || []).map(item => ({ ...item, source, version: s.version, key: source + ':' + item.id })));
    const grouped = new Map();
    for (const row of rows) {
        // Only an explicit shared source identifier can combine observations.
        // Keep every source variant so dates, conflicts and attribution survive.
        const key = row.identity || row.key, prior = grouped.get(key);
        if (prior) {
            prior.variants.push(row);
            if ((row.date || '') > (prior.date || ''))
                prior.date = row.date;
        }
        else
            grouped.set(key, { ...row, variants: [row] });
    }
    // Sorting is within this bounded page, not an invented global source order.
    return [...grouped.values()].sort((a, b) => (b.date || '').localeCompare(a.date || '') || a.title.localeCompare(b.title, locale) || a.key.localeCompare(b.key));
}

// Share only query inputs, never returned records or ingestion receipts.
export function feedCheckpoint(page, number) {
    return {number, sources: Object.fromEntries(Object.entries(page.states).map(([id, state]) => [id, {
        cursor: page.inputs[id].cursor || null,
        version: state.version || page.inputs[id].version || null,
        done: Boolean(page.inputs[id].done),
        meta: {issuer: page.inputs[id].meta?.issuer || null}
    }]))};
}

export function readCheckpoint(raw, sourceIds) {
    if (!raw || raw.length > 12000) return null;
    try {
        const checkpoint = JSON.parse(raw);
        if (!Number.isSafeInteger(checkpoint.number) || checkpoint.number < 1 || checkpoint.number > 1000000) return null;
        if (Object.keys(checkpoint.sources).length !== sourceIds.length) return null;
        for (const id of sourceIds) {
            const state = checkpoint.sources[id];
            if (!state || typeof state.done !== 'boolean') return null;
            if (state.cursor !== null && (typeof state.cursor !== 'string' || state.cursor.length > 2048)) return null;
            if (state.version !== null && (typeof state.version !== 'string' || !/^[A-Za-z0-9._-]{1,100}$/.test(state.version))) return null;
            if (state.meta?.issuer != null && !/^webb:person:[0-9]{1,12}$/.test(state.meta.issuer)) return null;
        }
        return checkpoint;
    } catch { return null; }
}
