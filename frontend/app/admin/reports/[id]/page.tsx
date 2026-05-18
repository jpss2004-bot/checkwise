"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

/**
 * /admin/reports/[id] — R1.0 placeholder.
 *
 * The editor itself is a 500+ line component currently wrapped in
 * PortalAppShell. Lifting it to support both shells in the same slice
 * is more refactor than R1.0 budgets; instead this route redirects to
 * the existing editor. The shared editor extraction lands in R1.0.1.
 */
export default function AdminReportEditorRedirect() {
  const params = useParams();
  const router = useRouter();
  const id = typeof params?.id === "string" ? params.id : "";

  useEffect(() => {
    if (id) router.replace(`/portal/reports/${id}`);
  }, [id, router]);

  return null;
}
