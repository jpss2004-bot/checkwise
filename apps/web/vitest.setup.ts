/**
 * Vitest global setup.
 *
 * Loads @testing-library/jest-dom so component tests can use the
 * extended `expect` matchers (`toBeInTheDocument`, `toHaveTextContent`,
 * `toBeVisible`, etc.) without an import in every test file.
 */
import "@testing-library/jest-dom/vitest";
