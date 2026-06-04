import Link from "next/link";

import { cn } from "@/lib/utils";

/**
 * Inline link to a vendor's expediente page.
 *
 * Item 5 — every vendor mention should be clickable. The destination
 * depends on the surface that renders it:
 *   - ``client`` (default): the client portal expediente at
 *     ``/client/vendors/[vendor_id]`` inside the ClientShell.
 *   - ``admin``: the operations expediente at
 *     ``/admin/vendors/[vendor_id]`` inside the AdminShell. Internal
 *     staff used to be dropped into the client portal chrome (wrong
 *     nav, client-facing framing); the admin surface keeps them in the
 *     operations console and links submissions to the reviewer.
 *
 * Centralising here keeps the visual treatment consistent (subtle
 * underline on hover, brand-tinted text on focus).
 *
 * Use ``muted`` for low-emphasis contexts (table cells, fine print);
 * the default treatment leaves the surrounding text styling intact
 * so the link blends with the row it sits in.
 */
export function VendorRef({
  vendorId,
  vendorName,
  clientId,
  surface = "client",
  className,
  muted = false,
  children,
  title,
}: {
  vendorId: string;
  vendorName?: string;
  /**
   * Optional client_id query param appended to the link. Required
   * when the link is rendered from an ``internal_admin`` shell so
   * the vendor-detail endpoint can resolve the scope without the
   * caller having to pick a default client first. ``client_admin``
   * shells leave this off — their tenant is implicit.
   */
  clientId?: string | null;
  /**
   * Which expediente surface to link to. ``admin`` keeps internal
   * staff inside the operations console instead of the client portal.
   */
  surface?: "client" | "admin";
  className?: string;
  muted?: boolean;
  children?: React.ReactNode;
  title?: string;
}) {
  const basePath = surface === "admin" ? "/admin/vendors" : "/client/vendors";
  const href = clientId
    ? `${basePath}/${encodeURIComponent(vendorId)}?client_id=${encodeURIComponent(clientId)}`
    : `${basePath}/${encodeURIComponent(vendorId)}`;
  return (
    <Link
      href={href}
      title={title ?? (vendorName ? `Abrir expediente de ${vendorName}` : "Abrir expediente del proveedor")}
      className={cn(
        "rounded-sm underline-offset-2 transition-colors hover:underline hover:text-[color:var(--text-brand)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--interactive-primary)]",
        muted && "text-[color:var(--text-secondary)] hover:text-[color:var(--text-primary)]",
        className,
      )}
    >
      {children ?? vendorName ?? "Ver proveedor"}
    </Link>
  );
}
