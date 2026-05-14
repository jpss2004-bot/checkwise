import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";
import { Spinner } from "./spinner";

const buttonVariants = cva(
  [
    "inline-flex items-center justify-center gap-2 rounded font-medium",
    "transition-[background-color,box-shadow,transform] duration-fast",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40 focus-visible:ring-offset-2 focus-visible:ring-offset-[color:var(--surface-page)]",
    "disabled:pointer-events-none disabled:opacity-50",
  ].join(" "),
  {
    variants: {
      variant: {
        default:
          "bg-[color:var(--interactive-primary)] text-[color:var(--text-inverse)] hover:bg-[color:var(--interactive-primary-hover)] active:bg-[color:var(--interactive-primary-active)] shadow-xs",
        secondary:
          "bg-[color:var(--interactive-secondary)] text-[color:var(--text-inverse)] hover:bg-[color:var(--interactive-secondary-hover)] shadow-xs",
        outline:
          "border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-primary)] hover:bg-[color:var(--surface-hover)] hover:border-[color:var(--border-strong)]",
        ghost:
          "text-[color:var(--text-primary)] hover:bg-[color:var(--interactive-ghost-hover)]",
        destructive:
          "bg-[color:var(--interactive-destructive)] text-[color:var(--text-inverse)] hover:bg-[color:var(--interactive-destructive)]/90 shadow-xs",
        link:
          "text-[color:var(--text-link)] underline-offset-4 hover:underline px-0 h-auto",
      },
      size: {
        sm: "h-8 px-3 text-[13px]",
        default: "h-10 px-4 text-sm",
        lg: "h-12 px-6 text-[15px]",
        icon: "h-10 w-10 p-0",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  /** Show a spinner and disable the button. Children stay rendered. */
  loading?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant,
      size,
      asChild = false,
      loading = false,
      disabled,
      children,
      ...props
    },
    ref,
  ) => {
    const Comp = asChild ? Slot : "button";
    // Slot requires a single child, so when asChild is true we pass
    // `children` directly without injecting the loading spinner. The
    // `loading` prop is only meaningful for native button usage.
    const content =
      asChild || !loading ? (
        children
      ) : (
        <>
          <Spinner className="text-current" label={null} />
          {children}
        </>
      );
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        aria-busy={!asChild && loading ? true : undefined}
        disabled={!asChild && (disabled || loading)}
        {...props}
      >
        {content}
      </Comp>
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
