import * as React from "react";
import { Eye, EyeSlash } from "@phosphor-icons/react";

import { cn } from "@/lib/utils";
import { Input } from "./input";

type PasswordInputProps = Omit<React.InputHTMLAttributes<HTMLInputElement>, "type">;

const PasswordInput = React.forwardRef<HTMLInputElement, PasswordInputProps>(
  ({ className, disabled, ...props }, ref) => {
    const [pinnedVisible, setPinnedVisible] = React.useState(false);
    const [peekVisible, setPeekVisible] = React.useState(false);
    const visible = pinnedVisible || peekVisible;

    return (
      <div className="relative">
        <Input
          ref={ref}
          type={visible ? "text" : "password"}
          className={cn("pr-12", className)}
          disabled={disabled}
          {...props}
        />
        <button
          type="button"
          aria-label={visible ? "Ocultar contraseña" : "Mostrar contraseña"}
          aria-pressed={pinnedVisible}
          disabled={disabled}
          onClick={() => setPinnedVisible((value) => !value)}
          onMouseEnter={() => setPeekVisible(true)}
          onMouseLeave={() => setPeekVisible(false)}
          onPointerDown={() => setPeekVisible(true)}
          onPointerUp={() => setPeekVisible(false)}
          onPointerCancel={() => setPeekVisible(false)}
          onBlur={() => setPeekVisible(false)}
          className="absolute inset-y-0 right-0 flex w-12 items-center justify-center text-[color:var(--text-tertiary)] transition-colors hover:text-[color:var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/30 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {visible ? (
            <EyeSlash className="h-4 w-4" weight="bold" aria-hidden="true" />
          ) : (
            <Eye className="h-4 w-4" weight="bold" aria-hidden="true" />
          )}
        </button>
      </div>
    );
  },
);
PasswordInput.displayName = "PasswordInput";

export { PasswordInput };
