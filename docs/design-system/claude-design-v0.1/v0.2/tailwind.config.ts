/**
 * CheckWise · Design System v0.2 · Phase 1
 * Tailwind config bridge
 *
 * This file shows the `theme.extend` block to merge into the existing
 * `frontend/tailwind.config.ts`. Keep your `content` array, `darkMode`,
 * and any plugins you've added — only replace the `extend` object.
 */

import type { Config } from "tailwindcss";

const config: Partial<Config> = {
  // ─── KEEP YOUR EXISTING `content` ARRAY ────────────────────────────────
  // content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", ...],

  theme: {
    extend: {
      // ─── Colors — consume semantic tokens, never primitives directly ─
      colors: {
        // shadcn back-compat names
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
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },

        // Brand primitives — available to foundation/token code only.
        // Components must NOT reference these directly; use semantic tokens.
        navy: {
          50:  "hsl(var(--navy-50))",
          100: "hsl(var(--navy-100))",
          200: "hsl(var(--navy-200))",
          300: "hsl(var(--navy-300))",
          400: "hsl(var(--navy-400))",
          500: "hsl(var(--navy-500))",
          600: "hsl(var(--navy-600))",
          700: "hsl(var(--navy-700))",
          800: "hsl(var(--navy-800))",   // brand primary
          900: "hsl(var(--navy-900))",
          950: "hsl(var(--navy-950))",
        },
        teal: {
          // TEAL IS RESERVED FOR AI / INTELLIGENCE STATES. Do not paint
          // chrome, dividers, or generic icons with teal — see globals.css.
          50:  "hsl(var(--teal-50))",
          100: "hsl(var(--teal-100))",
          200: "hsl(var(--teal-200))",
          300: "hsl(var(--teal-300))",
          400: "hsl(var(--teal-400))",
          500: "hsl(var(--teal-500))",   // brand teal
          600: "hsl(var(--teal-600))",
          700: "hsl(var(--teal-700))",
          800: "hsl(var(--teal-800))",
          900: "hsl(var(--teal-900))",
        },

        // Semantic status — used inside Badge/Alert/StatusPill primitives.
        success: {
          DEFAULT: "hsl(var(--status-success-text))",
          bg:      "hsl(var(--status-success-bg))",
          border:  "hsl(var(--status-success-border))",
        },
        warning: {
          DEFAULT: "hsl(var(--status-warning-text))",
          bg:      "hsl(var(--status-warning-bg))",
          border:  "hsl(var(--status-warning-border))",
        },
        error: {
          DEFAULT: "hsl(var(--status-error-text))",
          bg:      "hsl(var(--status-error-bg))",
          border:  "hsl(var(--status-error-border))",
        },
        info: {
          DEFAULT: "hsl(var(--status-info-text))",
          bg:      "hsl(var(--status-info-bg))",
          border:  "hsl(var(--status-info-border))",
        },
        ai: {
          DEFAULT: "hsl(var(--status-ai-text))",
          bg:      "hsl(var(--status-ai-bg))",
          border:  "hsl(var(--status-ai-border))",
        },
      },

      // ─── Border radius ──────────────────────────────────────────────
      borderRadius: {
        sharp:  "var(--radius-sharp)",
        sm:     "var(--radius-sm)",
        DEFAULT:"var(--radius)",
        md:     "var(--radius-md)",
        lg:     "var(--radius-lg)",
        xl:     "var(--radius-xl)",
        "2xl":  "var(--radius-2xl)",
      },

      // ─── Box shadow (tinted toward navy) ────────────────────────────
      boxShadow: {
        none: "none",
        xs:   "var(--shadow-xs)",
        sm:   "var(--shadow-sm)",
        DEFAULT: "var(--shadow-sm)",
        md:   "var(--shadow-md)",
        lg:   "var(--shadow-lg)",
        xl:   "var(--shadow-xl)",
        soft: "var(--shadow-sm)",   // legacy alias
        "focus":       "var(--shadow-focus)",
        "focus-ai":    "var(--shadow-focus-ai)",
        "focus-error": "var(--shadow-focus-error)",
      },

      // ─── Fonts ──────────────────────────────────────────────────────
      fontFamily: {
        sans: ["var(--font-geist-sans)", "Arial", "sans-serif"],
        mono: ["var(--font-geist-mono)", "SF Mono", "Menlo", "monospace"],
        // Open Sans available for marketing-only / PDF report templates.
        display: ["'Open Sans'", "var(--font-geist-sans)", "sans-serif"],
      },

      // ─── Font size scale (10-step) ──────────────────────────────────
      fontSize: {
        // [size, { lineHeight, letterSpacing, fontWeight? }]
        "display":    ["36px", { lineHeight: "1.0",  letterSpacing: "-0.025em" }],
        "display-sm": ["28px", { lineHeight: "1.1",  letterSpacing: "-0.02em"  }],
        "h1":         ["22px", { lineHeight: "1.2",  letterSpacing: "-0.015em" }],
        "h2":         ["18px", { lineHeight: "1.25", letterSpacing: "-0.01em"  }],
        "h3":         ["15px", { lineHeight: "1.3",  letterSpacing: "0"        }],
        "h4":         ["13px", { lineHeight: "1.4",  letterSpacing: "0.04em"   }],
        "body":       ["14px", { lineHeight: "1.6" }],
        "body-sm":    ["13px", { lineHeight: "1.6" }],
        "body-xs":    ["12px", { lineHeight: "1.5" }],
        "label":      ["13px", { lineHeight: "1.4" }],
        "helper":     ["12px", { lineHeight: "1.5" }],
        "caption":    ["11px", { lineHeight: "1.5", letterSpacing: "0.04em" }],
        "mono":       ["13px", { lineHeight: "1.5" }],
      },

      // ─── Animation / motion ─────────────────────────────────────────
      transitionDuration: {
        instant:     "80ms",
        fast:       "150ms",
        standard:   "250ms",
        slow:       "350ms",
        deliberate: "560ms",
      },

      transitionTimingFunction: {
        enter:    "cubic-bezier(0.16, 1, 0.3, 1)",
        exit:     "cubic-bezier(0.4, 0, 1, 1)",
        standard: "cubic-bezier(0.4, 0, 0.2, 1)",
        bounce:   "cubic-bezier(0.34, 1.56, 0.64, 1)",
      },

      keyframes: {
        shimmer: {
          "0%":   { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)"  },
        },
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to:   { opacity: "1", transform: "translateY(0)" },
        },
      },

      animation: {
        shimmer:    "shimmer 1.5s ease-in-out infinite",
        "fade-in":  "fade-in 250ms cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },

  // ─── KEEP YOUR EXISTING `plugins` ARRAY ────────────────────────────
  // plugins: [require("tailwindcss-animate"), ...],
};

export default config;
