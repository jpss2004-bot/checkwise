import Link from "next/link";

import { cn } from "@/lib/utils";

/**
 * Inline link to a vendor's expediente page.
 *
 * Item 5 — every vendor mention across the client portal should be
 * clickable and land on `/client/vendors/[vendor_id]`. Centralising
 * here keeps the visual treatment consistent (subtle underline on
 * hover, brand-tinted text on focus) and gives us a single place to
 * tweak the destination later if product decisions change.
 *
 * Use ``muted`` for low-emphasis contexts (table cells, fine print);
 * the default treatment leaves the surrounding text styling intact
 * so the link blends with the row it sits in.
 */
export function VendorRef({
  vendorId,
  vendorName,
  className,
  muted = false,
  children,
  title,
}: {
  vendorId: string;
  vendorName?: string;
  className?: string;
  muted?: boolean;
  children?: React.ReactNode;
  title?: string;
}) {
  return (
    <Link
      href={`/client/vendors/${encodeURIComponent(vendorId)}`}
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
