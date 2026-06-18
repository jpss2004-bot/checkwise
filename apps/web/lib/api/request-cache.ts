/**
 * Tiny in-flight de-duplication + short-TTL cache for idempotent GET reads.
 *
 * The app has no data-fetching library (no React Query / SWR), so identity /
 * summary / overview reads were re-fetched on every mount and fired twice
 * whenever a shell and its page requested the same endpoint concurrently
 * (e.g. the client shell's consent gate and the dashboard both call
 * ``getClientMe``). This utility:
 *
 *   1. Coalesces concurrent identical reads — while a request is in flight,
 *      further callers with the same key share the same promise. This is
 *      always safe for idempotent GETs and carries **zero** staleness risk:
 *      the in-flight entry is dropped the moment the promise settles.
 *   2. Optionally serves the resolved value for a short TTL, so repeated
 *      reads across navigations don't re-hit the network.
 *
 * Rules of use:
 *   - Only ever wrap GET-shaped, idempotent reads. Never wrap a mutation.
 *   - Errors are never cached (they re-throw), so fail-closed callers keep
 *     their behaviour.
 *   - When a mutation changes a cached resource, call ``invalidateRead`` with
 *     the key (or a key prefix) so the next read observes fresh data.
 */

type CacheEntry<T> = { at: number; value: T };

const inflight = new Map<string, Promise<unknown>>();
const ttlCache = new Map<string, CacheEntry<unknown>>();

/**
 * Read ``loader()`` through the de-dupe (+ optional TTL) layer.
 *
 * @param key    Stable identity for the request (include any query params).
 * @param loader The actual fetch; only invoked on a cache+in-flight miss.
 * @param ttlMs  When > 0, serve the resolved value for this many ms. Defaults
 *               to 0 (coalesce concurrent calls only, never serve stale).
 */
export function dedupeRead<T>(
  key: string,
  loader: () => Promise<T>,
  ttlMs = 0,
): Promise<T> {
  if (ttlMs > 0) {
    const hit = ttlCache.get(key) as CacheEntry<T> | undefined;
    if (hit && Date.now() - hit.at < ttlMs) {
      return Promise.resolve(hit.value);
    }
  }

  const pending = inflight.get(key) as Promise<T> | undefined;
  if (pending) return pending;

  const promise = loader()
    .then((value) => {
      if (ttlMs > 0) ttlCache.set(key, { at: Date.now(), value });
      return value;
    })
    .finally(() => {
      inflight.delete(key);
    });
  inflight.set(key, promise);
  return promise;
}

/**
 * Drop cached entries whose key equals ``keyOrPrefix`` or starts with it.
 * Call after a mutation that changes the underlying resource. Does not touch
 * in-flight requests (those resolve to the value that was current when they
 * were issued, which is correct).
 */
export function invalidateRead(keyOrPrefix: string): void {
  for (const k of ttlCache.keys()) {
    if (k === keyOrPrefix || k.startsWith(keyOrPrefix)) {
      ttlCache.delete(k);
    }
  }
}
