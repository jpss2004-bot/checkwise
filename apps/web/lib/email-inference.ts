/**
 * Email-based name + company inference helpers.
 *
 * Used by the account activation flow to pre-fill the identity form
 * from the temporary-credentials email. The inferences are always
 * presented to the user as **suggestions** they can override —
 * never blindly trusted.
 *
 * Spec: task §3 (Account Activation Form — Automation logic).
 */

const GENERIC_DOMAINS = new Set([
  "gmail.com",
  "googlemail.com",
  "outlook.com",
  "hotmail.com",
  "live.com",
  "msn.com",
  "icloud.com",
  "me.com",
  "mac.com",
  "yahoo.com",
  "yahoo.com.mx",
  "ymail.com",
  "rocketmail.com",
  "aol.com",
  "protonmail.com",
  "proton.me",
  "zoho.com",
  "gmx.com",
  "yandex.com",
  "tutanota.com",
  "fastmail.com",
]);

export interface EmailInference {
  /** Suggested first name (or empty if uninferable). */
  first_name: string;
  /** Suggested last name (or empty if uninferable). */
  last_name: string;
  /** Suggested company name (or empty if domain is generic). */
  company: string;
  /** Whether the domain is in the generic list (gmail/outlook/etc). */
  is_generic_domain: boolean;
}

const NAME_SEPARATORS = /[._\-+]/g;

function titleCase(word: string): string {
  if (!word) return "";
  // Drop trailing digits ("juan123" → "juan")
  const cleaned = word.replace(/\d+$/g, "");
  if (!cleaned) return "";
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1).toLowerCase();
}

function inferNameFromLocalPart(local: string): { first: string; last: string } {
  const tokens = local
    .split(NAME_SEPARATORS)
    .map(titleCase)
    .filter(Boolean);

  if (tokens.length === 0) return { first: "", last: "" };
  if (tokens.length === 1) return { first: tokens[0], last: "" };
  // First token = first name; everything else joined as "last name"
  return { first: tokens[0], last: tokens.slice(1).join(" ") };
}

function inferCompanyFromDomain(domain: string): string {
  // "constructoraabc.com.mx" → "constructoraabc"
  // "checkwise.legalshelf.com" → "checkwise legalshelf"
  // Drop the public TLD and known second-level country suffixes.
  // "gob" is the Mexican government second-level label (.gob.mx) — the
  // product's market — so it must be dropped like "gov" or an email such
  // as contacto@empresa.gob.mx would infer "Empresa Gob" instead of "Empresa".
  const COUNTRY_TLD = new Set([
    "com",
    "co",
    "ne",
    "or",
    "ed",
    "ac",
    "gov",
    "gob",
  ]);
  const parts = domain.toLowerCase().split(".");
  if (parts.length < 2) return "";

  // Walk from the right: drop TLD, then drop country-2LD if it looks like one.
  const popped: string[] = [];
  popped.push(parts.pop() as string); // tld
  if (parts.length > 1 && COUNTRY_TLD.has(parts[parts.length - 1])) {
    popped.push(parts.pop() as string);
  }

  // Remaining parts (excluding "www") become the company name.
  const meaningful = parts.filter((p) => p && p !== "www");
  if (meaningful.length === 0) return "";

  return meaningful
    .map((p) => titleCase(p.replace(/-/g, " ")))
    .join(" ")
    .trim();
}

/**
 * Infer (first_name, last_name, company) from an email.
 *
 * Examples:
 *   juan.perez@constructoraabc.com → { first: "Juan", last: "Perez", company: "Constructoraabc" }
 *   juan.perez@gmail.com → { first: "Juan", last: "Perez", company: "", is_generic_domain: true }
 *   foo@bar → { first: "Foo", last: "", company: "" }
 */
export function inferFromEmail(email: string): EmailInference {
  const trimmed = email.trim().toLowerCase();
  const atIdx = trimmed.indexOf("@");
  if (atIdx === -1) {
    return { first_name: "", last_name: "", company: "", is_generic_domain: false };
  }
  const local = trimmed.slice(0, atIdx);
  const domain = trimmed.slice(atIdx + 1);

  const { first, last } = inferNameFromLocalPart(local);
  const is_generic_domain = GENERIC_DOMAINS.has(domain);
  const company = is_generic_domain ? "" : inferCompanyFromDomain(domain);

  return { first_name: first, last_name: last, company, is_generic_domain };
}

/**
 * Validate a password against the design system's rules.
 *
 * Rules:
 *   - At least 12 characters
 *   - At least one uppercase letter
 *   - At least one lowercase letter
 *   - At least one number
 *
 * Returns a list of failed rule labels (empty list = valid).
 */
export interface PasswordRule {
  label: string;
  test: (value: string) => boolean;
}

export const PASSWORD_RULES: PasswordRule[] = [
  { label: "Mínimo 12 caracteres", test: (v) => v.length >= 12 },
  { label: "Una letra mayúscula", test: (v) => /[A-Z]/.test(v) },
  { label: "Una letra minúscula", test: (v) => /[a-z]/.test(v) },
  { label: "Al menos un número", test: (v) => /\d/.test(v) },
];

export function evaluatePassword(value: string): { rule: PasswordRule; passed: boolean }[] {
  return PASSWORD_RULES.map((rule) => ({ rule, passed: rule.test(value) }));
}
