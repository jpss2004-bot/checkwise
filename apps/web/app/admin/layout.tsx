import type { ReactNode } from "react";

// M1-follow-up (2026-06-02) — mirror the cliente layout's
// force-dynamic. AdminShell now reads ``?client_id=`` from
// useSearchParams (via AdminWiseMount) at the layout level. Without
// force-dynamic, Next 15's static prerender bails out on /admin/*
// pages with the same Suspense complaint that hit /client/* before
// commit 567988f. Pages stay server-rendered + edge-cached; only
// the build-time prerender step is opted out.
export const dynamic = "force-dynamic";

export default function AdminLayout({ children }: { children: ReactNode }) {
  return <div className="min-h-screen bg-background">{children}</div>;
}
