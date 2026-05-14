import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-geist-sans)", "Geist", "Arial", "sans-serif"],
        mono: ["var(--font-geist-mono)", "Geist Mono", "Courier New", "monospace"],
      },
      colors: {
        // shadcn-compatible aliases (consume the component-token layer)
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },

        // Brand-named (raw primitive aliases) — for icon fills, brand chips
        "brand-navy":  "hsl(var(--brand-navy))",
        "brand-teal":  "hsl(var(--brand-teal))",
        "brand-blue":  "hsl(var(--brand-blue))",
        "brand-slate": "hsl(var(--brand-slate))",
      },
      borderRadius: {
        none:    "0",
        sharp:   "4px",
        sm:      "6px",
        DEFAULT: "8px",
        md:      "10px",
        lg:      "12px",
        xl:      "16px",
        "2xl":   "20px",
        full:    "9999px",
      },
      boxShadow: {
        // Navy-tinted elevation scale (per DESIGN_SYSTEM.md §3.4)
        none: "none",
        xs:   "0 1px 2px rgba(1, 53, 87, 0.06)",
        sm:   "0 2px 8px rgba(1, 53, 87, 0.08), 0 1px 2px rgba(1, 53, 87, 0.04)",
        DEFAULT: "0 2px 8px rgba(1, 53, 87, 0.08), 0 1px 2px rgba(1, 53, 87, 0.04)",
        md:   "0 4px 16px rgba(1, 53, 87, 0.10), 0 2px 4px rgba(1, 53, 87, 0.06)",
        lg:   "0 12px 40px rgba(1, 53, 87, 0.12), 0 4px 12px rgba(1, 53, 87, 0.08)",
        xl:   "0 24px 64px rgba(1, 53, 87, 0.14), 0 8px 20px rgba(1, 53, 87, 0.08)",
        // legacy alias — keep pointing at "sm"
        soft: "0 2px 8px rgba(1, 53, 87, 0.08), 0 1px 2px rgba(1, 53, 87, 0.04)",
      },
      animation: {
        shimmer: "shimmer 1.5s infinite",
      },
      transitionTimingFunction: {
        enter:    "cubic-bezier(0.16, 1, 0.3, 1)",
        exit:     "cubic-bezier(0.4, 0, 1, 1)",
        standard: "cubic-bezier(0.4, 0, 0.2, 1)",
        bounce:   "cubic-bezier(0.34, 1.56, 0.64, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
