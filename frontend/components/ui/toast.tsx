"use client";

import * as React from "react";
import { Toaster as SonnerToaster, toast as sonnerToast, type ToasterProps } from "sonner";

/**
 * Toast layer built on Sonner.
 *
 * Mount <Toaster/> once in app/layout.tsx. Trigger from anywhere with the
 * exported `toast` API:
 *
 *   import { toast } from "@/components/ui/toast";
 *   toast.success("Documento aprobado");
 *   toast.error("No fue posible cargar el calendario", { description: "..." });
 *
 * Token wiring is done via Sonner's CSS-variable overrides on `--normal-*`,
 * `--success-*`, `--error-*`, etc. so toasts read in the CheckWise palette
 * regardless of which call site fires them.
 */

const SONNER_THEME_STYLE: React.CSSProperties & Record<string, string> = {
  // Default toast surface
  "--normal-bg": "var(--surface-overlay)",
  "--normal-text": "var(--text-primary)",
  "--normal-border": "var(--border-default)",

  // Success
  "--success-bg": "var(--status-success-bg)",
  "--success-text": "var(--status-success-text)",
  "--success-border": "var(--status-success-border)",

  // Error
  "--error-bg": "var(--status-error-bg)",
  "--error-text": "var(--status-error-text)",
  "--error-border": "var(--status-error-border)",

  // Warning
  "--warning-bg": "var(--status-warning-bg)",
  "--warning-text": "var(--status-warning-text)",
  "--warning-border": "var(--status-warning-border)",

  // Info
  "--info-bg": "var(--status-info-bg)",
  "--info-text": "var(--status-info-text)",
  "--info-border": "var(--status-info-border)",
};

export function Toaster(props: ToasterProps) {
  return (
    <SonnerToaster
      theme="light"
      richColors
      closeButton
      position="top-right"
      style={SONNER_THEME_STYLE}
      toastOptions={{
        classNames: {
          toast: "rounded-md shadow-md",
          title: "text-sm font-medium",
          description: "text-[12px] leading-[1.45]",
        },
      }}
      {...props}
    />
  );
}

export const toast = sonnerToast;
export type { ToasterProps };
