import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { CheckCircle, Info, WarningCircle, Warning } from "@phosphor-icons/react";

import { cn } from "@/lib/utils";

const alertVariants = cva(
  "relative flex w-full items-start gap-3 rounded-lg border p-4 text-sm",
  {
    variants: {
      variant: {
        info:
          "border-[color:var(--status-info-border)] bg-[color:var(--status-info-bg)] text-[color:var(--status-info-text)]",
        success:
          "border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)] text-[color:var(--status-success-text)]",
        warning:
          "border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] text-[color:var(--status-warning-text)]",
        error:
          "border-[color:var(--status-error-border)] bg-[color:var(--status-error-bg)] text-[color:var(--status-error-text)]",
      },
    },
    defaultVariants: {
      variant: "info",
    },
  },
);

const VARIANT_ICON = {
  info: Info,
  success: CheckCircle,
  warning: Warning,
  error: WarningCircle,
} as const;

export interface AlertProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof alertVariants> {
  /** Override the default icon for this variant. Pass `null` to render none. */
  icon?: React.ReactNode | null;
}

/**
 * Page-level alert banner. Used for recoverable errors, info notices,
 * and non-blocking success confirmations.
 *
 * Spec: docs/DESIGN_SYSTEM.md §6.8
 */
export function Alert({
  className,
  variant = "info",
  icon,
  children,
  role,
  ...props
}: AlertProps) {
  const DefaultIcon = VARIANT_ICON[variant ?? "info"];
  const resolvedIcon =
    icon === null ? null : icon ?? (
      <DefaultIcon className="mt-0.5 h-4 w-4 shrink-0" weight="fill" aria-hidden="true" />
    );

  return (
    <div
      role={role ?? (variant === "error" || variant === "warning" ? "alert" : "status")}
      className={cn(alertVariants({ variant }), className)}
      {...props}
    >
      {resolvedIcon}
      <div className="flex min-w-0 flex-1 flex-col gap-1">{children}</div>
    </div>
  );
}

export function AlertTitle({
  className,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-sm font-semibold leading-5", className)} {...props} />;
}

export function AlertDescription({
  className,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      className={cn(
        "text-[13px] leading-5 text-[color:inherit] opacity-90",
        className,
      )}
      {...props}
    />
  );
}
