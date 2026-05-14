"use client";

import { type ComponentType, type ReactNode } from "react";
import {
  Warning,
  ArrowRight,
  FileMagnifyingGlass,
  Tray,
  ArrowsClockwise,
  WifiSlash,
} from "@phosphor-icons/react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Skeleton primitives
//
// Shared placeholders the portal uses while data is in flight. Per the design
// rule the goal is to mirror the layout the user is about to see — never a
// generic spinner — so the page does not visibly jump on resolve.
// ---------------------------------------------------------------------------

type SkeletonProps = {
  className?: string;
  ariaHidden?: boolean;
};

export function Skeleton({ className, ariaHidden = true }: SkeletonProps) {
  return (
    <div
      aria-hidden={ariaHidden}
      className={cn("animate-pulse rounded-md bg-muted/70", className)}
    />
  );
}

type SkeletonLineProps = {
  width?: "full" | "11/12" | "10/12" | "9/12" | "8/12" | "7/12" | "6/12" | "5/12" | "4/12" | "3/12" | "2/12";
  height?: "sm" | "md" | "lg";
  className?: string;
};

const LINE_WIDTH_CLASS: Record<NonNullable<SkeletonLineProps["width"]>, string> = {
  full: "w-full",
  "11/12": "w-11/12",
  "10/12": "w-10/12",
  "9/12": "w-9/12",
  "8/12": "w-8/12",
  "7/12": "w-7/12",
  "6/12": "w-6/12",
  "5/12": "w-5/12",
  "4/12": "w-4/12",
  "3/12": "w-3/12",
  "2/12": "w-2/12",
};

const LINE_HEIGHT_CLASS: Record<NonNullable<SkeletonLineProps["height"]>, string> = {
  sm: "h-3",
  md: "h-4",
  lg: "h-5",
};

export function SkeletonLine({
  width = "full",
  height = "md",
  className,
}: SkeletonLineProps) {
  return (
    <Skeleton
      className={cn(LINE_WIDTH_CLASS[width], LINE_HEIGHT_CLASS[height], className)}
    />
  );
}

// ---------------------------------------------------------------------------
// Empty state
//
// Used when a payload arrived successfully but has nothing to show — e.g. an
// onboarding checklist with no items, or a calendar month with no recurring
// obligations. Always shows what populates the list and (optionally) the
// action that will help.
// ---------------------------------------------------------------------------

type EmptyStateProps = {
  icon?: ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
  variant?: "default" | "muted";
};

export function EmptyState({
  icon: Icon = Tray,
  title,
  description,
  action,
  className,
  variant = "default",
}: EmptyStateProps) {
  const tone =
    variant === "muted"
      ? "border-border bg-muted/30"
      : "border-border bg-white";
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-md border px-6 py-10 text-center",
        tone,
        className,
      )}
    >
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <Icon className="h-5 w-5" aria-hidden />
      </div>
      <div className="max-w-md space-y-1">
        <p className="text-sm font-semibold">{title}</p>
        {description ? (
          <p className="text-sm text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {action ? <div className="mt-1">{action}</div> : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Error state
//
// Surfaced when a fetch fails. Always shows a retry path so the provider is
// not stuck — calmer than a red banner because we have not lost any of their
// work, only the read.
// ---------------------------------------------------------------------------

type ErrorStateProps = {
  title?: string;
  description?: string;
  onRetry?: () => void;
  retryLabel?: string;
  secondary?: ReactNode;
  className?: string;
  variant?: "network" | "default";
};

export function ErrorState({
  title = "No pudimos cargar esta sección",
  description = "Revisa tu conexión y vuelve a intentarlo. Si el problema persiste, escríbenos.",
  onRetry,
  retryLabel = "Reintentar",
  secondary,
  className,
  variant = "default",
}: ErrorStateProps) {
  const Icon = variant === "network" ? WifiSlash : Warning;
  return (
    <div
      role="alert"
      className={cn(
        "rounded-md border border-amber-300 bg-amber-50 p-5",
        className,
      )}
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-amber-500 text-white">
            <Icon className="h-4 w-4" aria-hidden />
          </div>
          <div className="min-w-0 space-y-1">
            <p className="text-sm font-semibold text-amber-900">{title}</p>
            <p className="text-sm text-amber-900/80">{description}</p>
          </div>
        </div>
        {onRetry || secondary ? (
          <div className="flex flex-wrap items-center gap-2 self-start sm:self-auto">
            {secondary}
            {onRetry ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={onRetry}
                className="active:scale-[0.98]"
              >
                <ArrowsClockwise className="h-4 w-4" aria-hidden />
                {retryLabel}
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Not-found
//
// A page-level variant used when the resource itself does not exist (e.g. an
// invalid submission id). Keeps the layout calm and offers the obvious next
// move back to the calendar.
// ---------------------------------------------------------------------------

type NotFoundStateProps = {
  title?: string;
  description?: string;
  action?: ReactNode;
};

export function NotFoundState({
  title = "No encontramos lo que buscas",
  description = "El enlace puede haber expirado o el documento ya no pertenece a tu expediente.",
  action,
}: NotFoundStateProps) {
  return (
    <EmptyState
      icon={FileMagnifyingGlass}
      title={title}
      description={description}
      action={action}
      variant="muted"
    />
  );
}

// ---------------------------------------------------------------------------
// Page-specific skeleton compositions
// ---------------------------------------------------------------------------

export function DashboardSkeleton() {
  return (
    <div className="space-y-5" aria-busy="true" aria-live="polite">
      <span className="sr-only">Cargando calendario…</span>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="rounded-md border border-border bg-white p-4">
            <Skeleton className="h-3 w-5/12" />
            <Skeleton className="mt-3 h-7 w-2/12" />
            <Skeleton className="mt-2 h-3 w-7/12" />
          </div>
        ))}
      </div>
      <div className="rounded-md border border-border bg-white p-4">
        <Skeleton className="h-4 w-3/12" />
        <Skeleton className="mt-2 h-3 w-8/12" />
        <div className="mt-4 flex flex-wrap gap-2">
          {Array.from({ length: 12 }).map((_, i) => (
            <Skeleton key={i} className="h-7 w-16" />
          ))}
        </div>
        <div className="mt-5 space-y-3">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="rounded-md border border-border/70 p-3">
              <Skeleton className="h-4 w-4/12" />
              <div className="mt-3 space-y-2">
                {Array.from({ length: 3 }).map((__, j) => (
                  <div key={j} className="flex items-center justify-between gap-3">
                    <div className="flex-1 space-y-1">
                      <Skeleton className="h-3 w-6/12" />
                      <Skeleton className="h-3 w-4/12" />
                    </div>
                    <Skeleton className="h-7 w-20" />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function OnboardingSkeleton() {
  return (
    <div className="rounded-md border border-border bg-white p-5" aria-busy="true" aria-live="polite">
      <span className="sr-only">Cargando expediente corporativo…</span>
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-2">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-3 w-80" />
        </div>
        <Skeleton className="h-6 w-36" />
      </div>
      <Skeleton className="mt-4 h-2 w-full" />
      <div className="mt-6 space-y-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="rounded-md border border-border/70 p-3">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="mt-2 h-1.5 w-full" />
            <div className="mt-3 space-y-2">
              {Array.from({ length: 2 }).map((__, j) => (
                <div key={j} className="flex items-center justify-between gap-3">
                  <div className="flex-1 space-y-1">
                    <Skeleton className="h-3 w-7/12" />
                    <Skeleton className="h-3 w-4/12" />
                  </div>
                  <Skeleton className="h-7 w-20" />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function SubmissionDetailSkeleton() {
  return (
    <div className="grid gap-5 lg:grid-cols-3" aria-busy="true" aria-live="polite">
      <span className="sr-only">Cargando documento…</span>
      <div className="space-y-5 lg:col-span-2">
        <div className="rounded-md border border-border bg-white p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <Skeleton className="h-10 w-10 rounded-full" />
              <div className="space-y-2">
                <Skeleton className="h-5 w-20" />
                <Skeleton className="h-4 w-64" />
                <Skeleton className="h-3 w-48" />
              </div>
            </div>
            <Skeleton className="h-9 w-40" />
          </div>
        </div>
        <div className="rounded-md border border-border bg-white p-5 space-y-3">
          <Skeleton className="h-4 w-3/12" />
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="rounded-md border border-border/70 p-3 space-y-2">
              <Skeleton className="h-4 w-5/12" />
              <Skeleton className="h-3 w-9/12" />
            </div>
          ))}
        </div>
        <div className="rounded-md border border-border bg-white p-5">
          <Skeleton className="h-4 w-3/12" />
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="rounded-md border border-border/70 p-3 space-y-2">
                <Skeleton className="h-3 w-4/12" />
                <Skeleton className="h-4 w-7/12" />
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="space-y-5">
        <div className="rounded-md border border-border bg-white p-5 space-y-3">
          <Skeleton className="h-4 w-5/12" />
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="flex items-start gap-3">
              <Skeleton className="h-2.5 w-2.5 rounded-full" />
              <div className="flex-1 space-y-1">
                <Skeleton className="h-3 w-7/12" />
                <Skeleton className="h-3 w-4/12" />
              </div>
            </div>
          ))}
        </div>
        <div className="rounded-md border border-border bg-white p-5 space-y-2">
          <Skeleton className="h-4 w-5/12" />
          <Skeleton className="h-3 w-9/12" />
          <Skeleton className="h-3 w-8/12" />
        </div>
      </div>
    </div>
  );
}

export function UploadWizardSkeleton() {
  return (
    <div className="rounded-md border border-border bg-white p-5" aria-busy="true" aria-live="polite">
      <span className="sr-only">Preparando el formulario…</span>
      <div className="flex flex-wrap items-center gap-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-7 w-24" />
        ))}
      </div>
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="space-y-2">
            <Skeleton className="h-3 w-3/12" />
            <Skeleton className="h-10 w-full" />
          </div>
        ))}
      </div>
      <Skeleton className="mt-6 h-9 w-32" />
    </div>
  );
}

// Inline retry chip — useful when the embedded component already owns its
// own loading state and we want to keep the layout intact while signalling
// the failure.
type InlineRetryProps = {
  message: string;
  onRetry: () => void;
  className?: string;
};

export function InlineRetry({ message, onRetry, className }: InlineRetryProps) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-wrap items-center justify-between gap-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm",
        className,
      )}
    >
      <div className="flex items-center gap-2 text-amber-900">
        <Warning className="h-4 w-4" aria-hidden />
        <span>{message}</span>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="inline-flex items-center gap-1 rounded-md border border-amber-300 bg-white px-2 py-1 text-xs font-medium text-amber-900 transition-transform hover:bg-amber-100 active:scale-[0.98]"
      >
        Reintentar
        <ArrowRight className="h-3.5 w-3.5" aria-hidden />
      </button>
    </div>
  );
}
