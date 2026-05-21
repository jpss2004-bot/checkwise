/**
 * Tiny ring buffer of recent console errors/warns + global errors.
 *
 * The FeedbackLauncher attaches the last N entries to each report so
 * we have something to look at when a tester says "it didn't work".
 *
 * Idempotent: ``startConsoleCapture()`` is safe to call multiple times
 * (e.g. from the launcher mount in three different shells). It only
 * monkey-patches ``console`` once per page load.
 *
 * Captured signals:
 *   - ``console.error`` calls
 *   - ``console.warn`` calls
 *   - ``window.onerror`` / "error" events
 *   - unhandled promise rejections
 *
 * Each entry is truncated to ``MAX_ENTRY_CHARS`` so a single huge
 * payload (e.g. a stringified DOM tree) does not crowd everything
 * else out of the buffer.
 */

const MAX_ENTRIES = 20;
const MAX_ENTRY_CHARS = 400;

const buffer: string[] = [];
let installed = false;

export function startConsoleCapture(): void {
  if (typeof window === "undefined" || installed) return;
  installed = true;

  const originalError = console.error.bind(console);
  const originalWarn = console.warn.bind(console);

  console.error = (...args: unknown[]) => {
    record("error", args);
    originalError(...args);
  };
  console.warn = (...args: unknown[]) => {
    record("warn", args);
    originalWarn(...args);
  };

  window.addEventListener("error", (event) => {
    record("window.error", [event.message, event.filename, event.lineno]);
  });
  window.addEventListener("unhandledrejection", (event) => {
    record("unhandledrejection", [event.reason]);
  });
}

export function snapshotConsoleLog(): string {
  return buffer.join("\n");
}

export function clearConsoleLog(): void {
  buffer.length = 0;
}

function record(level: string, args: unknown[]): void {
  const time = new Date().toISOString().slice(11, 19);
  const text = args.map(formatArg).join(" ").slice(0, MAX_ENTRY_CHARS);
  buffer.push(`[${time}] [${level}] ${text}`);
  while (buffer.length > MAX_ENTRIES) buffer.shift();
}

function formatArg(value: unknown): string {
  if (value instanceof Error) {
    return value.stack ? value.stack.split("\n").slice(0, 3).join(" | ") : value.message;
  }
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}
