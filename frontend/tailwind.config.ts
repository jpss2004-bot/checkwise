import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

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
        display: ["'Open Sans'", "var(--font-geist-sans)", "Geist", "Arial", "sans-serif"],
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

        // Semantic status aliases for component variants and future primitives
        success: {
          DEFAULT: "hsl(var(--status-success-text))",
          bg: "hsl(var(--status-success-bg))",
          border: "hsl(var(--status-success-border))",
        },
        warning: {
          DEFAULT: "hsl(var(--status-warning-text))",
          bg: "hsl(var(--status-warning-bg))",
          border: "hsl(var(--status-warning-border))",
        },
        error: {
          DEFAULT: "hsl(var(--status-error-text))",
          bg: "hsl(var(--status-error-bg))",
          border: "hsl(var(--status-error-border))",
        },
        info: {
          DEFAULT: "hsl(var(--status-info-text))",
          bg: "hsl(var(--status-info-bg))",
          border: "hsl(var(--status-info-border))",
        },
        ai: {
          DEFAULT: "hsl(var(--status-ai-text))",
          bg: "hsl(var(--status-ai-bg))",
          border: "hsl(var(--status-ai-border))",
        },
      },
      borderRadius: {
        none:    "0",
        sharp:   "var(--radius-sharp)",
        sm:      "var(--radius-sm)",
        DEFAULT: "var(--radius)",
        md:      "var(--radius-md)",
        lg:      "var(--radius-lg)",
        xl:      "var(--radius-xl)",
        "2xl":   "var(--radius-2xl)",
        full:    "var(--radius-pill)",
      },
      boxShadow: {
        // Navy-tinted elevation scale (per DESIGN_SYSTEM.md §3.4)
        none: "none",
        xs:   "var(--shadow-xs)",
        sm:   "var(--shadow-sm)",
        DEFAULT: "var(--shadow-sm)",
        md:   "var(--shadow-md)",
        lg:   "var(--shadow-lg)",
        xl:   "var(--shadow-xl)",
        // legacy alias — keep pointing at "sm"
        soft: "var(--shadow-sm)",
        focus: "var(--shadow-focus)",
        "focus-ai": "var(--shadow-focus-ai)",
        "focus-error": "var(--shadow-focus-error)",
      },
      fontSize: {
        display: ["36px", { lineHeight: "1", letterSpacing: "-0.025em" }],
        "display-sm": ["28px", { lineHeight: "1.1", letterSpacing: "-0.02em" }],
        h1: ["22px", { lineHeight: "1.2", letterSpacing: "-0.015em" }],
        h2: ["18px", { lineHeight: "1.25", letterSpacing: "-0.01em" }],
        h3: ["15px", { lineHeight: "1.3", letterSpacing: "0" }],
        h4: ["13px", { lineHeight: "1.4", letterSpacing: "0.04em" }],
        body: ["14px", { lineHeight: "1.6" }],
        "body-sm": ["13px", { lineHeight: "1.6" }],
        "body-xs": ["12px", { lineHeight: "1.5" }],
        label: ["13px", { lineHeight: "1.4" }],
        helper: ["12px", { lineHeight: "1.5" }],
        caption: ["11px", { lineHeight: "1.5", letterSpacing: "0.04em" }],
        mono: ["13px", { lineHeight: "1.5" }],
      },
      animation: {
        shimmer: "shimmer 1.5s infinite",
      },
      transitionDuration: {
        instant: "80ms",
        fast: "150ms",
        standard: "250ms",
        slow: "350ms",
        deliberate: "560ms",
      },
      transitionTimingFunction: {
        enter:    "cubic-bezier(0.16, 1, 0.3, 1)",
        exit:     "cubic-bezier(0.4, 0, 1, 1)",
        standard: "cubic-bezier(0.4, 0, 0.2, 1)",
        bounce:   "cubic-bezier(0.34, 1.56, 0.64, 1)",
      },
    },
  },
  plugins: [animate],
};

export default config;
