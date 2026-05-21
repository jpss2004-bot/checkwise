"use client";

import * as React from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";

import { cn } from "@/lib/utils";

/**
 * Tabs primitive built on Radix.
 *
 * Composition:
 *   <Tabs defaultValue="queue">
 *     <TabsList>
 *       <TabsTrigger value="queue">Cola</TabsTrigger>
 *       <TabsTrigger value="audit">Auditoría</TabsTrigger>
 *     </TabsList>
 *     <TabsContent value="queue">...</TabsContent>
 *     <TabsContent value="audit">...</TabsContent>
 *   </Tabs>
 */

const Tabs = TabsPrimitive.Root;

const TabsList = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.List
    ref={ref}
    className={cn(
      "inline-flex h-10 items-center justify-start gap-1 rounded-md p-1",
      "bg-[color:var(--surface-sunken)] text-[color:var(--text-secondary)]",
      className,
    )}
    {...props}
  />
));
TabsList.displayName = TabsPrimitive.List.displayName;

const TabsTrigger = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      "inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1.5",
      "text-[13px] font-medium transition-colors duration-fast",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40 focus-visible:ring-offset-2 focus-visible:ring-offset-[color:var(--surface-sunken)]",
      "disabled:pointer-events-none disabled:opacity-50",
      "hover:text-[color:var(--text-primary)]",
      "data-[state=active]:bg-[color:var(--surface-raised)] data-[state=active]:text-[color:var(--text-primary)] data-[state=active]:shadow-xs",
      className,
    )}
    {...props}
  />
));
TabsTrigger.displayName = TabsPrimitive.Trigger.displayName;

const TabsContent = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content
    ref={ref}
    className={cn(
      "mt-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40 rounded-sm",
      className,
    )}
    {...props}
  />
));
TabsContent.displayName = TabsPrimitive.Content.displayName;

export { Tabs, TabsList, TabsTrigger, TabsContent };
