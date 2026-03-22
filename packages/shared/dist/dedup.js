const inflight = new Map();
export const dedup = (key, fn) => {
    const existing = inflight.get(key);
    if (existing !== undefined) {
        return existing;
    }
    const promise = fn().finally(() => {
        inflight.delete(key);
    });
    inflight.set(key, promise);
    return promise;
};
//# sourceMappingURL=dedup.js.map