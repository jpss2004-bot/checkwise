import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

const eslintConfig = [
  {
    ignores: [
      ".next/**",
      ".cw-next-*/**",
      "node_modules/**",
      "out/**",
      "dist/**",
      "next-env.d.ts",
      // Static + vendored assets are not source to lint. The vendored,
      // minified pdf.js worker (copied into public/ by copy-pdf-worker.mjs)
      // was producing 7 no-this-alias errors that reddened CI for no signal.
      "public/**",
      "tmp/**",
    ],
  },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
];

export default eslintConfig;
