// Copy the pdf.js worker + standard fonts from the *installed* pdfjs-dist into
// public/ so they ship as same-origin static assets.
//
// Why this exists:
//   <PdfPreview> renders PDFs to <canvas> via pdfjs-dist. pdf.js runs its
//   parser in a web worker whose file MUST match the API version exactly — a
//   mismatch fails *silently* with a blank canvas (i.e. it would reintroduce
//   the very bug this component fixes). Copying from node_modules on every
//   predev/prebuild makes the worker structurally impossible to drift from the
//   pinned dependency. The files are also committed, so a production build has
//   them even if the lifecycle script is bypassed by the build command.
//
// Run automatically via the `predev` / `prebuild` npm scripts.

import { cpSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = join(here, "..");
const pkgDir = join(webRoot, "node_modules", "pdfjs-dist");
const publicDir = join(webRoot, "public");

const worker = join(pkgDir, "build", "pdf.worker.min.mjs");
const fonts = join(pkgDir, "standard_fonts");
const workerDest = join(publicDir, "pdf.worker.min.mjs");
const fontsDest = join(publicDir, "standard_fonts");

if (!existsSync(pkgDir) || !existsSync(worker)) {
  // No installed copy to read from. If we already vendored the assets, keep
  // them; otherwise this is a hard error (a build without the worker = blank
  // previews in prod).
  if (existsSync(workerDest)) {
    console.warn("[copy-pdf-worker] pdfjs-dist not installed; using vendored worker.");
    process.exit(0);
  }
  console.error("[copy-pdf-worker] pdfjs-dist not found and no vendored worker — run `npm install` first.");
  process.exit(1);
}

const version = JSON.parse(
  readFileSync(join(pkgDir, "package.json"), "utf8"),
).version;

mkdirSync(publicDir, { recursive: true });
cpSync(worker, workerDest);
cpSync(fonts, fontsDest, { recursive: true });

console.log(`[copy-pdf-worker] copied pdfjs-dist@${version} worker + standard_fonts → public/`);
