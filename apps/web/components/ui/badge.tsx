import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

/**
 * Badge variants are wired to semantic token CSS variables (not raw
 * Tailwind palette colors) so the design system can re-skin status
 * surfaces from one place. See docs/DESIGN_SYSTEM.md §3.1.
 */
const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-medium leading-5",
  {
    variants: {
      variant: {
        default:
          "border-[color:var(--border-brand)] bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]",
        secondary:
          "border-[color:var(--border-default)] bg-[color:var(--surface-sunken)] text-[color:var(--text-primary)]",
        outline:
          "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-secondary)]",
        brand:
          "border-[color:var(--border-default)] bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)]",
        teal:
          "border-transparent bg-[color:var(--surface-teal-muted)] text-[color:var(--text-teal)]",

        // Status
        success:
          "border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)] text-[color:var(--status-success-text)]",
        warning:
          "border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] text-[color:var(--status-warning-text)]",
        destructive:
          "border-[color:var(--status-error-border)] bg-[color:var(--status-error-bg)] text-[color:var(--status-error-text)]",
        info:
          "border-[color:var(--status-info-border)] bg-[color:var(--status-info-bg)] text-[color:var(--status-info-text)]",

        // REPSE document states
        "doc-pending":
          "border-[color:var(--doc-pending-border)] bg-[color:var(--doc-pending-bg)] text-[color:var(--doc-pending-text)]",
        "doc-uploaded":
          "border-[color:var(--doc-uploaded-border)] bg-[color:var(--doc-uploaded-bg)] text-[color:var(--doc-uploaded-text)]",
        "doc-in-review":
          "border-[color:var(--doc-in-review-border)] bg-[color:var(--doc-in-review-bg)] text-[color:var(--doc-in-review-text)]",
        "doc-approved":
          "border-[color:var(--doc-approved-border)] bg-[color:var(--doc-approved-bg)] text-[color:var(--doc-approved-text)]",
        "doc-rejected":
          "border-[color:var(--doc-rejected-border)] bg-[color:var(--doc-rejected-bg)] text-[color:var(--doc-rejected-text)]",
        "doc-expired":
          "border-[color:var(--doc-expired-border)] bg-[color:var(--doc-expired-bg)] text-[color:var(--doc-expired-text)]",
        "doc-needs-review":
          "border-[color:var(--doc-needs-review-border)] bg-[color:var(--doc-needs-review-bg)] text-[color:var(--doc-needs-review-text)]",
        "doc-empty":
          "border-[color:var(--doc-empty-border)] bg-[color:var(--doc-empty-bg)] text-[color:var(--doc-empty-text)]",

        // AI/OCR confidence
        "confidence-high":
          "border-[color:var(--confidence-high-border)] bg-[color:var(--confidence-high-bg)] text-[color:var(--confidence-high-text)]",
        "confidence-medium":
          "border-[color:var(--confidence-medium-border)] bg-[color:var(--confidence-medium-bg)] text-[color:var(--confidence-medium-text)]",
        "confidence-low":
          "border-[color:var(--confidence-low-border)] bg-[color:var(--confidence-low-bg)] text-[color:var(--confidence-low-text)]",
        "confidence-none":
          "border-[color:var(--confidence-none-border)] bg-[color:var(--confidence-none-bg)] text-[color:var(--confidence-none-text)]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
