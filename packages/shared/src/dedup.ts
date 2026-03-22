const inflight = new Map<string, Promise<unknown>>();

export const dedup = <T>(key: string, fn: () => Promise<T>): Promise<T> => {
  const existing = inflight.get(key);
  if (existing !== undefined) {
    return existing as Promise<T>;
  }

  const promise = fn().finally(() => {
    inflight.delete(key);
  });

  inflight.set(key, promise);
  return promise;
};
