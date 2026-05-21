"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Legacy /admin/login route.
 *
 * CheckWise 1.8 collapsed every login surface into a single /login
 * page. This stub stays for any bookmarked URL and just redirects.
 */
export default function LegacyAdminLoginRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/login");
  }, [router]);
  return null;
}
