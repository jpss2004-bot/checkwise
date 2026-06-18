import { useEffect, useState } from "react";

/**
 * Debounce a fast-changing value (e.g. a search box) so downstream effects —
 * typically a server query keyed on it — fire once the value settles instead
 * of on every keystroke. Returns the latest value after `delayMs` of quiet.
 */
export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}
