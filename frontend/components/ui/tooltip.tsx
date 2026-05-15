"use client";

import * as React from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";

import { cn } from "@/lib/utils";

/**
 * Tooltip primitive built on Radix.
 *
 * Replaces the native `title=""` attribute (slow, OS-styled, untokened)
 * with a floating, accessible tooltip wired into the design tokens.
 * The default open delay favors hover discovery without nagging, while
 * keyboard focus opens immediately per Radix.
 *
 * <TooltipProvider> is mounted once at the app root in app/layout.tsx.
 * Per-call providers are not needed.
 *
 * Usage:
 *   <Tooltip content="Helpful copy">
 *     <button>...</button>
 *   </Tooltip>
 *
 * For richer composition, drop down to the primitives:
 *   <TooltipRoot>
 *     <TooltipTrigger asChild><button>...</button></TooltipTrigger>
 *     <TooltipContent side="top">...</TooltipContent>
 *   </TooltipRoot>
 */

const TooltipProvider = TooltipPrimitive.Provider;

const TooltipRoot = TooltipPrimitive.Root;

const TooltipTrigger = TooltipPrimitive.Trigger;

const TooltipContent = React.forwardRef<
  React.ElementRef<typeof TooltipPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>
>(({ className, sideOffset = 6, children, ...props }, ref) => (
  <TooltipPrimitive.Portal>
    <TooltipPrimitive.Content
      ref={ref}
      sideOffset={sideOffset}
      className={cn(
        "z-50 max-w-xs rounded-sm border px-2.5 py-1.5",
        "border-[color:var(--border-default)] bg-[color:var(--surface-overlay)]",
        "text-[12px] leading-[1.45] text-[color:var(--text-primary)] shadow-md",
        className,
      )}
      {...props}
    >
      {children}
    </TooltipPrimitive.Content>
  </TooltipPrimitive.Portal>
));
TooltipContent.displayName = TooltipPrimitive.Content.displayName;

interface TooltipProps {
  /** Tooltip body. Pass `null` or omit to render the child without a tooltip. */
  content?: React.ReactNode;
  /** The element the tooltip is anchored to. Must accept a ref. */
  children: React.ReactNode;
  /** Open delay in ms. Defaults to Radix's 700ms. */
  delayDuration?: number;
  /** Side of the trigger to render on. */
  side?: React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>["side"];
  /** className on the content. */
  className?: string;
}

/**
 * Convenience wrapper for the common case: one trigger, one short message.
 * For lineage strips, audit metadata, or compound triggers, use the
 * `TooltipRoot`/`TooltipTrigger`/`TooltipContent` primitives directly.
 */
function Tooltip({ content, children, delayDuration, side = "top", className }: TooltipProps) {
  if (content == null || content === "") return <>{children}</>;
  return (
    <TooltipRoot delayDuration={delayDuration}>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side={side} className={className}>
        {content}
      </TooltipContent>
    </TooltipRoot>
  );
}

export {
  Tooltip,
  TooltipRoot,
  TooltipTrigger,
  TooltipContent,
  TooltipProvider,
};
