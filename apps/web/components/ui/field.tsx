import * as React from "react";

import { cn } from "@/lib/utils";
import { Label } from "./label";

interface FieldProps {
  /** Visible field label. */
  label: string;
  /** Stable id; passed to the input + linked to label/helper/error. */
  htmlFor: string;
  /** Mark as required (renders an asterisk + sets aria-required on the input). */
  required?: boolean;
  /** Helper text shown beneath the input when no error is present. */
  helper?: React.ReactNode;
  /** Error message. Replaces helper and adds aria-invalid to the input. */
  error?: string | null;
  /** Optional right-aligned content next to the label (e.g. character count). */
  trailing?: React.ReactNode;
  /** The input/textarea/select element. */
  children: React.ReactNode;
  className?: string;
}

/**
 * Composed form field: Label + control + helper text + error.
 *
 * The child is responsible for rendering the actual input. This
 * component handles the label, the helper/error toggle, and the
 * accessibility wiring through aria-describedby on the child.
 *
 * Spec: docs/DESIGN_SYSTEM.md §6.4
 */
export function Field({
  label,
  htmlFor,
  required = false,
  helper,
  error,
  trailing,
  children,
  className,
}: FieldProps) {
  const helperId = `${htmlFor}-helper`;
  const errorId = `${htmlFor}-error`;

  // Inject aria-describedby + aria-invalid + required onto the child input.
  const enhancedChild = React.isValidElement(children)
    ? React.cloneElement(children as React.ReactElement<Record<string, unknown>>, {
        id: htmlFor,
        "aria-describedby": error ? errorId : helper ? helperId : undefined,
        "aria-invalid": error ? true : undefined,
        "aria-required": required || undefined,
        required: required || undefined,
      })
    : children;

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <div className="flex items-baseline justify-between gap-3">
        <Label htmlFor={htmlFor} className="flex items-center gap-1">
          <span>{label}</span>
          {required && (
            <span aria-hidden="true" className="text-[color:var(--status-error-text)]">
              *
            </span>
          )}
        </Label>
        {trailing && (
          <span className="text-xs text-[color:var(--text-tertiary)]">{trailing}</span>
        )}
      </div>
      {enhancedChild}
      {error ? (
        <p
          id={errorId}
          role="alert"
          className="flex items-start gap-1.5 text-xs leading-5 text-[color:var(--status-error-text)]"
        >
          <ErrorIcon />
          <span>{error}</span>
        </p>
      ) : helper ? (
        <p id={helperId} className="text-xs leading-5 text-[color:var(--text-tertiary)]">
          {helper}
        </p>
      ) : null}
    </div>
  );
}

function ErrorIcon() {
  // Inline SVG to avoid a Phosphor import in a primitive.
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      width="14"
      height="14"
      className="mt-0.5 shrink-0 fill-current"
    >
      <path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1Zm-.75 4h1.5v5h-1.5V5Zm.75 7.25a.95.95 0 1 1 0-1.9.95.95 0 0 1 0 1.9Z" />
    </svg>
  );
}
