import { createHash } from "node:crypto";

import type { NextConfig } from "next";

/**
 * Resolve the `distDir` Next.js should write builds into.
 *
 * Background:
 *   Next.js 15 + webpack stores absolute paths in the `.next/` manifests
 *   it generates. When the project's absolute path contains characters
 *   like em-dash (U+2014), some `fs.rename` and `require()` calls on
 *   macOS fail with ENOENT even though the directory exists. The dev
 *   server then loops on "Cannot find module '.next/server/middleware
 *   -manifest.json'" because the temp-to-final rename silently aborted.
 *
 *   Empirically the bug is keyed off the literal `.next` directory name
 *   under a path with non-ASCII characters. Renaming the dist dir to a
 *   different ASCII-only name (e.g. `.cw-next-<hash>`) sidesteps the
 *   race. On normal (ASCII) paths, we keep `.next` so tooling that
 *   targets it directly keeps working.
 *
 *   Override with `CHECKWISE_DIST_DIR=<path>` to force a specific dir.
 */

function pathHasNonAscii(s: string): boolean {
  for (let i = 0; i < s.length; i++) {
    if (s.charCodeAt(i) > 127) return true;
  }
  return false;
}

function resolveDistDir(): string {
  if (process.env.CHECKWISE_DIST_DIR) {
    return process.env.CHECKWISE_DIST_DIR;
  }
  if (!pathHasNonAscii(process.cwd())) {
    return ".next";
  }
  // Stable per-project hash so concurrent checkouts do not collide and
  // so CI cache keys remain deterministic.
  const hash = createHash("sha1").update(process.cwd()).digest("hex").slice(0, 10);
  return `.cw-next-${hash}`;
}

const nextConfig: NextConfig = {
  reactStrictMode: true,
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  distDir: resolveDistDir(),
};

export default nextConfig;
