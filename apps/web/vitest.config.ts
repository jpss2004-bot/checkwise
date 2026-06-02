/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tsconfigPaths from "vite-tsconfig-paths";

/**
 * Vitest config for the CheckWise frontend.
 *
 * Decisions:
 *   - happy-dom over jsdom: 2-3x faster cold start, sufficient API
 *     coverage for the components we test (no Canvas, no Worker
 *     internals exercised in current tests).
 *   - vite-tsconfig-paths: lets tests import via the `@/...` alias
 *     used everywhere in the app without restating the alias here.
 *   - globals: true: `describe` / `it` / `expect` are global so tests
 *     read like Jest-style tests with no boilerplate at the top.
 *   - setupFiles: loads `@testing-library/jest-dom` matchers so we can
 *     `expect(el).toBeInTheDocument()` etc.
 */
export default defineConfig({
  plugins: [react(), tsconfigPaths()],
  test: {
    environment: "happy-dom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    css: false,
    // Run tests in parallel by default; this many components shouldn't
    // need more than ~3 workers locally.
    pool: "threads",
    // Filter test discovery to the conventional .test.ts(x) suffix
    // and __tests__/ folders. Anything else (storybook, mdx examples,
    // ad-hoc throwaways) stays out of CI.
    include: [
      "**/*.{test,spec}.?(c|m)[jt]s?(x)",
      "**/__tests__/**/*.?(c|m)[jt]s?(x)",
    ],
    exclude: [
      "**/node_modules/**",
      "**/.next/**",
      "**/dist/**",
    ],
  },
});
