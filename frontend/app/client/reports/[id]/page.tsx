"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

/**
 * /client/reports/[id] — R1.1 placeholder.
 *
 * The editor is a 500+ line component currently wrapped in
 * PortalAppShell. Lifting it to support all three shells in one
 * slice is more refactor than R1.1 budgets; instead this route
 * redirects to the existing editor. The shared editor extraction
 * lands in R1.0.1.
 */
export default function ClientReportEditorRedirect() {
  const params = useParams();
  const router = useRouter();
  const id = typeof params?.id === "string" ? params.id : "";

  useEffect(() => {
    if (id) router.replace(`/portal/reports/${id}`);
  }, [id, router]);

  return null;
}
