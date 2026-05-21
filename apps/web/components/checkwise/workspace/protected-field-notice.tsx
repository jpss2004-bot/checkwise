import { Lock } from "@phosphor-icons/react";

import { cn } from "@/lib/utils";

interface ProtectedFieldNoticeProps {
  /** Short label like "RFC" / "Razón social" / "Rol asignado". */
  label: string;
  /** The locked value to display. Rendered as text — never as HTML. */
  value: string;
  /** Optional supporting copy. */
  helper?: string;
  /** Render value with Geist Mono — recommended for RFCs / IDs. */
  mono?: boolean;
  className?: string;
}

/**
 * Read-only display for a tenant-locked field.
 *
 * Used on /portal/entra-a-tu-espacio and the dashboard
 * WorkspaceIdentityCard to communicate "this value is tied to your
 * workspace identity — to change it, request a correction." The lock
 * icon + muted styling make the protection visible without nagging.
 *
 * Spec: docs/CHECKWISE_1_6.md §4 (Protect Tenant Information).
 */
export function ProtectedFieldNotice({
  label,
  value,
  helper,
  mono = false,
  className,
}: ProtectedFieldNoticeProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-1 rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)] px-3 py-2.5",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
          {label}
        </p>
        <Lock
          className="h-3 w-3 text-[color:var(--text-tertiary)]"
          weight="bold"
          aria-label="Campo protegido"
        />
      </div>
      <p
        className={cn(
          "truncate text-[13px] text-[color:var(--text-primary)]",
          mono && "font-mono",
        )}
      >
        {value || (
          <span className="text-[color:var(--text-tertiary)]">No registrado</span>
        )}
      </p>
      {helper && (
        <p className="text-[11px] leading-4 text-[color:var(--text-tertiary)]">
          {helper}
        </p>
      )}
    </div>
  );
}
